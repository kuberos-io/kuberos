# Python 
import logging

# Celery
from celery import shared_task, Task, chain

# Kuberos 
from pykuberos.kuberos_runner import KuberosRunner
from main.tasks.base import KubeROSBaseTask
from main.models import (
    DeploymentEvent, 
    Deployment, 
    DeploymentJob
)


logger = logging.getLogger('kuberos.main.tasks')
logger.propagate = False


class DeployRosModuleBaseTask(Task):

    def on_success(self, retval, task_id, args, kwargs):
        # Write this operation to the deployment model
        # args: A tuple containing the original positional arguments passed to the task function. 
        
        # logger.critical("TASK_ID_CALLBACK: {}".format(task_id))
        dep_event = DeploymentEvent.objects.get(celery_task_id=task_id)
        dep_event.event_status = 'dispatched'
        dep_event.message = str(retval)
        dep_event.save()
        return super().on_success(retval, task_id, args, kwargs)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        # logger.critical("TASK_ID_CALLBACK: {}".format(task_id))
        dep_event = DeploymentEvent.objects.get(celery_task_id=task_id)
        dep_event.event_status = 'failed'
        dep_event.message = str(exc)
        dep_event.save()
        logger.error("Deployment <{}> failed".format(dep_event.deployment.name))
        logger.error("Exception: {}".format(exc))
        
        return super().on_failure(exc, task_id, args, kwargs, einfo)


@shared_task(base=DeployRosModuleBaseTask)
def deploy_ros_modules_to_robot(
    kube_config: dict,
    sc_result: dict, 
    deployment_event_uuid = None,
    wait_for_completion=True):
    """
    Call PyKubeROS to deploy ROS modules
    args:
        kube_config: dict - 
            - api server address, api server port
            - credentials to access the cluster
        
        wait_for_completion: bool 
            - True: wait for the deployment to be completed
    return: 
        response: dict - {'deployment_event_uuid': str,
             'ros_pods': [list of pod_name], 
             'namespace': str,
             'dds_server': [dds_server_name], 
             'dds_service': [dds_service_name]}
    """
    logger.debug("Deploying ROS modules")
    success = True
    
    runner = KuberosRunner(k8s_config=kube_config)
    
    # create dds discovery server and wait until it is ready.
    disc_server_list = sc_result['discovery']
    dds_res = {}
    if len(disc_server_list) > 0:
    
        dds_res = runner.deploy_disc_server(
            disc_server_list)
        logger.debug("Waiting for the dds discovery server to be ready")

    # deploy pods:     
    rosmodule_pod_list = sc_result['rosmodules']
    # create deployment request
    ros_pods =runner.deploy_ros_modules(
        pod_list = rosmodule_pod_list,
    )
    response = {'success': True, 
                'event_type': 'deploy',
                'deployment_event_uuid': deployment_event_uuid,
                'msg': 'Deployment request has been sent to the cluster'}
    response.update(dds_res)
    response.update(ros_pods)
    if success:
        return response
    else: 
        raise Exception("ROS2 Deployment failed")




@shared_task(base=DeployRosModuleBaseTask)
def deploy_ros_modules_2(
    kube_config: dict,
    kuberos_config: dict,
    # yaml_file_content: str,
    scheduled_deployment: dict, 
    pod_list_for_test: list,
    deployment_event_uuid = None,
    wait_for_completion=True):
    """
    Call PyKubeROS to deploy ROS modules
    args:
        kube_config: dict - 
            - api server address, api server port
            - credentials to access the cluster
        
        kuberos_config: dict 
            - image pull secret
            - discovery server (if existed)
        
        yaml_file_content: ATTENTION: 
        
        wait_for_completion: bool 
            - True: wait for the deployment to be completed
    return: 
        response: dict - {
            'ros_pods': list - list of ros pods
            'namespace': str - namespace of the deployment
            'dds_pods': list - list of dds pods
            'dds_services': list - list of dds services
        }
    """
    logger.debug("Deploying ROS modules")
    runner = KuberosRunner(k8s_config=kube_config)
    
    # get discovery server list 
    discovery_server_list = scheduled_deployment['discovery']
        
    # create dds discovery server
    dds_res = runner.create_dds_discovery_server(
        discovery_server_list)
    
    logger.debug("Waiting for the dds discovery server to be ready")
    
    success = True
    
    pod_list = pod_list_for_test
    
    # create deployment request
    ros_pods =runner.deploy_ros2_module_2(
        pod_list = pod_list,
    )
    response = {'success': True, 
                'event_type': 'deploy',
                'deployment_event_uuid': deployment_event_uuid,
                'msg': 'Deployment request has been sent to the cluster'}
    response.update(dds_res)
    response.update(ros_pods)
    if success:
        return response
    else: 
        raise Exception("ROS2 Deployment failed")


