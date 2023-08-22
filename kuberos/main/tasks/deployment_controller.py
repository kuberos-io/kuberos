# Python 
import logging

# Celery
from celery import shared_task

# Kuberos 
from pykuberos.kuberos_executer import KuberosExecuter

from main.models import (
    Deployment,
    DeploymentEvent, 
    DeploymentJob,
)


logger = logging.getLogger('kuberos.main.tasks')
logger.propagate = False


STATUS_CHECK_INTERVAL = 3 # seconds


@shared_task()
def check_deployment_job_status(
    kube_config: dict,
    dep_job_uuid: str,
):
    """
    Check the deployment job status
    """
    logger.debug("Checking pod status")
    
    kube_exec = KuberosExecuter(kube_config=kube_config)
    
    # get pod and svc list
    dep_job = DeploymentJob.objects.get(uuid=dep_job_uuid)
    pod_list = dep_job.get_pod_list()
    svc_list = dep_job.get_svc_name_list()
    
    # check status
    pod_res = kube_exec.check_deployed_pod_status(pod_list)
    pod_status = pod_res['data']
    svc_res = kube_exec.check_deployed_svc_status(svc_list)
    svc_status = svc_res['data']
    # print("Pod status: ", pod_status)
    # print("Svc status: ", svc_status)
    
    next_action = dep_job.update_pod_status(pod_status, svc_status)

    # if status_changed: trigger the deployment_job_processing task 
    if next_action == 'next':
        logger.debug("Status changed, trigger the processing_deployment_job task")
        processing_deployment_job.apply_async(([dep_job_uuid]))
        return True
    elif next_action == 'check':
        logger.debug("Status not changed, wait for the next check")
        
        check_deployment_job_status.apply_async(
                args = (kube_config, dep_job_uuid),
                countdown=STATUS_CHECK_INTERVAL, 
                # retry=True,
                # retry_policy={
                #     'max_retries': 3,
                    # 'autoretry_for': (Exception,),
                # }
            )
        # raise Exception("Status not changed, wait for the next check")
    

### DISCOVERY SERVER ###
@shared_task()
def deploy_discovery_server(kube_config: dict, 
                            discovery_server_list: list,
                            job_uuid: str) -> None:
    """
    Call KubeROSExecutor to deploy the discovery server pod and service 
     - kube_config: dict,
     - discovery_server_list: list of {'pod': disc_pod_name, 'svc': disc_svc_name},
    """
    logger.debug("Deploying discovery server")
    
    kuberos_exec = KuberosExecuter(kube_config=kube_config)
    response = kuberos_exec.deploy_disc_server(
        disc_server_list = discovery_server_list)
    
    if response['status'] == 'success':
        logger.debug("Waiting for the dds discovery server to be ready")
    else:
        logger.error("Failed to deploy the dds discovery server")
        logger.error(response['errors'])


### ROSMODULES ###
@shared_task()
def deploy_rosmodules(kube_config: dict,
                      pod_list: list) -> dict:
    """
    Deploy the rosmodules
    """
    logger.debug("Deploying ROS modules")

    kube_exec = KuberosExecuter(kube_config=kube_config)
    response = kube_exec.deploy_rosmodules(
        pod_list = pod_list,
    )
    
    if response['status'] == 'success':
        logger.debug("ROS modules deployed")
    else:
        logger.error("Failed to deploy ROS modules")
        logger.error(response['errors'])
        

@shared_task()
def delete_deployed_modules(kube_config: dict,
                            pod_list: list, 
                            svc_list: list = []):
    """
    Delete deployed rosmodules
    """
    logger.debug("Deleting ROS modules")
    
    #runner = KuberosRunner(k8s_config=kube_config)    
    kube_exec = KuberosExecuter(kube_config=kube_config)
    
    response = kube_exec.delete_rosmodules(
        pod_list=pod_list,
        svc_list=svc_list
    )
    if response['status'] == 'success':
        logger.debug("ROS modules deleted")
    else:
        logger.error("Failed to delete ROS modules")
        logger.error(response['errors'])



