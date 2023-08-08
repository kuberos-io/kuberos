# Python
import sys
import time
import logging
from typing import List

# Kubernetes
import kubernetes
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from urllib3.exceptions import MaxRetryError



logger = logging.getLogger('pykuberos')



class KubeConfig():
    """
    Kubenetes cluster config object
    """

    def __init__(self,
                k8s_config_dict: dict,
                 ) -> None:

        self._cluster_config = kubernetes.client.Configuration()

        self._cluster_config.host = k8s_config_dict['host_url']
        self._cluster_config.api_key['authorization'] = k8s_config_dict['service_token']
        self._cluster_config.api_key_prefix['authorization'] = 'Bearer'
        self._cluster_config.ssl_ca_cert = k8s_config_dict['ca_cert_path']

        # self.kube_config_file = "path_to_config"
        # self.context = "context in this config"
        # self.token = "token"

    @property
    def cluster_config(self) -> dict:
        """
        Return the cluster config object
        """
        return self._cluster_config



class ExecutionResponse():
    """
    Execution response class for KubeROS tasks.
    """

    def __init__(self) -> None:
        self._status = 'pending'
        self._data = {}
        self._errors = []
        self._msgs = []

    def clear(self) -> None:
        self.__init__()

    def set_success(self) -> None:
        self._status = 'success'

    def set_data(self, data: dict) -> None:
        """
        set the data to the response.
        """
        self._data = data

    def add_msg(self, msg: str) -> None:
        """
        Add the message to the response.
        """
        self._msgs.append(msg)

    def _add_error(self,
                   err_reason: str,
                   err_msg: str,
                   err_msg_verbose: str = '') -> None:
        if not isinstance(err_reason, str):
            raise ValueError("The err_reason must be a string.")
        if not isinstance(err_msg, str):
            raise ValueError("The err_msg must be a string.")

        self._errors.append({
            'reason': err_reason,
            'err_msg': err_msg,
            'msg_verbose': err_msg_verbose
        })

    def raise_api_exception_error(self,
                                  exc: ApiException) -> None:
        """
        Add the error message from ApiException to the response.
        """

        self._add_error(
            err_reason=exc.reason,
            err_msg=self.parse_error_reason(exc),
            err_msg_verbose=exc.body
        )
        self._status = 'failed'

    def parse_error_reason(self,
                           exc: ApiException) -> str:
        """
        Return a more readable error message for KubeROS users
        """
        msg = 'Cluster is not reachable.'

        reason = exc.reason
        if reason == 'Unauthorized':
            msg = 'Cluster service account token is invalid or expired.'

        return msg


    def set_rejected(self,
                     reason: str,
                     msg: str = None) -> None:
        self._status = 'rejected'
        self._add_error(
            err_reason=reason,
            err_msg=msg
        )

    def set_failed(self,
                   reason: str,
                   err_msg: str) -> None:
        """
        Set the response status as failed.
        """
        self._status = 'failed'
        self._add_error(reason, err_msg)

    def to_dict(self) -> dict:
        """
        Get the response as a dict.
        """
        return {
            'status': self._status,
            'data': self._data,
            'errors': self._errors,
            'msgs': self._msgs
        }


