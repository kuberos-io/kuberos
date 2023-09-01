# python
import logging
import json

# pykuberos
from .rosparameter import RosParameterList


logger = logging.getLogger('scheduler')


# DEFAULT_DDS_IMAGE_URL = 'metagoto/ros2_dds_server:humble-v1'
DEFAULT_DDS_IMAGE_URL = 'metagoto/dds_introspection_node:humble-v1.1.1'
DEFAULT_IMAGE_PULL_SEC = 'kuberos-fogrobo-registry-token-test-lala'

DEFAULT_ROS_VERSION = 'humble'
DEFAULT_CONTAINER_RESTART_POLICY = 'Never'


def convert_string_to_linux_convention(strings: str) -> str:
    """
    Convert the string to kubernetes naming convention
    """
    return "_".join(strings.split('-')).upper()


class RosModule():
    """
    Basis deployable unit in KubeROS 
    Each rosmodule contains serveral cohesive ros packages (nodes) to perform a certain task.
    """

    def __init__(self,
                 name: str,  # robot_name-module_name
                 discovery_svc_name: str,

                 container_image: dict,  # from deployment request
                 entrypoint: list,
                 source_ws: str = None,
                 
                 volumes: list = None,

                 target: str = None,  # target node name or resource group
                 resource_group='edge',  # edge resource group

                 requested_resources: dict = None, # for batch job
                 
                 image_pull_secret: str = None,
                 image_pull_policy: str = 'Always',  # Always|IfNotPresent|Never
                 node_selector_type: str = 'node',  # node|resource_group
                 ros_version: str = DEFAULT_ROS_VERSION,
                 restart_policy: str = DEFAULT_CONTAINER_RESTART_POLICY,
                 ) -> None:
        """
        RosModule instance for scheduler: 

        Args: 
            description: rosModule description in KubeROS manifest. 
            discovery_svc_name: name of the discovery server service! 
        """
        # parameter from scheduler
        self._name = name
        self.pod_name = None
        self._ros_version = ros_version
        self.discovery_svc_name = discovery_svc_name
        self.node_selector_type = node_selector_type

        self.target = target
        self.resource_group = resource_group

        # from deployment manifest
        # self.app_metadata = app_metadata
        self.image_name = container_image['image_name']
        self.image_url = container_image['image_url']
        self.entrypoint = entrypoint

        self._source_ws = source_ws
        
        if requested_resources is not None:
            self._resources = requested_resources
        else:
            self._resources = {}
        # self.requirements = module_manifest['requirements']

        # image registry
        self.image_pull_secret = DEFAULT_IMAGE_PULL_SEC if image_pull_secret is None else image_pull_secret
        self.ros_version = ros_version
        self.restart_policy = restart_policy
        self._image_pull_policy = image_pull_policy

        self.svc_env_host = convert_string_to_linux_convention(
            self.discovery_svc_name) + '_SERVICE_HOST'
        self.svc_env_port = convert_string_to_linux_convention(
            self.discovery_svc_name) + '_SERVICE_PORT'

        # rosparameters in yaml file
        self.volumes = []
        self.volume_mounts = []

        if volumes is not None:
            for volume in volumes:
                self.volumes.append(volume['volume'])
                self.volume_mounts.append(volume['volume_mount'])

        # rosparameter in key-value pair
        self.env = []
        self.ros_launch_args = []


    @property
    def pod_manifest(self):
        """
        Get the pod manifest for kubernetes
        TODO: add multiple node selector to prevent the conflict between the nodes.
              and the sync error between KubeROS DB and K8s etcd.
        """
        if self.node_selector_type == 'node':
            node_sel_key = 'device.kuberos.io/hostname'
            node_sel_value = self.target
        else:
            node_sel_key = 'kuberos.io/role'
            node_sel_value = self.resource_group

        launch_args_str = ' '.join(['{}:={}'.format(
            arg['arg_name'], arg['arg_value']) for arg in self.ros_launch_args])

        # TODO: Do we need multiple commands in the entrypoint?
        entrypoint = self.entrypoint[0] + ' ' + launch_args_str

        self.args = [f'source /opt/ros/{self._ros_version}/setup.bash',
                     f'source {self._source_ws}setup.bash',
                     'export ROS_DISCOVERY_SERVER=${}:${}'.format(
                         self.svc_env_host, self.svc_env_port),
                     entrypoint]

        self._pod_manifest = {
            'apiVersion': 'v1',
            'kind': 'Pod',
            'metadata': {
                'name': self._name,
                'labels': {
                    # 'app-name': metadata['appName'],
                    # 'app-version': self.app_metadata['appVersion']
                }
            },
            'spec': {
                'nodeSelector': {
                    node_sel_key: node_sel_value},
                'containers': [{
                    'image': self.image_url,
                    'name': self.image_name,
                    'imagePullPolicy': self._image_pull_policy,
                    'command': ["/bin/bash"],
                    'args': ['-c', ';'.join(self.args)],
                    'ports': [{
                        'containerPort': 11811,
                        'protocol': 'UDP'
                    }],
                    'env': self.env,
                    'volumeMounts': self.volume_mounts,
                    'resources': self._resources,
                }],
                'volumes': self.volumes,
                'imagePullSecrets': [
                    {
                        'name': self.image_pull_secret
                    }
                ],
                'restartPolicy': self.restart_policy,
            }
        }
        return self._pod_manifest

    def set_resources_request_limit(self, 
                                    requests: dict,
                                    limits: dict) -> None:
        """
        For using Nvidia GPU: 
        resources:
           limits:
             nvidia.com/gpu: 1
        """
        self._resources = {
            'requests': requests,
            'limits': limits
        }
    
    def get_kubernetes_manifest(self):
        """
        Return the kubernetes pod manifests for deploying the ros module to the target nodes.
        """
        return self.pod_manifest


    def attach_configmap_yaml(self,
                              configmap_name: str,
                              mount_path: str) -> None:

        # replace the . with - in the configmap name to meet the kubernetes naming convention
        volume_name = f'{configmap_name}-volume'.replace('.', '-')
        self.volumes.append({
            'name': volume_name,
            'configMap': {
                'name': configmap_name
            }
        })
        self.volume_mounts.append({
            'name': volume_name,
            'mountPath': mount_path,
            'readOnly': True,
        })

        # print("Attaching configmap from yaml file ")
        # print(self.volumes)
        # print(self.volume_mounts)


    def attach_configmap_key_value(self,
                                   configmap: dict,
                                   launch_param_list):
        """
        Attach a configmap to get the args for the container entrypoint
        TODO: Check the wether the namespace match the configmap name! 
        """

        logger.debug(
            "[Scheduling - Rosmodule] Parsing the values from key-value pair RosParam to the container")

        launch_param_dict = {item['param']: item for item in launch_param_list}

        for key, val in configmap['content'].items():

            # Parameter used as launch args
            if key in launch_param_dict:

                arg_name_in_configmap = '{}-{}'.format(configmap['name'].upper(),
                                                       launch_param_dict[key]['key'].upper().replace('_', '-'))

                self.env.append({
                    'name': arg_name_in_configmap,
                    'valueFrom': {
                        'configMapKeyRef': {
                            'name': configmap['name'],
                            'key': launch_param_dict[key]['key']
                        }
                    }
                })

                self.ros_launch_args.append({
                    'arg_name': launch_param_dict[key]['param'],
                    'arg_value': '$({})'.format(arg_name_in_configmap)
                })

            # environment variables
            else:
                self.env.append({
                    'name': key,
                    'valueFrom': {
                        'configMapKeyRef': {
                            'name': configmap['name'],
                            'key': key
                        }
                    }
                })


    def insert_device_params(self,
                             launch_dev_param_list: list,
                             onboard_node_state: dict):

        # print("Inserting device params")
        # print(launch_dev_param_list)
        # print(onboard_node_state)

        for dev_param in launch_dev_param_list:
            dev_name = dev_param['namespace']
            value = self.find_device_params(dev_name=dev_name,
                                            val_key=dev_param['param'],
                                            peripheral_devices=onboard_node_state['cluster_node_state']['peripheral_devices'])
            self.ros_launch_args.append({
                'arg_name': dev_param['param'],
                'arg_value': value
            })


    @staticmethod
    def find_device_params(dev_name: str,
                           val_key: str,
                           peripheral_devices: list) -> str:
        """
        TODO: Correct the device name in FleetState and use NodeState instead of dict. 
        """
        print("Device name: {}".format(dev_name))
        print("Peripheral devices: {}".format(peripheral_devices))
        dev_name = dev_name.lower().replace('_', '-')
        val_key = val_key.lower().replace('_', '-')

        for dev in peripheral_devices:
            if dev['deviceName'] == dev_name:
                return dev['parameter'][val_key]
        return ''


    def attach_bridge_server(self):
        """
        Add bridge server
        """
        pass


    def create_image_proxy(self):
        pass


    @property
    def name(self):
        return self._name


    def print_pod_svc(self):
        pod = self.pod_manifest
        print(json.dumps(pod, indent=4, sort_keys=False))


