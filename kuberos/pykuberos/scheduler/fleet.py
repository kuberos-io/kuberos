"""
Fleet state and node state objects
"""

# python
import logging

logger = logging.getLogger('scheduler')

class NodeState(object):
    
    def __init__(self, fleet_node_state) -> None:
        """
        fleet_node_state: dict
    
        """
        self._node_state = fleet_node_state
        self._peripheral_devices = self.parse_peripheral_devices()
        
        logger.debug("[NodeState] Node <%s> Mounted peripheral devices in node: %s", 
                     self.hostname,
                     self._peripheral_devices)
        
    @property
    def hostname(self):
        return self._node_state['hostname']
    
    @property
    def robot_name(self):
        return self._node_state['robot_name']
    
    @property
    def robot_id(self):
        return self._node_state['robot_id']
    
    @property
    def onboard_comp_group(self):
        return self._node_state['onboard_comp_group']
    
    def parse_peripheral_devices(self):
        """
        Change the parameter name to uppercase letters, 
        following the definition in the deployment manifest, to distinguish different parameter types.
        for example:
            robot_ip -> ROBOT_IP
        """
        peripharal_devs = self._node_state['cluster_node_state'].get('peripheral_devices', [])
        devs_new_list = []
        for dev in peripharal_devs:
            dev_new = {
                'device_name': dev['deviceName'],
                'parameter': {}
            }
            for key, value in dev['parameter'].items():
                # dev_new['parameter'].update({key.upper().replace('-', '_'): value})
                dev_new['parameter'].update({key.upper(): value})
            devs_new_list.append(dev_new)
        return devs_new_list

    def get_peripheral_dev_params_by_name(self, 
                                          dev_name: str) -> dict:
        for dev in self._peripheral_devices:
            if dev['device_name'] == dev_name:
                return dev['parameter']
        return {}
    
    
### StatusCache 
class FleetState(object):
    """
    Cache the current status of the fleet and accessable resources (edge/cloud)
    
    This object will be instantiated with the current status cached in the KubeROS database. 
    
    """
    
    def __init__(self, 
                 fleet_state: dict,
                 ) -> None:
        self.fleet_state = fleet_state
        self.node_group = {}
        
        self._robot_names = []
        self.sort_fleet_node()
        
        self._fleet_nodes = {}
        for f_node in fleet_state['fleet_node_state_list']:
            # initialize the fleet node state instances
            self._fleet_nodes.update({
                f_node['hostname']: NodeState(f_node)
            })
            # gather the robot names
            if f_node['robot_name'] not in self._robot_names:
                self._robot_names.append(f_node['robot_name'])
    
    @property
    def robot_names(self):
        """
        Return the robot name list in the fleet.
        """
        return self._robot_names
    
    @property
    def computer_groups(self):
        """
        Return the list of available computer groups.
        """
        return list(self.node_group.keys())
    
    def get_peripheral_devices(self, hostname: str):
        """
        Return the list of peripheral devices in the target node.
        """
        for node in self.fleet_state['fleet_node_state_list']:
            if node['hostname'] == hostname:
                return node['cluster_node_state']['peripheral_devices']
        return None
    
    def get_nodes_state_by_comp_group(self, 
                                   group_name: str, 
                                   robot_name: list = []):
        """
        return list 
        check the validity of the request group name and robot name is done in 
        the scheduler precheck.
        """
        nodes_state = []
        for node in self.fleet_state['fleet_node_state_list']:
            if node['cluster_node_state']['computer_group'] == group_name:
                nodes_state.append(node)
        # filter by robot name
        if len(robot_name) > 0:
            nodes_state = [node for node in nodes_state if node['robot_name'] in robot_name]
        
        return nodes_state
    
    def sort_fleet_node(self):
        for node in self.fleet_state['fleet_node_state_list']:
            group = node['onboard_comp_group']
            hostname = node['hostname']
            
            if group not in self.node_group.keys():
                self.node_group.update({group: [hostname]})
            else: 
                self.node_group[group].append(hostname)
                
                
    def check_robot_names(self, 
                              tar_rob_names: list):
        invalid_rob_names = []
        for name in tar_rob_names:
            if name not in self._robot_names:
                invalid_rob_names.append(name)
        if len(invalid_rob_names) > 0:
            return False, 'The request robot names {} are not found in the fleet. \n\
                           Available robot names: {}'.format(invalid_rob_names, self.robot_name_list)
        else:
            return True, ''
        
        
    def get_node_state(self, node_name: str):
        """
        Get the node state by the node name (hostname).
        """
        for node in self.fleet_state['fleet_node_state_list']:
            if node['hostname'] == node_name:
                return node
        return None
    
    def check_fleet_node_name_and_computer_group(self,
                                                 node_name: str,
                                                 node_group: str):
        success = False 
        msg = ''
        if node_group not in self.node_group.keys():
            msg = '[Error] The computer group is not existed in the fleet. \n\
                    Available computer groups: {}'.format(self.node_group.keys())
            return success, msg
        else: 
            if node_name not in self.node_group[node_group]:
                msg = '[Error] The node name is not existed in this computer group. \n\
                        Available nodes in <{}>: {}'.format(node_group,
                                                            self.node_group[node_group])
                return success, msg
            else:
                success = True
                return success, msg
            
    def is_fleet_deployable(self):
        """
        Check if the fleet is deployable. 
        """
        if not self.fleet_state['active']:
            return False
        if not self.fleet_state['deployable']:
            return False
        if len(self.fleet_state['fleet_node_state_list']) == 0:
            return False
        return True
    
    def get_available_onboard_computer_group(self):
        return self.node_group.keys()
    

    def get_schedulings_node_list(self, 
                                    req_comp_group: str, 
                                    req_comp_list: list):
        err = False
        msg = ''
        node_list = []
        
        # check the request group name
        if req_comp_group not in self.node_group.keys():
            error = True
            msg = '[Error] The request targetOnboardComputerGroup {} is not existed in the fleet. \n\
                    Available computer groups: {}'.format(req_comp_group, self.node_group.keys())
            return err, msg, []
        
        # if the taregetOnboardComputers is not specified, this rosmodule will be deployed to every node in this group
        if len(req_comp_list) == 0:
            node_list = self.node_group[req_comp_group]
            return err, msg, node_list
        
        # check wether the request onboard computer name available in the fleet
        for req_comp in req_comp_list:
            unavailable_comp = []
            if req_comp not in self.node_group[req_comp_group]:
                unavailable_comp.append(req_comp)
                
        if len(unavailable_comp) > 0:
            err = True
            msg = '[Error] The request targetOnboardComputers {} is not existed in the fleet. \n\
                    Available onboard computers in <{}>: {}'.format(unavailable_comp,
                                                                    req_comp_group,
                                                                    self.node_group[req_comp_group])
            return err, msg, []
        else:
            return err, msg, req_comp_list
        
    
    def get_fleet_node_status(self, name: str):
        status = ''
        for node in self.fleet_state['fleet_node_set']:
            if node['name'] == name:
                return node['status']
        return status

    
    