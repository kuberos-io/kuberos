# python
from typing import List

# pykuberos 
from .rosmodule import RosModule
from .rosparameter import RosParameter, RosParamMap, RosParameterList 


WORKSPACE_PATH_DEFAULT = '/workspace/install/'


class DeploymentManifest(object):
    """
    KubeROS deployment manifest. 
    """
    def __init__(self, 
                 manifest: dict) -> None:
        
        self._manifest = manifest
        self._rosmodules_mani = []
        for module_mani in self._manifest['rosModules']:
            self._rosmodules_mani.append(RosModuleManifest(module_mani, 
                                                           container_registry_list=self.container_registry))
        
    @property
    def metadata(self) -> dict:
        """
        Return the metadata as dict
        """
        return self._manifest['metadata']
    
    @property
    def rosmodules_mani(self) -> List[dict]:
        """
        Return the list of rosmodules manifest
        # TODO: Check it! 
        """
        return self._rosmodules_mani
    
    def get_target_robot_names(self):
        """
        Check wether this deployment is for the specific robots.
        Return: 
            - list of robot names
            - empty list if this deployment is for all robots in this fleet.
        """
        return self.metadata.get('targetRobots', [])
    
    @property
    def rosparam_map(self) -> List[RosParamMap]:
        """
        Get the custom ros parameters from the deployment manifest. 
        
        """
        return self._manifest.get('rosParamMap', [])

    @property
    def staticfile_map(self):
        """
        Get the static file maps
        """
        return self._manifest.get('staticFileMap', [])

    def substitute_params(self, 
                          hardware_specs: dict, 
                          configmap: dict):
        pass
    
    @property
    def container_registry(self):
        container_registry = self._manifest.get('containerRegistry', None)
        if not container_registry:
            return []
        return container_registry
    
    def get_default_container_registry(self):
        result = {
                'imagePullSecret': '',
                'imagePullPolicy': 'Always'
            }
        container_registry = self._manifest.get('containerRegistry', None)

        if container_registry is None:
            return result

        # find the default container registry
        for item in container_registry:
            if item['name'] == 'default':
                result['imagePullSecret'] = item['imagePullSecret']
                result['imagePullPolicy'] = item['imagePullPolicy']

        return result


    def __repr__(self) -> str:
        return f'<DeploymentManifest: {self.metadata["name"]}>'    
    