class KubernetesExecuter():
    """
    Handler to interact with Kubernetes cluster.
    Provides following functionalities:
        - create/delete namespaces
        - create/delete pods
        - create/delete services
        - create/delete configmaps
        - create/delete daemonsets
    """

    def __init__(self,
                 kube_config: dict,
                 namespace: str = 'ros-default',
                 ) -> None:
        """
        Args:
            - kube_config: {
                'name': 'kubernetes',
                'host_url': 'https://xxxxx:6443',
                'service_token': 'admin-token-xxxxx',
                'ca_cert_path': '/home/xxxxx/ca.crt',
            }
        """
        self._kube_config = KubeConfig(kube_config)
        self._ns = namespace

        self._kube_client = kubernetes.client.ApiClient(
            self._kube_config.cluster_config)
        self._kube_core_api = kubernetes.client.CoreV1Api(self._kube_client)

        self._response = ExecutionResponse()

        logger.debug("KubernetesExecuter initialized.")


    def __exit__(self, exc_type, exc_value, traceback):
        self._kube_client.close()


    ### NAMESPACE ###
    def create_namespace(self,
                         namespace: str) -> ExecutionResponse:
        """
        Create a new namespace
        """
        try:
            existed_ns = self._kube_core_api.list_namespace(_request_timeout=1)
        except ApiException as exc:
            self._response.raise_api_exception_error(exc)
            return self._response.to_dict()
        except MaxRetryError:
            self._response.set_failed(
                reason='UnexpectedError',
                err_msg=f'Unexpected error: {sys.exc_info()[0]}'
            )
            print(self._response.to_dict())
            sys.exit(1)

        # check if the namespace already exists
        for item in existed_ns.items:
            if item.metadata.name == namespace:
                # logger.debug("Namespace <%s> already exists.", namepace)
                self._response.set_success()
                self._response.set_data(
                    self._kube_client.sanitize_for_serialization(item)
                )
                self._response.add_msg(
                    f'Namespace <{namespace}> already exists.')
                return self._response.to_dict()

        # namespace manifest
        ns_manifest = {
            'apiVersion': 'v1',
            'kind': 'Namespace',
            'metadata': {
                'name': namespace,
            }
        }

        try:
            res = self._kube_core_api.create_namespace(body=ns_manifest)
            self._response.set_data(res)
            self._response.set_success()

        except ApiException as exc:
            self._response.raise_api_exception_error(exc)

        return self._response.to_dict()


    ### NODE ###
    def get_nodes_status(self,
                   node_selector=None) -> ExecutionResponse:
        """
        Get node status in the cluster
        TODO: TimeoutError
        """
        try:
            res = self._kube_core_api.list_node()

            nodes = []
            for item in res.items:
                node = {
                    'name': item.metadata.name,
                    'labels': item.metadata.labels,
                    'status': self._kube_client.sanitize_for_serialization(item.status),
                    'ready': self.check_node_readiness(item),
                }
                nodes.append(node)

            self._response.set_data(nodes)
            self._response.set_success()
        except ApiException as exc:
            self._response.raise_api_exception_error(exc)

        return self._response.to_dict()


    @staticmethod
    def check_node_readiness(node: dict) -> str:
        """
        Find the node readiness status from the node status conditions.
        """
        try:
            conditions = node.status.conditions
        except AttributeError:
            return 'Unknown'

        if conditions is None:
            return 'Unknown'

        for condition in conditions:
            if condition.type == 'Ready':
                return condition.status

        # If no 'Ready' condition is found, return 'Unknown'
        return 'Unknown'


    def label_node(self,
                   node_name: str,
                   labels: dict) -> ExecutionResponse:
        """
        Add labels to the nodes.
        Label is crucial as identifier for the node selection in the deployment
        It must be careful maintained, to avoid any inconsistences and conficts.

        args:
            - node_name: str
            - labels: dict, e.g. {
                    'resource.kuberos.io/type': 'onboard',
                    'robot.kuberos.io/name': 'dummy-1'
                }
        """
        try:
            node = self._kube_core_api.read_node(name=node_name)
            node.metadata.labels.update(labels)
            res = self._kube_core_api.patch_node(name=node_name,
                                                 body=node)
            
            new_labels = res.metadata.labels
            self._response.set_data(new_labels)
            self._response.set_success()

        except ApiException as exc:
            self._response.raise_api_exception_error(exc)

        return self._response.to_dict()


    ### POD ###
    def create_pod(self,
                   pod_manifest: dict) -> ExecutionResponse:
        """
        Create a pod in a given namespace

        Args:
            - pod_manifest: pod manifest in dict format
        """

        try:
            res = self._kube_core_api.create_namespaced_pod(
                body=pod_manifest,
                namespace=self._ns,
            )
            self._response.set_data(res)
            self._response.set_success()

        except ApiException as exc:
            self._response.raise_api_exception_error(exc)

        return self._response.to_dict()


    def check_pod_status(self,
                         pod_name: str) -> ExecutionResponse:
        """
        Check the pod status
        """
        # simplified pod status
        pod_status = {
            'name': pod_name,
            'status': '',
            'container_status': '',
            'pod_ip': '',
            'reason': '',
            'msg': None
            }

        try:
            res = self._kube_core_api.read_namespaced_pod_status(
                namespace=self._ns,
                name=pod_name
            )
            pod_status['status'] = res.status.phase
            pod_status['container_status'] = self._kube_client.sanitize_for_serialization(
                res.status.container_statuses)
            pod_status['pod_ip'] = res.status.pod_ip
            pod_status['msg'] = res.status.message
            pod_status['reason'] = res.status.reason
            pod_status['conditions'] = self._kube_client.sanitize_for_serialization(
                res.status.conditions)

            # check if the pod is in the terminating state
            if res.metadata.deletion_timestamp is not None:
                
                pod_status['status'] = 'Terminating'

            self._response.set_data(pod_status)
            self._response.set_success()

        except ApiException as exc:
            if exc.reason == 'Not Found':
                pod_status['status'] = 'NotFound'
                self._response.set_data(pod_status)
                self._response.set_success()
            else:
                self._response.raise_api_exception_error(exc)

        return self._response.to_dict()


    def delete_pod(self,
                   pod_name: str) -> ExecutionResponse:
        """
        Delete a pod
        """
        try:
            res = self._kube_core_api.delete_namespaced_pod(
                namespace=self._ns,
                name=pod_name,
            )
            self._response.set_data(res)
            self._response.set_success()

        except ApiException as exc:
            if exc.reason == 'Not Found':
                self._response.set_success()
            else:
                self._response.raise_api_exception_error(exc)

        return self._response.to_dict()


    ### SERVICE ###
    def create_service(self,
                       svc_manifest: dict) -> ExecutionResponse:
        """
        Create a service in a given namespace

        Args:
            - svc_manifest: service manifest in dict format
        """

        try:
            res = self._kube_core_api.create_namespaced_service(
                body=svc_manifest,
                namespace=self._ns
            )
            self._response.set_data(res)
            self._response.set_success()

        except ApiException as exc:
            self._response.raise_api_exception_error(exc)

        return self._response.to_dict()


    def check_service_status(self,
                             svc_name: str) -> ExecutionResponse:
        """
        Check the service status
        """
        svc_status = {
            'name': svc_name,
            'status': '',
            'cluster_ip': '',
            'ports': '',
            'reason': '',
            'msg': None
        }

        try:
            res = self._kube_core_api.read_namespaced_service_status(
                namespace=self._ns,
                name=svc_name
            )
            svc_status['status'] = 'Found'
            svc_status['cluster_ip'] = res.spec.cluster_ip
            svc_status['ports'] = self._kube_client.sanitize_for_serialization(res.spec.ports)
            self._response.set_data(svc_status)
            self._response.set_success()

        except ApiException as exc:
            if exc.reason == 'Not Found':
                svc_status['status'] = 'NotFound'
                self._response.set_data(svc_status)
                self._response.set_success()
            else:
                self._response.raise_api_exception_error(exc)

        return self._response.to_dict()


    def delete_service(self,
                       svc_name: str) -> ExecutionResponse:
        """
        Delete a service
        """
        try:
            res = self._kube_core_api.delete_namespaced_service(
                namespace=self._ns,
                name=svc_name
            )
            self._response.set_data(res)
            self._response.set_success()

        except ApiException as exc:
            self._response.raise_api_exception_error(exc)

        return self._response.to_dict()



    ### CONFIGMAP ###
    def create_configmap(self,
                         name: str,
                         content: dict) -> ExecutionResponse:
        """
        Create a configmap in a given namespace

        Args:
            - name: str - name of the configmap
            - content: dict - content of the configmap
        """
        logger.debug("[Kube Client] Creating Configmap: %s", name)

        configmap=client.V1ConfigMap(
            api_version='v1',
            kind='ConfigMap',
            metadata=client.V1ObjectMeta(
                name=name,
                namespace=self._ns
            ),
            data=content
        )

        try:
            res=self._kube_core_api.create_namespaced_config_map(
                namespace=self._ns,
                body=configmap
            )
            
            self._response.set_data(
                self._kube_client.sanitize_for_serialization(res)
            )
            self._response.set_success()

        except ApiException as exc:
            self._response.raise_api_exception_error(exc)

        return self._response.to_dict()


    def delete_configmap(self,
                         name: str) -> ExecutionResponse:
        """
        Delete a configmap in a given namespace

        Args:
            - name: str - name of the configmap
        """
        logger.debug("[Kube Client] Deleting Configmap: %s", name)

        try:
            res=self._kube_core_api.delete_namespaced_config_map(
                namespace=self._ns,
                name=name
            )

            print("x " * 20)
            print(res)
            
            # check the response status
            if res.status == 'Success': # snippet from response: {..., "status": "Success"}
                self._response.set_data(self._kube_client.sanitize_for_serialization(res))
                self._response.set_success()
            else:
                self._response.set_failed(
                    reason='FailedToDeleteConfigmap',
                    err_msg='Failed to delete configmap.'
                )
            
        except ApiException as exc:
            if exc.reason == 'Not Found':
                # if the configmap is not found, set the response as success
                self._response.set_success()
            else:
                self._response.raise_api_exception_error(str(exc))

        return self._response.to_dict()


