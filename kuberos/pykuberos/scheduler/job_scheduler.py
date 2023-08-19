"""
Job Scheduler generates the pod list and svc for batch jobs
"""

# python
import logging
import json
import ruamel.yaml 
from ruamel.yaml import YAML, load, safe_load

# Pykuberos
from .scheduler_base import SchedulingMsgs, RobotEntity
from .manifest import RosModuleManifest, DeploymentManifest
from .rosmodule import RosModule, DiscoveryServer
from .manifest import RosModuleManifest
from .rosparameter import RosParamMapList
from .node import EdgeNodeGroup, FleetNode, NodeBase
from .fleet import FleetState

logger = logging.getLogger('scheduler')


class JobScheduler():
    
    def __init__(self, 
                 deployment_manifest: dict,
                 ec_state: dict) -> None:
        """
        Initialize the KuberosScheduler
        param: deployment_manifest: dict - deployment manifest
        param: ec_state: dict - the state of the edge or cloud nodes
        """
        
        self._deployment_manifest = DeploymentManifest(deployment_manifest)
        
        self._rosparam_maps = RosParamMapList(self._deployment_manifest.rosparam_map)
        
        self._ec_state = ec_state
        
        self._disc_server = None
        
        self._configmaps = []
        
        self._volumes = []
        
        self._rosmodules = []
    
    def schedule(self) -> dict:
        self.sc_result = {
            'disc_server': {},
            'configmaps': [],
            'volumes': [],
            'rosmodules': [],
        }
        
        self.sc_result['disc_server'] = self.schedule_discovery_server()
        self.sc_result['configmaps'] = self.schedule_configmaps()
        self.sc_result['volumes'] = self.schedule_volumes()
        self.sc_result['rosmodules'] = self.schedule_rosmodules()
        
        return self.sc_result
        
    def schedule_discovery_server(self) -> None:
        """
        Schedule a discovery server
        """
        self._disc_server = DiscoveryServer(
            name = f'xxx-disc',
            port = 11811,
            target_node = 'Todo'
        )
        
        return {
            'pod': self._disc_server.pod_manifest,
            'svc': self._disc_server.service_manifest,
        }
        
    
    def schedule_configmaps(self):
        self._configmaps = self._rosparam_maps.get_all_configmaps_for_deployment()
        print("Configmaps: ", self._configmaps)
        return self._configmaps

    def schedule_volumes(self) -> []:
        return []
    
    def schedule_rosmodules(self) -> list:
        for module_mani in self._deployment_manifest.rosmodules_mani:
            pod_name = 'todo'
            sc_module = RosModule(
                name=pod_name,
                discovery_svc_name=self._disc_server.discovery_svc_name,
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
                rosparam_maps=self._rosparam_maps
            )
            self._rosmodules.append(sc_module.get_kubernetes_manifest())
        return self._rosmodules
    
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