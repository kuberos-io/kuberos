"""
Job Scheduler generates the pod list and svc for batch jobs
"""

# python
import logging
import copy
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
    """
    Select the edge node for the job
    """
    
    def __init__(self, 
                 next_job_list: list,
                 deployment_manifest: dict,
                 cluster_state: dict) -> None:
        """
        Initialize the KuberosScheduler
        param: deployment_manifest: dict - deployment manifest
        
        param: next_job_list: list - the next job list
            example: {
                'job_uuid': self.get_uuid(),
                'group_postfix': self.batch_job_group.group_postfix,
                'job_postfix': self.slug,
                'manifest': self.deployment_manifest,
            }
        
        param: cluster_state: dict - the cluster state for batch jobs
            {
                'cluster_name': 'kube', 
                'nodes': [{
                    'hostname': 'kube-edge-worker-02', 
                    'is_allocatable': True, 
                    'cpu': 3.968162422, 
                    'memory': 6.118108, 
                    'storage': 3.2684154680000006, 
                    'num_pods': 0},
                {
                    'hostname': 'kube-simbot-02', 
                    'is_allocatable': True, 
                    'cpu': 3.9455201, 
                    'memory': 5.321452000000001, 
                    'storage': 3.1729054499999947, 
                    'num_pods': 2}
                    ]
            }
        """
        
        self._deployment_manifest = DeploymentManifest(deployment_manifest)
        
        self._job_spec = self._parse_batch_job_spec(deployment_manifest)
        
        self._next_job_list = next_job_list
        
        self._rosparam_maps = RosParamMapList(self._deployment_manifest.rosparam_map)
        
        self._cluster_state = cluster_state
        
        self.scheduled_jobs = []
        
        
        self._disc_server = None
        
        self._configmaps = []
        
        self._volumes = []
        
        self._rosmodules = []

        self._sc_result = []

    def schedule(self) -> dict:
        
        # loop through the cluster node list 
        for node in self._cluster_state['nodes']:
            # check if the node is allocatable
            allocatable = self.check_node_allocability(node, self._job_spec)
            
            # if this node is not allocatable, skip it
            if not allocatable:
                logger.warning("[Job Scheduler] Node %s is not allocatable", node['hostname'])
                continue
            
            # if there is no more job to schedule, break the loop
            if len(self._next_job_list) == 0:
                logger.info("[Job Scheduler] No more jobs to schedule")
                break
            
            job = self._next_job_list.pop()
            
            # schedule the job to the node
            logger.debug("[Job Scheduler] Scheduling job %s to node %s", job['job_uuid'], node['hostname'])
            sc_job = self.schedule_one(node, job)
            self._sc_result.append(sc_job)

        return self._sc_result

    def schedule_one(self, node, job) -> dict:
        """
        Schedule one batch job
        """
        sc_job = {
            'disc_server': {},
            'configmaps': [],
            'volumes': [],
            'rosmodules': [],
        }
        
        hostname = node['hostname']
        pod_name_postfix = f"-{job['group_postfix']}-{job['job_postfix']}"
        
        sc_job['job_uuid'] = job['job_uuid']
        sc_job['group_postfix'] = job['group_postfix']
        
        sc_job['disc_server'] = self.schedule_discovery_server(
            hostname=hostname,
            pod_name_postfix=pod_name_postfix
        )
        
        sc_job['configmaps'] = self.schedule_configmaps()
        sc_job['volumes'] = self.schedule_volumes()
        
        sc_job['rosmodules'] = self.schedule_rosmodules(
            hostname=hostname,
            group_postfix = job['group_postfix'],
            job_postfix = job['job_postfix']
        )
        
        return sc_job


    def _parse_batch_job_spec(self, deployment_manifest) -> dict:
        """
        Get the batch job spec from the deployment manifest.
        If the job spec is not fully specified, use the default values.
        """
        job_spec = {
                'maxRetry': 1,
                'startupTimeout': 300,
                'runningTimeout': 300,
                'resources': {
                    'numProNode': 1,
                    'requests': {
                        'cpu': 1
                }
            }
        }
        
        job_spec_from_manifest = deployment_manifest.get('jobSpec', None)
        
        if job_spec is not None:
            # convert the cpu unit
            try:
                cpu = job_spec_from_manifest['resources']['requests'].get('cpu', 1)
                if type(cpu) == str:
                    cpu = float(cpu.replace('m', '')) / 1000
                    job_spec_from_manifest['resources']['requests']['cpu'] = cpu
            except:
                job_spec_from_manifest['resources']['requests']['cpu'] = 1
            job_spec.update(job_spec_from_manifest)
        
        return job_spec
            
    

    @staticmethod
    def check_node_allocability(node: dict,
                                job_spec) -> bool:    
        """
        Check whether the node can be used for the job
        # TODO: Filter with labels: The pod of number is not equal the number of jobs!
        """
        
        # number of pods
        num_pods_requested = job_spec['resources']['numProNode']
        num_pods_on_node = node['num_pods']
        if num_pods_requested <= num_pods_on_node:
            logger.warning("Node <%s> has %s pods running, %s pods requested",
                           node['hostname'], num_pods_on_node, num_pods_requested)
            return False
        
        # CPU usage
        cpu_requested = job_spec['resources']['requests']['cpu']
        cpu_available = node['cpu']
        if cpu_requested > cpu_available:
            logger.warning("Node <%s> has %s CPU available, %s CPU requested",
                           node['hostname'], cpu_available, cpu_requested)
            return False
        
        return True

    def schedule_discovery_server(self,
                                  hostname,
                                  pod_name_postfix) -> None:
        """
        Schedule a discovery server
        """
        self._disc_server = DiscoveryServer(
            name = f'batch-job-disc-server-{pod_name_postfix}',
            port = 11811,
            target_node = hostname,
            add_env_for_introspection=False,
            skip_running=True,
        )
        
        return {
            'pod': self._disc_server.pod_manifest,
            'svc': self._disc_server.service_manifest,
        }

    
    def schedule_configmaps(self):
        self._configmaps = self._rosparam_maps.get_all_configmaps_for_deployment()
        # print("Configmaps: ", self._configmaps)
        return self._configmaps

    def schedule_volumes(self) -> []:
        return []
    
    def schedule_rosmodules(self,
                            hostname: str,
                            group_postfix: str,
                            job_postfix: str,
                            ) -> list:
        rosmodules = []
        for module_mani in self._deployment_manifest.rosmodules_mani:
            pod_name = f'{group_postfix}-{module_mani.name}-{job_postfix}'
            sc_module = RosModule(
                name=pod_name,
                discovery_svc_name=self._disc_server.discovery_svc_name,
                node_selector_type='node',
                target=hostname,
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
                rosparam_maps=self._rosparam_maps,
                configmap_postfix=group_postfix
            )
            rosmodules.append(sc_module.get_kubernetes_manifest())
        
        return rosmodules


    def _attach_required_rosparameter_and_env_var(self,
                                                scheduled_module: RosModule,
                                                module_manifest,
                                                rosparam_maps: RosParamMapList,
                                                configmap_postfix: str = '') -> None:
        """
        Attach required ROS parameters to the scheduled module.

        :param scheduled_module: The ROS module scheduled to be attached.
        :param module_manifest: ROS module manifest.
        :param rosparam_maps: List containing ROS parameter maps.
        :param configmap_postfix: Postfix to be added to the configmap name to distinguish different groups.
        """

        # Get the required rosparameters from ROSModuleManifest
        req_rosparam_list = module_manifest.get_rosparam_list()
        # Match the corresponding RosParamMap
        # Find the custom rosparam from the RosParamMap
        req_rosparam_list.match_rosparam_map_list(rosparam_maps)

        # Get the required ros2 launch args
        req_launch_param = module_manifest.get_launch_param()
        launch_rosparam_list = module_manifest.get_launch_param_rosparam()

        # logger.debug("Required launch param: %s", req_launch_param)

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
            else:
                if req_rosparam.type == 'yaml':
                    # attach the configmap to scheduled ros module
                    # mount the configmap to the container
                    # Add group prefix!
                    scheduled_module.attach_configmap_yaml(configmap_name=f"{configmap_postfix}-{configmap.get('name')}",
                                                    mount_path=req_rosparam.mount_path)
                    
                if req_rosparam.type == 'key-value':
                    # add ENV variables with valueFrom - configMapKeyRef
                    # append the launch parameters with arg_value from the configmap
                    # TODO support dynamically setting the ros parameters through configmap
                    # TODO Add group prefix -> Review
                    
                    confgmap_copy = copy.deepcopy(configmap)
                    confgmap_copy['name'] = f"{configmap_postfix}-{confgmap_copy['name']}"
                    scheduled_module.attach_configmap_key_value(
                        configmap=confgmap_copy,
                        launch_param_list=launch_rosparam_list,
                    )
                