@shared_task()
def deploy_discovery_server(
    kube_config: dict, 
    discovery_server_list: list,
):
    runner = KuberosRunner(k8s_config=kube_config)
    
    # create dds discovery server and wait until it is ready.
    if len(discovery_server_list) > 0:
    
        dds_res = runner.deploy_disc_server(
            discovery_server_list, 
            wait_until_ready=False)
        logger.debug("Waiting for the dds discovery server to be ready")


@shared_task()
def check_discovery_server(
    kube_config: dict,
    discovery_server_list: list,
): 
    runner = KuberosRunner(k8s_config=kube_config)
    
    if len(discovery_server_list) > 0:
        dds_res = runner.check_disc_server_status(
            discovery_server_list)



@shared_task(base=DeployRosModuleBaseTask)
def delete_deployment(kube_config: dict,
                      deployment_yaml_content: str, 
                        delete_dds_server=False,
                        deployment_event_uuid = None,
                        wait_for_comleation=False):
    """
    Call PyKubeROS to delete ROS modules
    args: 
        modules: list - list of module names
    """
    logger.debug("Deleting ROS modules")
    runner = KuberosRunner(k8s_config=kube_config)
    result = runner.delete_ros2_module(
        deployment_yaml_content,
        is_path = False, 
        delete_dds_server=delete_dds_server, 
        wait_until_ready=wait_for_comleation
    )
    response = {
        'success': True,
        'event_type': 'delete',
        'deployment_event_uuid': deployment_event_uuid,
    }
    response.update(result)
    success = True
    if success:
        return response
    else:
        raise Exception("Error while calling K8s api server to delete deployment")


@shared_task(base=KubeROSBaseTask)
def update_ros_modules(modules, wait_for_completion=True):
    """
    Call PyKubeROS to update ROS modules
    """
    pass


class CheckDeploymentBaseTask(Task):

    def on_success(self, retval, task_id, args, kwargs):
        # Write this operation to the deployment model
        # args: A tuple containing the original positional arguments passed to the task function. 
        previous_task_return = args[0]
        dep_event = self.get_development_event(previous_task_return['deployment_event_uuid'])
        dep_event.event_status = 'success'
        dep_event.message = str(retval)
        dep_event.save()
        return super().on_success(retval, task_id, args, kwargs)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        previous_task_return = args[0]
        dep_event = self.get_development_event(previous_task_return['deployment_event_uuid'])
        dep_event.message = str(exc)
        dep_event.event_status = 'failed'
        dep_event.save()
        return super().on_failure(exc, task_id, args, kwargs, einfo)
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        print('Retrying...' * 3)
        
    @staticmethod
    def get_development_event(dep_event_uuid):
        try:
            dep_event = DeploymentEvent.objects.get(
                uuid=dep_event_uuid)
            return dep_event
        except DeploymentEvent.DoesNotExist:
            logger.fatal("FATAL Error: Deployment event does not exist")
            raise Exception("FATAL Error: Deployment event does not exist")    

@shared_task(bind=True, 
             autoretry_for=(Exception,),
             retry_backoff=False, 
             default_retry_delay=3, # repeat every 3 seconds 
             max_retries=10, 
             base=CheckDeploymentBaseTask)
def check_deployment_status(self, 
                            previous_task_return: dict):
    """
    Call PykubeROS to check deployment status
    args:
        previous_task_return: dict -
            {'deployment_event_uuid': str,
             'ros_pods': [list of pod_name], 
             'namespace': str,
             'dds_server': [dds_server_name], 
             'dds_service': [dds_service_name]}
    """
    logger.debug("Checking deployment status: {}".format(previous_task_return))
    dep_event = DeploymentEvent.objects.get(
                    uuid=previous_task_return['deployment_event_uuid'])
    # deployment_event_msg = dep_event.message
    runner = KuberosRunner(k8s_config=dep_event.deployment.fleet.k8s_main_cluster.cluster_config_dict)
    res = runner.check_deployment_status(previous_task_return)
    
    if res['is_completed']:
        logger.info("Deployment is completed")
        return res
    else:
        # Retry
        raise Exception("Retry checking deployment status")


