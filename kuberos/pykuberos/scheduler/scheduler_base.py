# python
import logging
from typing import Optional, List

# Pykuberos
from .rosmodule import RosModule, DiscoveryServer
from .manifest import RosModuleManifest
from .rosparameter import RosParamMapList

logger = logging.getLogger('scheduler')


class RobotEntity():
    """
    A robot can have multiple onboard computers.
    For simple deployment, we assume that there is only one onboard computer.
    """

    def __init__(self, node_state) -> None:
        """
        node_state: dict - the node state of the primary node of the robot.
        """

        self.rmw_impl = 'fastdds'
        self._robot_name = node_state['robot_name']
        self.robot_id = node_state['robot_id']
        self.hostname = node_state['hostname']
        self.robot_primary_node_name = node_state['hostname']
        self._node_state = node_state

        self.onboard_module_mani = [] # List of RosModuleManifest
        self.edge_module_mani = []

        self.sc_onboard_modules = [] # list of scheduled RosModule instance
        self.sc_edge_modules = [] # list of scheduled RosModule instance

        self.sc_onboard = []
        self.sc_edge = []


    def schedule_primary_discovery_server(self) -> None:
        """
        Bind a default discovery server to the primary node.
        """
        
        # if not self.rmw_impl == 'fastdds':
        #     # if using cyclonedds, skip the discovery server
        #     return []
        
        self.primary_discovery_server = DiscoveryServer(
            name = f'{self._robot_name}-primary-discovery-server',
            port = 11811, # 11311
            target_node = self.robot_primary_node_name)
        self.pri_disc_svc_name = self.primary_discovery_server.discovery_svc_name

        pod_manifest = self.primary_discovery_server.pod_manifest
        svc_manifest = self.primary_discovery_server.service_manifest
        return [{
            'pod': pod_manifest,
            'svc': svc_manifest,
        }]
        
    
    def bind_rosmodule(self, 
                        module_manifest: RosModuleManifest,
                        rmw_impl: str = 'fastdds') -> None:
        """
        Bind the ros_modules to the robot
        """
        # get target node
        target = module_manifest.preference
        
        self.rmw_impl = rmw_impl
        
        if target == 'onboard':
            self.onboard_module_mani.append(module_manifest)
        elif target == 'edge':
            self.edge_module_mani.append(module_manifest)
    
    def check_onboard_module_validity(self, node_state: dict):
        """
        Check the validity of the onbard module manifest and 
        the required resources on the node, such as
         - cpu architecture 
         - container runtime 
         - mounted peripheral devices: like robot, camera, lidar, gripper, etc.
        """
        
        err_msgs = []
        
        # check the required peripheral devices 
        node_peri_dev_list = node_state['cluster_node_state']['peripheral_devices']
        for mani in self.onboard_module_mani:
            req_dev_list = mani.peripheral_devices
            for req_dev in req_dev_list:
                if req_dev not in node_peri_dev_list:
                    err_msgs.append(f'Required peripheral device {req_dev} is not available on the node {self.robot_primary_node_name}')
        
        # check the cpu architecture
        
        # check the container runtime
        
        # check the nvidia gpu
        
        if len(err_msgs) > 0:
            return False, err_msgs
        
        logger.info("[Scheduling] Check validity of onboard module [PASSED]")
        
        return True, ''


    def _attach_required_rosparameter_and_env_var(self,
                                                  scheduled_module: RosModule,
                                                  module_manifest,
                                                  rosparam_maps: RosParamMapList) -> None:
        """
        Attach required ROS parameters to the scheduled module.

        :param scheduled_module: The ROS module scheduled to be attached.
        :param module_manifest: ROS module manifest.
        :param rosparam_maps: List containing ROS parameter maps.
        """

        # Get the required rosparameters from ROSModuleManifest
        req_rosparam_list = module_manifest.get_rosparam_list()
        # Match the corresponding RosParamMap
        # Find the custom rosparam from the RosParamMap
        req_rosparam_list.match_rosparam_map_list(rosparam_maps)

        # Get the required ros2 launch args
        req_launch_param = module_manifest.get_launch_param()
        launch_rosparam_list = module_manifest.get_launch_param_rosparam()

        logger.debug("Required launch param: %s", req_launch_param)

        # Loop to attach parameters from the manifest to the scheduled module
        # Parameters from each RosParamMap are used in
        #   - volume mount - yaml
        #   - environment variables - key-value
        #   - launch parameters - key-value
        for req_rosparam in req_rosparam_list.rosparam_list:

            # get configmap
            configmap = rosparam_maps.get_configmap_by_name(
                    param_map_name=req_rosparam.value_from
                    )

            logger.debug("[Scheduling] Attaching required rosparam: %s \n - Value from: %s \n - ConfigMap: %s", 
                            req_rosparam.name,
                            req_rosparam.value_from,
                            configmap)
                            
            if configmap == {}:
                # TODO: raise error
                logger.error("[Scheduling] RosParam <%s> Configmap is empty", 
                                req_rosparam.name)
            
            if req_rosparam.type == 'yaml':
                # attach the configmap to scheduled ros module
                # mount the configmap to the container
                scheduled_module.attach_configmap_yaml(configmap_name=configmap.get('name'),
                                                mount_path=req_rosparam.mount_path)
                
            if req_rosparam.type == 'key-value':
                # add ENV variables with valueFrom - configMapKeyRef
                # append the launch parameters with arg_value from the configmap
                # TODO support dynamically setting the ros parameters through configmap
                scheduled_module.attach_configmap_key_value(
                    configmap=configmap,
                    launch_param_list=launch_rosparam_list,
                )
    

    def schedule_onboard_modules(self,
                                 rosparam_maps: RosParamMapList) -> list:
        """
        Schedule the onboard modules to the primary node.
        """
        for module_mani in self.onboard_module_mani:
            
            # Initialize the pod 
            pod_name = f'{self._robot_name}-{module_mani.name}'
            target_node = self.robot_primary_node_name
            sc_module = RosModule(
                name=pod_name,
                discovery_svc_name=self.pri_disc_svc_name,
                target=target_node,
                node_selector_type='node',
                container_image=module_mani.container_image,
                image_pull_secret=module_mani.container_registry['imagePullSecret'],
                image_pull_policy=module_mani.container_registry['imagePullPolicy'],
                entrypoint=module_mani.entrypoint,
                source_ws=module_mani.source_ws,
                )
            
            # Attach ros parameters and environment variables
            self._attach_required_rosparameter_and_env_var(
                scheduled_module=sc_module,
                module_manifest=module_mani,
                rosparam_maps=rosparam_maps
            )
            
            # Add the device parameter from the fleet state
            launch_dev_param_list = module_mani.get_launch_param_device()
            sc_module.insert_device_params(
                launch_dev_param_list = launch_dev_param_list,
                onboard_node_state = self._node_state
            )
            
            # Add the rosmodule to the scheduled list
            self.sc_onboard_modules.append(sc_module)
            self.sc_onboard.append(sc_module.get_kubernetes_manifest())
            
            logger.debug("[Scheduling] ROS launch args: %s", sc_module.ros_launch_args)
            logger.debug("[Scheduling] Entry point: %s", sc_module.entrypoint)
            # print(sc_module.print_pod_svc())

        return self.sc_onboard


    def schedule_edge_modules(self, 
                              rosparam_maps: RosParamMapList):
        """
        After binding the edge modules to the robot, 
        check the feasibility of deploying the edge modules to the edge.
        
        If the requirement is not fulfilled, reschedule 
        the edge modules to the onboard computers. 
        """
        for module_mani in self.edge_module_mani:
            
            # Intitialize the pod
            pod_name = f'{self._robot_name}-{module_mani.name}'
            sc_module = RosModule(
                name=pod_name,
                discovery_svc_name=self.pri_disc_svc_name,
                node_selector_type='edge',      
                container_image=module_mani.container_image,
                image_pull_secret=module_mani.container_registry['imagePullSecret'],
                image_pull_policy=module_mani.container_registry['imagePullPolicy'],
                entrypoint=module_mani.entrypoint,
                source_ws=module_mani.source_ws,
                )
            
            # Attach ros parameters and environment variables
            self._attach_required_rosparameter_and_env_var(
                scheduled_module=sc_module,
                module_manifest=module_mani,
                rosparam_maps=rosparam_maps
            )
            
            # Add the rosmodule to the scheduled list
            self.sc_edge_modules.append(sc_module)
            self.sc_edge.append(sc_module.get_kubernetes_manifest())
            
        return self.sc_edge


    @property
    def onboard_primary_node_name(self):
        """
        Return the hostname of the primary onboard computer. 
        """
        return self.hostname


    def get_sc_modules(self):
        """
        Return all kubernetes pod and service manifests of the scheduled modules.
        """
        dds_pod_list = [self.primary_discovery_server.pod_manifest]
        dds_svc_list = [self.primary_discovery_server.service_manifest]
        onboard_pod_list = []
        edge_pod_list = []
        for module in self.sc_onboard_modules:
            onboard_pod_list.append(module.get_kubernetes_manifest())
        for module in self.sc_edge_modules:
            edge_pod_list.append(module.get_kubernetes_manifest())
        return {
            'dds_pod_list': dds_pod_list,
            'dds_svc_list': dds_svc_list,
            'onboard_pod_list': onboard_pod_list,
            'edge_pod_list': edge_pod_list
        }
        
    def get_discovery_server(self):
        pod_manifest = self.primary_discovery_server.pod_manifest
        svc_manifest = self.primary_discovery_server.service_manifest
        return {
            'pod': pod_manifest,
            'svc': svc_manifest,
        }
    
    def get_scheduled_modules(self):
        sc_modules_k8s = []
        for module in self.sc_onboard_modules:
            sc_modules_k8s.append(module.get_kubernetes_manifest())
        for module in self.sc_edge_modules:
            sc_modules_k8s.append(module.get_kubernetes_manifest())
        return sc_modules_k8s
    
    def get_onboard_modules(self):
        return self.onboard_module_mani
    
    def get_edge_modules(self):
        return self.onboard_module_mani
    
    @property
    def robot_name(self):
        return self._robot_name
    
    
    def __repr__(self) -> str:
        return f'RobotName: {self._robot_name}, Onboard: {self.onboard_module_mani}, Edge: {self.edge_module_mani}'


class SchedulingMsgs():
    """
    Gathering the analysis result from the scheduler. 
    Add message to the message queue.
    Check result.
    Message types:
     - Debug:
     - Info: 
     - Warning: 
     - Error: 
    """
    def __init__(self, ) -> None:
        self.msgs = []

    def add_msg(self,
                   msg_type: str,
                   msg: str):
        """
        Add msg with msg type: 
        args: 
            - msg_type: debug | info | warning | error
        """
        if msg_type not in ['debug', 'info', 'warning', 'error']:
            print("Invalid msg type")
            self.msgs.append({msg_type: msg})

    def contains_error(self):
        """
        Check whether error occured in the scheduling process.
        """
        for msg in self.msgs:
            if 'error' in msg.keys():
                return True
        return False

    def get_msgs(self):
        """
        Get all messages
        """
        return self.msgs

    def print_msgs(self):
        """
        Print messages for debugging
        """
        print(self.msgs)
