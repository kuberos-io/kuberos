"""
KubeROS Scheduler to determine the best node for the rosmodules.
"""

# python
import logging
import json
import ruamel.yaml 
from ruamel.yaml import YAML, load, safe_load
from typing import Optional

# Pykuberos
from .scheduler_base import SchedulingMsgs, RobotEntity
from .manifest import RosModuleManifest, DeploymentManifest
from .rosparameter import RosParamMapList
from .node import EdgeNodeGroup, FleetNode, NodeBase
from .fleet import FleetState


logger = logging.getLogger('scheduler')


"""
Idea: 
 - Scheduler update the should status in each deployment. 
 - Controller check the IST status of each deployment.
 - Dynamic scheduler will be executed periodically to update the SOLL status.

"""


class ScoringPluginBase(object):
    
    def __init__(self) -> None:
        self._score = 0
        
    def calculate_score(self):
        raise NotImplementedError


class SimpleScoringPlugin(ScoringPluginBase):
    
    def __init__(self) -> None:
        super().__init__()
        
    def calculate_score(self):
        pass


class SchedulerPlugin(object):
    
    def __init__(self, 
                 fleet_state: dict,
                 edge_state: dict,
                 cloud_state: dict,
                 ):
        self._fleet_state_state = fleet_state
        self._edge_state = edge_state
        self._cloud_state = cloud_state
        
    def check_fleet_status(self):
        pass
    
    def check_edge_status(self):
        pass
    
    def check_cloud_status(self):
        pass
    
    def check_network_status(self):
        pass
    
    def check_robot_status(self):
        pass
    
    def check_robot_network_status(self):
        pass
    
    def check_robot_resource_status(self):
        pass
    
    def check_robot_network_resource_status(self):
        pass




