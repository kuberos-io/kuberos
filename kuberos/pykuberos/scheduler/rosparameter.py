"""
This module contains two objects for parsing the ros parameter from deployment manifest
 - RosParamMap 
 - RosParamMapList
 - RosParam
"""

# python
from typing import Optional, List

class RosParamMap():
    """
    RosParamMap instance to parse the ros parameter map provided in the deployment manifest
    """

    def __init__(self,
                 ros_param_map: dict,
                 ) -> None:
        """
        Args: 
            ros_param_map: item in the rosParamMap in KubeROS deployment manifest. 
        """
        # parameter from scheduler
        self._ros_param_map = ros_param_map
        self.err_msgs = []
        self._ros_param_configmap = self.parse_ros_param_map(param_map=self._ros_param_map)
        
        self.print()

    def parse_ros_param_map(self,
                            param_map: dict) -> dict:
        """
        Parse the ros parameter map from the manifest.
        """
        ros_param_configmap = {}
        if param_map['type'] == 'yaml':
            success, data, err_msg = self.load_ros_parameter_from_yaml(
                param_map['path'])
            if not success:
                self.err_msgs.append(err_msg)
                print(self.err_msgs)
                content = ''
            else:
                content = {param_map['name']: data}
        elif param_map['type'] == 'key-value':
            content = self.replace_boolean_for_configmap(
                data=param_map['data'])
        else:
            self.err_msgs.append(
                "Unsupported rosParamMap type: {}".format(param_map['type']))
            content = ''
        ros_param_configmap.update({
            'name': param_map['name'],
            'type': param_map['type'],
            'content': content
        })

        return ros_param_configmap

    def get_configmap_for_deployment(self) -> dict: 
        """
        Return the parsed config map
        """
        return self._ros_param_configmap
    
    @property
    def configmap_name(self) -> str:
        """
        Return the name of parsed configmap
        """
        return self._ros_param_configmap['name']

    @property
    def ros_param_map_name(self) -> str:
        """
        Return the name of ros parameter map
        """
        return self._ros_param_map['name']

    @staticmethod
    def load_ros_parameter_from_yaml(path: str) -> str:
        """
        Load ros_parameter from a yaml file
        return: 
            - success: bool
            - dict: ros_parameter_dict
            - err_msgs: list
        """
        err_msgs = []
        try:
            with open(path, 'r') as f:
                ros_param_yaml = f.read()
            return True, ros_param_yaml, ''

        except FileNotFoundError:
            err_msgs.append("Parameter file not found: {}".format(path))
            return False, {}, err_msgs

    @staticmethod
    def replace_boolean_for_configmap(data: dict):
        """
        Replace the boolean value for configmap
        """
        for key in data.keys():
            if isinstance(data[key], bool):
                data[key] = 'True' if data[key] else 'False'
        return data

    def print(self):
        """
        Print the parameter list for debugging purpose
        """
        print("Read configmap: {}".format(self._ros_param_map['name']))
        print(self._ros_param_configmap)
        
        


class RosParamMapList():
    """
    RosParamMapList instance to parse the ros parameter map
    """
    def __init__(self,
                 ros_param_map_list: list,
                 ) -> None:
        """
        RosParamMap instance to parse the ros parameter map provided in the deployment manifest: 

        Args: 
            ros_parameter_map: rosParameters description in KubeROS manifest. 
        """

        self._param_map_list = self.parse_ros_param_map(ros_param_map_list)
        self.err_msgs = []
        self.print()

    def parse_ros_param_map(self, 
                            ros_param_map_list: list):
        """
        Parse the ros parameter map from the manifest.
        """
        param_list = []
        for item in ros_param_map_list:
            param_map = RosParamMap(ros_param_map=item)
            param_list.append(param_map)
        return param_list
    
    def get_all_configmaps_for_deployment(self) -> list:
        """
        Return 
         - configmap_name
         - configmap_dict
        """
        configmaps = []
        for param_map in self._param_map_list:
            configmaps.append(param_map.get_configmap_for_deployment())
        return configmaps
        
    def get_configmap_by_name(self,
                              param_map_name: str) -> dict:
        """
        Return the configmap by name for scheduler
        """
        for param_map in self._param_map_list:
            if param_map_name == param_map.configmap_name:
                return param_map.get_configmap_for_deployment()
        return {}
    
    def print(self):
        """
        Print the parameter list for debugging purpose
        """
        for param_map in self._param_map_list:
            param_map.print()


class RosParameter():
    """
    Required ROS parameter object in the RosModule from the RosModule manifest.
    """

    def __init__(self,
                 required_rosparam: dict
                 ) -> None:
        """
        Args: 
         - required_rosparam: a dict contains following key-value pairs: 
            - name 
            - type: yaml / key-value
            - valueFrom: name of rosParamMap
            - mountPath (optional): the yaml path in the container for ros launch to get the parameter
        """
        self._req_param = required_rosparam
        self._configmap = {}

    def matach_rosparam_map_list(self,
                                 ros_param_map_list: RosParamMapList):
        """
        Get the configmap from the ros_param_map_list
        """
        self._configmap = ros_param_map_list.get_configmap_by_name(
            self.value_from)
        
    def get_configmap(self):
        """
        Return the name of the configmap
        """
        return self._configmap
    
    @property
    def name(self):
        """
        Return the of the required ROS parameter
        """
        return self._req_param['name']
    
    @property
    def type(self):
        """
        Return the parameter type: 
            - yaml: 
            - key-value:
        """
        return self._req_param.get('type', '')

    @property
    def mount_path(self):
        """
        Return the mount path in the container.
        """
        return self._req_param.get('mountPath', '')

    @property
    def value_from(self):
        """
        Return the "valueFrom"
        This value indicates the name of the rosParamMap. 
        In KubeROS, the actual parameter is provided separately in the rosParamMap. 
        """
        return self._req_param.get('valueFrom', '')
    
    def print(self):
        """
        Print for debugging purpose
        """
        print("[KubeROS ROS Parameter] - [Info] - Name: {}".format(self.name))
        print("  - type: {}".format(self.type))
        print("  - mountPath: {}".format(self.mount_path))
        print("  - valueFrom: {}".format(self.value_from))
        print("  - configmap: {}".format(self._configmap))





class RosParameterList(): 
    """
    Object to parse the ros parameter list from the deployment manifest.
    """
    def __init__(self, rosparam_mani_list: list) -> None:
        """
        Args: 
            - rosparam_mani_list: rosParameters description in KubeROS manifest.
        """
        self._rosparam_list = self.parse_rosparam_mani(rosparam_mani_list)
        
    def parse_rosparam_mani(self, 
                            rosparam_mani_list: list) -> List[RosParameter]:
        """
        Parse manifest and return a list of RosParameter objects.
        """
        rosparam_list = []
        for item in rosparam_mani_list: 
            rosparam_list.append(RosParameter(item))
        return rosparam_list
    
    @property
    def rosparam_list(self) -> List[RosParameter]:
        """
        Return the parsed RosParameter object
        """
        return self._rosparam_list
    
    def match_rosparam_map_list(self,
                                ros_param_map_list: RosParamMapList) -> None:
        """
        Match the rosparam_map_list with the rosparam_list
        """
        for rosparam in self._rosparam_list:
            rosparam.matach_rosparam_map_list(ros_param_map_list)
    
    def get_configmap_by_name(self, 
                              name: str) -> dict:
        """
        Get the configmap that will be created in the cluster
        """
        for rosparam in self._rosparam_list:
            if rosparam.name == name:
                return rosparam.get_configmap()
        
    def print(self):
        for item in self._rosparam_list:
            item.print()
    
    