class RosModuleManifest(object):
    """
    Object to parse the RosModule in the deployment manifest. 
    Each ros module contains the following information:
        - container image name / address / entrypoint
        - preference: onboard / edge / cloud
        - requirements
        - launchParameters -> Parameters used as arguments for the ros launch file.
            - device sepecific parameters: upper case, e.g. {SIM_ARM.ROBOT_IP}, 
                                           acquired from KubeROS device registry.
            - launch arguments: lower case, e.g. {launch_parameters.use_sim},
                                           acquired from the attached RosParamMap
        - rosParameters -> loaded from the rosParamMap and are used as ROS paramteters.
        - staticFiles -> loaded from the staticFileMap and are used as static files. 
    """
    
    def __init__(self, 
                  rosmodule_manifest: dict,
                  container_registry_list: list) -> None:
        """
        Parse the rosmodule manifest.
        """
        self._module_mani = rosmodule_manifest
        self._requirements = self._module_mani.get('requirements', {})
        
        self._container_registry = {
            'imagePullSecret': '',
            'imagePullPolicy': 'Always',
        }
        self._container_registry_list = container_registry_list
        
        self._launch_param_list = self.parse_launch_param()
        
        # RosParameterList objects
        self._rosparam_list = self.parse_rosparam_from_manifest()
        
        # get container registry pull secret and policy
        self._parse_container_registry()
    
    def _parse_container_registry(self):
        """
        Get the container registry by name
        """
        req_container_registry = self._module_mani.get('containerRegistry', None)
        
        if not req_container_registry:
            # use the default container registry
            for item in self._container_registry_list:
                if item['name'] == 'default':
                    self._container_registry['imagePullSecret'] = item['imagePullSecret']
                    self._container_registry['imagePullPolicy'] = item['imagePullPolicy']
            return
        
        # find the required container registry
        for item in self._container_registry_list:
            if item['name'] == req_container_registry:
                self._container_registry['imagePullSecret'] = item['imagePullSecret']
                self._container_registry['imagePullPolicy'] = item['imagePullPolicy']
            return
        

    @property
    def container_registry(self):
        return self._container_registry


    def parse_rosparam_from_manifest(self) -> RosParameterList:
        """
        Return the required ros parameters as a list of RosParameter objects.
        This method is used in the RobotEntity to schedule the bind rosmodules. 
        """
        return RosParameterList(self._module_mani.get('rosParameters', []))
    
    def get_rosparam_list(self) -> RosParameterList:
        return self._rosparam_list
    
    def get_launch_param(self):
        return self._launch_param_list
    
    def get_launch_param_device(self):
        param_dev = []
        for param in self._launch_param_list:
            if param['type'] == 'device':
                param_dev.append(param)
        return param_dev
    
    def get_launch_param_rosparam(self):
        param_rosparam = []
        for param in self._launch_param_list:
            if param['type'] == 'rosparam':
                param_rosparam.append(param)
        return param_rosparam
    
    def parse_launch_param(self):
        """
        Parse the launch parameters and sort them by the letter case.
        Upper case: device specific parameters 
        Lower case: value from attached rosparameters
        """
        
        param_list = []
        launch_param_dict = self._module_mani.get('launchParameters', {}) 
        
        for param, val in launch_param_dict.items():

            param_val = list(val.keys())[0]
                        
            # split the provided launch parameter into namespace and key
            # for rosparam: 
            #      Given: {launch_parameters.use_sim}
            #           namespace: launch_parameters
            #           key: use_sim 
            # for device: 
            #      Given: {SIM_ARM.ROBOT_IP}
            #           namespace: sim_arm
            #           key: robot_ip
            namespace, key = param_val.split('.')
            
            param_list.append({
                'param': param,
                'type': self.check_launch_param_type(param_val),
                'namespace': namespace,
                'key': key,
            })
        return param_list
    
    
    @staticmethod
    def check_launch_param_type(param_key: str) -> str:
        """
        Check the launch parameter type. 
        """
        if param_key.isupper():
            return 'device'
        elif param_key.islower():
            return 'rosparam'
        else:
            return 'unknown'
    
    def calculate_node_score(self, node_state: dict):
        pass
    
    def get_bind_ros_module(self, 
                            name: str, 
                            selector_type: str,
                            target_node: str, 
                            ) -> RosModule:
        pass 
    
    @property
    def name(self):
        """
        Return the rosmodule name.
        """
        return self._module_mani['name']
    
    @property
    def preference(self) -> str:
        """
        Get the deployment preference of the rosmodule. 
        If no preference is specified, return 'onboard' as default.
        Return: 
            str: 'onboard' | 'edge' | 'cloud'
        """
        pref = self._module_mani.get('preference', [])
        if len(pref) == 0: 
            return 'onboard'
        else:
            return pref[0]
    
    @property
    def peripheral_devices(self) -> List[str]:
        """
        Return the name list of the required peripheral devices.
        """
        return self._requirements.get('peripheral_devices', [])
    
    @property
    def requirements(self)-> dict:
        return self._requirements 
        
    @property
    def container_image(self) -> dict:
        """
        Return the container image name and url
        """
        return {
            'image_name': self._module_mani['name'],
            'image_url': self._module_mani['image']}
    
    @property
    def required_launch_param_list(self) -> List[str]:
        
        required_launch_param = self._module_mani.get('requiredLaunchParamList', {})
        return required_launch_param.keys()
    
    @property
    def entrypoint(self):
        """
        Return the command that will be executed.
        """
        return self._module_mani['entrypoint']
    
    @property
    def source_ws(self):
        """
        Return the path to the setup.bash
        Format: /workspace/install/
            with dash at the end
        """
        source_ws = self._module_mani.get('sourceWs', WORKSPACE_PATH_DEFAULT)
        if not source_ws.endswith('/'):
            source_ws += '/'
        return source_ws
    
    def __repr__(self) -> str:
        return f'<RosModule: {self.name}>'