### CONFIGMAPS ###
@shared_task()
def prepare_deployment_env(kube_config: dict, 
                           configmap_list: list, 
                           dep_uuid: str) -> dict: 
    """
    Prepare the deployment: 
        - create configmaps
    """

    logger.debug("Preparing deployment env: creating configmaps")
    
    kube_exec = KuberosExecuter(kube_config=kube_config)
    dep = Deployment.objects.get(uuid=dep_uuid)
    response = kube_exec.deploy_configmaps(
        configmap_list=configmap_list)
    
    if response['status'] == 'success':
        print("Reponse Configmaps: ", response['data'])
        dep.update_created_configmaps(response['data'])
        logger.debug("Configmaps created")
    else: 
        logger.error("Failed to create configmaps")
        logger.error(response['errors'])

    return response


@shared_task()
def delete_deployed_configmaps(kube_config: dict, 
                               configmap_list: list, 
                               dep_uuid: str):
    """
    Delete deployed configmaps
    """
    logger.debug("Deleting configmaps")
    
    kube_exec = KuberosExecuter(kube_config=kube_config)
    dep = Deployment.objects.get(uuid=dep_uuid)
    
    response = kube_exec.delete_deployed_configmaps(
        configmap_list = configmap_list
    )
    
    if response['status'] == 'success':
        dep.update_deleted_configmaps()
        logger.debug("Configmaps deleted")
    else:
        logger.error("Failed to delete configmaps")
        logger.error(response['errors'])
        
    return response


@shared_task(bind=True)
def processing_deployment_job(dep_job_uuid_list: list = None, 
                              *args, **kwargs):
    """
    Control the deployment workflow and trigger the subsequent tasks depending on the job status
    
    Args:
        - dep_job_uuid_list: list of deployment job uuids
    """
    
    print("I am listening to the deployment events")

    # get deployment jobs in progress
    if type(dep_job_uuid_list) == list and len(dep_job_uuid_list) > 0:
        # triggered by the subtasks
        job_in_progress = DeploymentJob.objects.filter(uuid__in=dep_job_uuid_list)
    else: 
        # triggered by the deployment controller
        deps_in_progress = Deployment.objects.filter(status__in=['deploying', 'deleting'])
        job_in_progress = []
        for dep in deps_in_progress:
            job_in_progress.extend(dep.deployment_job_set.all()) 
        
    # check the status of the deployment jobs and 
    # trigger subsequent tasks depending on the status
    for job in job_in_progress:
        
        print(job)
        
        # start pending job -> dispatch task to deploy discovery server
        if job.job_phase == 'pending':
            logger.info("Pending, start to deploy discovery server")
            deploy_discovery_server.delay(
                kube_config=dep.get_main_cluster_config(),
                discovery_server_list=job.get_disc_server(),
                job_uuid=job.get_uuid(),
            )
            # deploy_discovery_server.delay(job) Input argument mus be json serializable
            job.job_phase = 'disc_server_in_progress'
            job.save()

        # discovery server is ready -> dispatch task to deploy rosmodules
        elif job.job_phase == 'disc_server_success':
            logger.info("Discovery server is ready, start to deploy rosmodules")
            deploy_rosmodules.delay(
                kube_config=dep.get_main_cluster_config(),
                pod_list = job.get_all_rosmodules(),
            )
            job.job_phase = 'rosmodule_in_progress'
            job.save()
        
        # recevied request to delete the deployment -> dispatch task to delete rosmodules
        elif job.job_phase == 'request_for_delete':
            logger.info("Request for delete, start to delete rosmodules")
            delete_deployed_modules.delay(
                kube_config=dep.get_main_cluster_config(),
                pod_list = job.get_all_deployed_pods(),
                svc_list = job.get_all_deployed_svcs(),
            )
            job.job_phase = 'delete_in_progress'
            job.save()
        
        # check the deployment status 
        logger.info('Changed Job Phase: {}'.format(job.job_phase))
        if job.job_phase in ['disc_server_in_progress',
                             'daemonset_in_progress',
                             'rosmodule_in_progress',
                             'delete_in_progress']:
            
            logger.info("Dispatch the check_deployment_job_status task ")
            
            check_deployment_job_status.apply_async(
                args = (job.deployment.get_main_cluster_config(),
                        job.get_uuid()),
            )
            
        # check deployment job status, if last check time is more than 5 minutes
        time_since_last_check = job.since_last_check()
        if time_since_last_check > 600:
            logger.warning("Last check time: {} seconds ago".format(time_since_last_check))
            check_deployment_job_status.apply_async(
                args = (job.deployment.get_main_cluster_config(),str(job.uuid)),
            )