class KuberosScheduler(object):
    """
    Default KubeROS Initial Scheduler  -> Dynamic Scheduler (Used in periodical monitoring/checking)

    Depending on the development type, the scheduler will choose 
    the best node to deploy the ros module. 
    The fleet status and cluster status will as input to the scheduler.
    
    Don't retrieve the fleet/cluster status in the scheduler, the Pykuberos 
    library should be a standalone library, it works independently from the 
    hardware and software management system, which are integrated and implemented
    as parts of the KubeROS API server.
    
    Besides, the scheduler should focus how to find the best node to the application. 
    
    With addtional information, like repository secret, the scheduler returns 
    the resource list for Kubernetes (With node selection). 
    
    The scheduler also provides the methods to check the validity of 
    the deployment request. 
    
    Meanwhile, the scheduler should be able to be replaced by other schedulers. 
    
    Different cases: 
    
    ### solo deployment - onboard only: 
     - each robot has a discovery server 
     - In the case of network partition, the robot can still work independently. 
       However, we have to prevent K8s start a new pod on other nodes
    
    ### solo deployment - edge/cloud-vpn: 
     - each robot has a discovery server
     - modules that required onboard will be deployed to the onboard node (fleet node)
     - call scheduler plugin to check wether the condition of edge/cloud nodes are satisfied
     - new feature: 
       - backup node on the onboard node -> a bridge node is required! 
    
    ### multi-robots deployment - onboard only | edge | cloud-vpn:
     - similiar to solo deployment
     - each robot fleet has a discovery server
    
    ### multi-mirror deployment - edge/cloud-bridge:
     - requirements: the quata for accessing resource is available 
     - each robot has a discovery server
     - in the third party cluster -> multiple discovery server
     - each instance in the cloud is wrapped with a ROS2 namespace
     - gateway / ingress node: responsible for balance the traffic to each instance. -> provides an interface for customization. 
    
    1. parse the manifest depending on the deployment type, append the rosmodules to each fleet node.
    
    
    
    Input: 
        - manifest: deployment manifest: 
        - fleet: fleet status
        - available edge resources
        - available cloud resources
        - network status (bandwidth, latency, etc. todo later)
    Output: 
        - schedeuled (dict): deterministic description
        - generated pods (list): list of generated pods (with injected repository secret)
    """
    
    
    def __init__(self, 
                 deployment_manifest: dict,
                 fleet_state: dict = None,
                 edge_state: dict = None, 
                 cloud_state: dict = None,
                 ):
        """
        Input: 
         - deployment_manifest: deployment manifest: 
         - fleet_state: fleet nodes state from the KubeROS database
         - edge_state: edge nodes state from selected resource group
         - cloud_state: edge nodes state from selected resource group
        
        Notes:
         - state contains essential information for scheduling, such as hostname, robotname, etc.
         - state is a dict, which is retrieved from the KubeROS database.
         - for advanced scheduling, the state can be extended with additional information, such as 
           - network bandwidth
           - network latency 
           - etc.
        """

        logger.info("Initialize the scheduler")
        
        # print(deployment_manifest)
        # print(fleet_state)
        # print(edge_state)
        
        self._deploy_mani = DeploymentManifest(deployment_manifest)
        self._fleet_state = FleetState(fleet_state)
        self._edge_state = EdgeNodeGroup(edge_state)
        
        # ros parameter map
        self._rosparam_maps = RosParamMapList(self._deploy_mani.rosparam_map)
         
        # static file map
        
        # self._rosparam = RosParameter(self._deploy_mani.rosparameters)
        
        self.sc_msgs = SchedulingMsgs()
        self.robots = [] # list of robot entity objects
        self.sc_res = [] # scheduling result
        
        logger.info("[INIT] Number of available edge nodes: %s", self._edge_state.num_of_ava_edge_nodes)
        
        # schedule the rosmodules to the fleet nodes: 
        # self.schedule()

        self.ip_last_digit_start = 3
        
    def check_target_robots(self): 
        """ 
            Rename to: check_deployment_target
            Check the wether the target fleet is deployable. 
            Create the target node instance and add to the list. 
        Return: 
            - fleet_node instance in the scheduling_result object            
        """
        
        # check wether the target fleet is deployable
        if not self._fleet_state.is_fleet_deployable():
            self.sc_msgs.add_msg('error', 'Fleet is not deployable')
        
        # check target robots's availability
        # if the target robot attribute is not set
        # select all the robots from the fleet.
        self.tar_rob_names = self._deploy_mani.get_target_robot_names()
        if not len(self.tar_rob_names) == 0:
            res, msg = self._fleet_state.check_robot_names(self.tar_rob_names)
            if not res:
                self.sc_msgs.add_msg('error', msg)
        else:
            self.tar_rob_names = self._fleet_state.robot_names
        
        # return check result and msgs
        if self.sc_msgs.contains_error():
            return False, self.sc_msgs.get_msgs()
        else:
            return True, ''
    
    
    def init_robot_entities(self) -> None:
        """
        Add fleet node in the scheduling result object. 
        Add the discovery server to this fleet node. 
        
        """
        # get the hostname and cluster node state for each robot. 
        # Note: This is a new unfished feature for the case that one robot has multiple onboard devices.
        
        # get the hostname of the primary onboard computer of the robot
        comp_groups = self._fleet_state.computer_groups
        if len(comp_groups) > 1:
            self.sc_msgs.add_msg('warning', 'More than one computer group is available in the fleet. \
                    The discovery server will be deployed to the group {}.'.format(comp_groups[0]))  
        # get the node states 
        nodes_state = self._fleet_state.get_nodes_state_by_comp_group(
            group_name = comp_groups[0], 
            robot_name = self.tar_rob_names)
        #print(nodes_state)

        # add new robot to the scheduling result object
        for state in nodes_state:
            new_robot = RobotEntity(state)
            self.robots.append(new_robot)
            logger.info('[INIT] Add new robot: %s', new_robot.robot_name)
        return True 


    def bind_rosmodules_to_robots(self): 
        """ 
            Rename to: check_deployment_target
            Check the wether the target fleet is deployable. 
            Create the target node instance and add to the list. 
        Return: 
            - fleet_node instance in the scheduling_result object            
        """
        
        # bind discovery server to the every fleet robot unit 
        self.init_robot_entities()
            
        # iterate over all the rosmodules
        # allocate the rosmodules to the target
        for module_mani in self._deploy_mani.rosmodules_mani: 
            # bind to robots
            for rob in self.robots:
                rob.bind_rosmodule(module_manifest=module_mani,
                                   rmw_impl=self._deploy_mani.rmw_implementation)
                logger.info("[INIT] Bind rosmodule %s to robot %s", 
                            module_mani.name, rob.robot_name)

        # TODO: Check the validity of the deployment request (rosmodules)    
        return True, ''
    
    
    
    def schedule(self,
                 use_cyclonedds=False) -> list:
        """
        Reutrn the schedeuled and assembled deployment description
        List of dict contains scheduled resources of each robot. 
        Format:
            [{'robot_name': str
             'sc_disc_server': dict 
             'sc_onboard': list
             'sc_edge': list
             'sc_cloud': list
            }]
        """

        self.sc_res = []
        
        for rob in self.robots:
            # schedule the primary discovery server
            sc_disc_server = rob.schedule_primary_discovery_server()
            
            # check the onboard rosmodules 
            primary_node_state = self._fleet_state.get_node_state(rob.onboard_primary_node_name)
            # print(rob)
            # print(primary_node_state)
            success, err_msgs = rob.check_onboard_module_validity(primary_node_state)        
            if not success: 
                for msg in err_msgs:
                    self.sc_msgs.add_msg('error', msg)

            # schedule the onboard rosmodules
            # input: 
            #   - rosparameter_map
            #   - staticfile_map
            #   - fleet_node_state
            sc_onboard = rob.schedule_onboard_modules(
                rosparam_maps = self._rosparam_maps,
            )
            
            # schedule the edge rosmodules 
            sc_edge = rob.schedule_edge_modules(
                rosparam_maps = self._rosparam_maps
            )
            
            # schedule the cloud rosmodules
            
            
            # scheduling result
            sc_global_res = self.get_global_resources()
            self.sc_res.append({'robot_name': rob.robot_name,
                                'sc_disc_server': sc_disc_server,
                                'sc_onboard': sc_onboard,
                                'sc_edge': sc_edge
                            })

            # print for debugging 
            self._rosparam_maps.print()
            self.print_sc_result()
            
        return self.sc_res, sc_global_res
            
    def get_global_resources(self) -> dict:
        """
        Return the config maps, staticfiles resources, which 
        are used in the entire fleet and have to be deployed firstly. 
        """
        configmap_list = self._rosparam_maps.get_all_configmaps_for_deployment()
        return {
            'sc_configmaps': configmap_list,
        }

    def schedule_rosmodule(self):
        """
        Schedule the rosmodule across the entire fleet, edge and the cloud.
        """
        pass
    
    
    def prioritize_nodes(self, 
                         nodes: list, 
                         rosmodules):
        """
        Prioritize the nodes, depending on the scheduling policy. 
        Input: 
            - rosmodules: containers the requirements
            - nodes: list of node objects 
        """
        # run pre-score-plugin
        # run score-plugin
        # calculate the final score
        # final_score = score * weight * framwork_max_node_score/Max_Extender_Priority 
        # select the best score node in the list 
        pass

    
    def find_best_node(self):
        """
        Find the best node from the available nodes. 
        onboard computer, edge, cloud 
        OR: the node in the edge.
        """
        pass 
    

    def create_configmap_for_rosparams(self):
        """
        Set the ros parameters for each robot. 
        """
        pass

    
    def load_staticfiles(self):
        pass
    
    
    @classmethod
    def load_manifest_from_yaml(cls, 
                                yaml_file: str, 
                                is_path: bool = True) -> None:
        """
        Load the manifest from a yaml file or yaml string.
        For using without KubeROS platform
        """
        if is_path: 
            yaml_file_path = yaml_file
            yaml = YAML(typ='safe', pure=True)
            with open(yaml_file_path) as f:
                try:
                    manifest = yaml.load(f)
                except:
                    print("File is not existed")
        else:
            manifest = safe_load(yaml_file)
        return cls(manifest)


    def update_fleet_state(self, 
                            fleet_state: str) -> None:
        """
        Interface for dynamic scheduler. 
        """
        self._fleet_state = fleet_state

            
    def print_sc_result(self):

        for res in self.sc_res:
            print("===============     {}   ================== ".format(res.get('robot_name')))
            print("=============== Discovery Server ================== ")
            disc_server = res.get('sc_disc_server')
            json_str = json.dumps(disc_server, indent=4)
            print(json_str)
            
            print("=============== Onboard Modules ================== ")
            onboard_modules = res.get('sc_onboard')
            json_str = json.dumps(onboard_modules, indent=4)
            print(json_str)
            
            print("=============== Edge Modules ================== ")
            onboard_modules = res.get('sc_edge')
            json_str = json.dumps(onboard_modules, indent=4)
            print(json_str)
        
        
    def save_as_yaml(self, output_path: str):
        
        yaml = ruamel.yaml.YAML()
        yaml.indent(mapping=2, sequence=4, offset=2)
        yaml.default_flow_style = False
        yaml.anchor_sort = False
        yaml.dump(self.sc_res, open(output_path, "w"))

        # with open(output_path, "w") as f:
        #    ruamel.yaml.safe_dump(self.schedeuled, f)
        print(f"Saved to {output_path}")
    


class ScedulingPolicy(object):
    pass 


    

class CloudNodeGroup(EdgeNodeGroup):
    # worker nodes in the cloud
    # differences to the edge worker nodes??? 
    #  - network bandwidth
    #  - network latency
    pass





class ScheduledThirdPartyCluster(NodeBase):
    pass
    # third party cluster
    

    
    