class DiscoveryServer(object):
    """
    Discovery server object for the fleet node. 
     - by default, the discovery server is deployed to the robot's main onboard computer.
     - if the robot has multiple onboard computers, a backup discovery server can be 
       used to ensure the availability of the discovery server.
    """

    def __init__(self,
                 name: str,
                 port: int,
                 target_node: str = None,  # hostname
                 image_pull_secret: str = None,
                 image_url: str = None,
                 image_pull_policy: str = 'Always',
                 requested_resources: dict = None, # for batch job TODO: Review!
                 add_env_for_introspection: bool = True,  # TODO Review!
                 skip_running: bool = False, # TODO: Issue with DDS in NAV2
                 volumes: list = None, # TODO: Review! To write the mata data to the volume
                 ) -> None:
        self._name = name
        self.port = port

        self._entrypoint = None  # change the entrypoint for backup discovery server
        self.kuberos_role = self.name

        # pod, svc name
        self.svc_name = f'{self._name}'
        self.pod_name = self._name

        # container image
        self.image_url = DEFAULT_DDS_IMAGE_URL if image_url is None else image_url
        self.image_pull_secret = DEFAULT_IMAGE_PULL_SEC if image_pull_secret is None else image_pull_secret
        self.image_pull_policy = image_pull_policy

        self.target_node = target_node
        self.target_port = 11811
        self.port_protocol = 'UDP'

        if requested_resources is not None:
            self._resources = requested_resources
        else:
            self._resources = {}
        
        # rosparameters in yaml file
        self.volumes = []
        self.volume_mounts = []

        if volumes is not None:
            for volume in volumes:
                self.volumes.append(volume['volume'])
                self.volume_mounts.append(volume['volume_mount'])

        self.env = []
        if add_env_for_introspection:
            self.set_env_for_introsprection()

        self._command = 'source /opt/ros/humble/setup.bash; fastdds discovery --server-id 0 --port 11811 -b'

        if skip_running:
            # TODO: Short cut
            # Issue: If we use cycloneDDS in the NAV2 example, 
            #        the CPU usage of discovery server node is about 1000 millicores.
            self._command = 'sleep 36000'


    def set_env_for_introsprection(self):
        """
        Set the environment variables for introspection
        """
        self.env.append({
            'name': 'DDS_DISCOVERY_SERVICE_NAME',
            'value': convert_string_to_linux_convention(self.svc_name) + '_SERVICE_HOST'
        })
        self.env.append({
            'name': 'DDS_DISCOVERY_PORT_NAME',
            'value': convert_string_to_linux_convention(self.svc_name) + '_SERVICE_PORT'
        })
        self.env.append({
            'name': 'FASTRTPS_DEFAULT_PROFILES_FILE',
            'value': '/dds_super_client_config.xml'
        })


    def set_target_node(self, node_name: str):
        self.target_node = node_name


    @property
    def name(self):
        """
        Return pod name
        """
        return self._name


    @property
    def discovery_svc_name(self):
        """
        Return service name for rosmodule to connect to the discovery server.
        """
        return self.svc_name


    @property
    def pod_manifest(self):
        """
        Return the pod manifest for kubernetes
        With determined node selector
        """
        self._pod_manifest = {
            'apiVersion': 'v1',
            'kind': 'Pod',
            'metadata': {
                'name': self.pod_name,
                # 'application': 'no-name', # todo: add application name
                'labels': {"kuberos-robot": self.name,
                           "kuberos-role": 'discovery-server'}
            },
            'spec': {
                'nodeSelector': {'device.kuberos.io/hostname': self.target_node},
                'containers': [{
                    'image': self.image_url,
                    'name': 'dds-discovery-server',
                    'imagePullPolicy': self.image_pull_policy,
                    'command': ['/bin/bash'],
                    'args': ['-c',
                             self._command
                             # 'source /opt/ros/humble/setup.bash; fastdds discovery --server-id 0 --port 11811 -b'
                             ],
                    'ports': [{
                        'containerPort': self.target_port,
                        'protocol': self.port_protocol
                    }],
                    'resources': self._resources,
                    'env': self.env,
                    'volumeMounts': self.volume_mounts,
                }],
                'volumes': self.volumes,
                'imagePullSecrets': [
                    {
                        'name': self.image_pull_secret
                    }
                ],
                'restartPolicy': 'Never',
            }
        }
        return self._pod_manifest


    @property
    def service_manifest(self):
        """
            Return the service manifest for kubernetes
        """
        self._svc_manifest = {
            'apiVersion': 'v1',
            'kind': 'Service',
            'metadata': {
                'name': self.svc_name,
                # 'labels': {"ros-role": "dds-discovery-server"}
            },
            'spec': {
                'type': 'ClusterIP',
                'ports': [{
                    'port': self.port,
                    'targetPort': self.target_port,
                    'protocol': self.port_protocol
                }],
                'selector': {
                    "kuberos-robot": self.name,
                    "kuberos-role": 'discovery-server'
                }
            }
        }
        return self._svc_manifest


    def use_custom_image(self,
                         image_url: str,
                         image_pull_secret: str,
                         image_pull_policy: str = 'Always') -> None:
        self.image_url = image_url
        self.image_pull_secret = image_pull_secret
        self.image_pull_policy = image_pull_policy


    def set_as_backup_server(self):
        """
        Set the discovery server id as 1
        """
        pass

    def set_as_primary_server(self):
        """
        Set the discovery server id as 0 
        """
        pass

    def mount_backup_volume(self):
        """
        Mount a volume to cache the dds participant data (json file)
        """
        pass