class KuberosExecuter(KubernetesExecuter):
    """
        Interface to interact with Kubernetes cluster,
        contains multiple operations to realize the whole functionality.
        It includes:
         - prepare new namespace for deployment
         - create dds servers and services
         -
    """
    def __init__(self,
                 kube_config: dict,  # Union[dict, KubeConfig] = KubeConfig(),
                 namespace: str='ros-default',
                 ) -> None:
        super().__init__(kube_config=kube_config,
                         namespace=namespace)


    def deploy_disc_server(self, 
                           disc_server_list: list) -> ExecutionResponse:
        """
        Deploy discovery server(s) for ONE robot.
        Primary server and a secondary (backup) server as optional.
        
        Args:
            - disc_server_list: list of dds manifest dict.
        """

        # check or create namespace
        self.create_namespace(namespace='ros-default')

        # create dds server and services
        for disc_server in disc_server_list:
            pod=disc_server['pod']
            svc=disc_server['svc']

            try:
                self.create_pod(pod_manifest=pod)
                self.create_service(svc_manifest=svc)
                self._response.clear()
                self._response.set_data({
                    'dds_pods': pod['metadata']['name'],
                    'dds_services': svc['metadata']['name'],
                    })
                self._response.set_success()

            except Exception as exc:
                print(exc)
                self._response.set_failed(
                    reason='FailedToCreateDDSServer',
                    err_msg='Failed to create dds discovery server.'
                )
                # raise Exception("Failed to create dds discovery server.")
        return self._response.to_dict()

        # return {
        #     'dds_pods': pod['metadata']['name'],
        #     'dds_services': svc['metadata']['name']}


    def deploy_rosmodules(self,
                           pod_list: list) -> dict:
        """
        Deploy a list of ROS modules in the cluster.
        
        Args:
            - pod_list: list of pod manifest dict.
        """

        pod_name_list=[]

        for pod in pod_list:
            try: 
                res = self.create_pod(pod_manifest=pod)
                
                if res['status'] == 'failed':
                    return res
                
                pod_name_list.append(pod['metadata']['name'])

            except Exception as exc:
                # catch unknown exception 
                logger.fatal("Failed to create pod: %s", pod['metadata']['name'])
                logger.fatal(exc)
                self._response.set_failed(
                    reson='FailedToCreatePod',
                    err_msg=str(exc),
                )
                return self._response.to_dict()
        
        self._response.set_data({
            'ros_pods': pod_name_list,
            'namespace': self._ns
             })
        self._response.set_success()
        
        return self._response.to_dict()


    def check_deployed_pod_status(self,
                                  pod_list: list) -> dict:
        """
        Get the status of the deployed pods.
        """
        try: 
            for pod in pod_list:
                logger.debug("Check pod status: %s", pod['name'])
                check_res=self.check_pod_status(pod_name=pod['name'])
                pod.update(check_res['data'])
            self._response.set_data(pod_list)
            self._response.set_success()
            return self._response.to_dict()
        
        except Exception as exc:
            # catch unknown exception
            logger.fatal("Failed to check pod status: %s", pod['name'])
            self._response.set_failed(
                reason='FailedToCheckPodStatus',
                err_msg=str(exc),
            )
            return self._response.to_dict()   


    def check_deployed_svc_status(self,
                                  svc_list: list) -> dict:
        """
        Get the status of the deployed services.
        """
        try:
            for svc in svc_list:
                logger.debug("Check svc status: %s", svc['name'])
                check_res=self.check_service_status(svc_name=svc['name'])
                svc.update(check_res['data'])
            self._response.set_data(svc_list)
            self._response.set_success()
            return self._response.to_dict()
        
        except Exception as exc:
            # catch unknown exception
            logger.fatal("Failed to check svc status: %s", svc['name'])
            self._response.set_failed(
                reason='FailedToCheckSvcStatus',
                err_msg=str(exc),
            )
            return self._response.to_dict()

        
    def delete_rosmodules(self,
                          pod_list: list,
                          svc_list: list=[]) -> None:
        """
        Delete rosmodules in the cluster.
        """
        try:
            for pod in pod_list:
                self.delete_pod(pod_name=pod)
            for svc in svc_list:
                self.delete_service(svc_name=svc)
            self._response.set_success()
        except Exception as exc:
            self._response.set_failed(
                reason='FailedToDeletePod',
                err_msg=str(exc),
            )
        return self._response.to_dict()

    def deploy_configmaps(self,
                         configmap_list: List[dict]) -> dict:
        """
        Create ConfigMaps from list 

        Args: 
            - configmap_list: list of configmap dict
        """
        for configmap in configmap_list:
            
            try:
                res = self.create_configmap(
                    name=configmap['name'],
                    content=configmap['content'],
                )
                if res['status'] == 'failed':
                    # Retrurn the failure response and break the loop
                    return res
                self._response.set_data(res)
                self._response.set_success()

            except Exception as exc: 
                # catch unknown exception
                logger.fatal("Failed to create configmap: %s", configmap['name'])
                logger.fatal(exc)
                self._response.set_failed(
                    reason='FailedToCreateConfigmap',
                    err_msg=exc
                )
                # break the loop and return the failure response
                return self._response.to_dict()

        return self._response.to_dict()


    def delete_deployed_configmaps(self,
                          configmap_list) -> dict:
        """
        Delete all ConfigMaps in the list
        """
        for configmap in configmap_list:
            try:
                res = self.delete_configmap(name=configmap['name'])
                if res['status'] == 'failed':
                    # Retrurn the failure response and break the loop
                    return res
                self._response.set_data(res)
            except Exception as exc: 
                logger.fatal("Failed to delete configmap: %s", configmap['name'])
                logger.fatal(exc)
                self._response.set_failed(
                    reason='FailedToDeleteConfigmap',
                    err_msg=str(exc)
                )
                self._response.to_dict()
        
        # if no exception, set the response as success
        self._response.set_success()
        return self._response.to_dict()
    
    
    # # Container access token
    # def create_container_access_token(self,
    #                                   secret_name: str,
    #                                   encoded_secret: str):
    #     """
    #     Create container access token
        
    #     Args:
    #         - secret_name: name of the secret
    #         - encoded_secret: base64 encoded string of the docker config file
    #     """
    #     docker_config_jetson={
    #         '.dockerconfigjson': encoded_secret
    #     }
    #     return self.create_container_access_token(secret_name, docker_config_jetson)



    # def check_cluster_status(self):
    #     success, msg=self.k8s_client.is_reachable()
    #     return success, msg
