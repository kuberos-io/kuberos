# Python 
import logging
import copy
import itertools

# Django 
from django.db import transaction
from django.utils.crypto import get_random_string
from django.db.utils import IntegrityError

# Celery
from celery import shared_task

# Pykuberos 
from pykuberos.kuberos_executer import KuberosExecuter
from pykuberos.scheduler.job_scheduler import JobScheduler

from pykuberos.scheduler.rosparameter import RosParameter, RosParamMap, RosParamMapList

from main.models import (
    BatchJobDeployment,
    BatchJobGroup,
    KuberosJob
)

from main.tasks.cluster_operating import (
    sync_kubernetes_cluster
)

logger = logging.getLogger('kuberos.main.tasks')
logger.propagate = False


def replace_rosparam(dep_manifest: str,
                     rosparam_map_name: str,
                     param_name: str,
                     value: str):
    replaced = dep_manifest
    for rosparam_map in replaced['rosParamMap']:
        if rosparam_map['name'] == rosparam_map_name:
            if rosparam_map['type'] == 'key-value':
                rosparam_map['data'][param_name] = value   
    return replaced



def create_job_groups(
    batch_job_deployment: BatchJobDeployment):
    """
    Create job queues for the batch job deployment.
    
    Each parameter combination is a job group/queue. 
    
    Each queue is executed on a single cluster.
    """
    
    exec_cluster_list = batch_job_deployment.exec_clusters.all()
    
    dep_manifest = batch_job_deployment.deployment_manifest
    job_spec = dep_manifest.get('jobSpec', None)
    
    varying_param_list = job_spec.get('varyingParameters', None)
    lifecycle_module = job_spec.get('lifecycleModule', None)

    # create all combinations of the varying parameters
    # each combination is enqueued as a job group
    value_list = [[*item['valueList']] for item in varying_param_list]
    all_combinations = list(itertools.product(*value_list))
    
    for combi in all_combinations:
        
        job_dep_manifest = copy.deepcopy(dep_manifest)
        for idx, value in enumerate(combi):
            vary_param = varying_param_list[idx]
            job_dep_manifest = replace_rosparam(
                dep_manifest=dep_manifest,
                rosparam_map_name=vary_param['toRosParamMap'],
                param_name=vary_param['paramName'],
                value=value
            )

        BatchJobGroup.objects.create(
            exec_cluster = exec_cluster_list[0],
            group_postfix = get_random_string(length=8, allowed_chars='abcdefghijklmnopqrstuvwxyz0123456789'),
            deployment = batch_job_deployment,
            deployment_manifest = job_dep_manifest,
            repeat_num = lifecycle_module.get('repeatNum', 1),
            lifecycle_rosmodule_name = lifecycle_module.get('rosModuleName', '')
        )

    return True
    

@transaction.atomic
def create_kuberos_jobs(
    batch_job_group: BatchJobGroup
):
    """
    Create single jobs for every job group.
    """
    repeat_num = batch_job_group.repeat_num
    
    while repeat_num > 0:
        try:
            KuberosJob.objects.create(
                batch_job_group = batch_job_group,
                deployment_manifest = batch_job_group.deployment_manifest,
                slug = f"{get_random_string(length=10, allowed_chars='abcdefghijklmnopqrstuvwxyz0123456789')}"
            )
            repeat_num -= 1
        except IntegrityError:
            continue


@shared_task()
def generate_job_queues(
    batch_job_dep_uuid: str) -> None:
    """
    Generate the batch job deployment unit.
    
    Combination of varyingParameter and repeatModule. 

    """
    logger.debug("[Batch Job] Generate job units")
    
    batch_job_dep = BatchJobDeployment.objects.get(uuid=batch_job_dep_uuid)
    
    # Create job groups and create configmaps with group postfix
    create_job_groups(batch_job_deployment=batch_job_dep)

    for batch_job_group in batch_job_dep.batch_job_group_set.all():

        kube_exec = KuberosExecuter(kube_config=batch_job_group.exec_cluster.cluster_config_dict)        
        
        ros_param_maps=RosParamMapList(batch_job_group.get_ros_param_maps())
        
        configmap_list = ros_param_maps.get_all_configmaps_for_deployment()
        # add group postfix
        for configmap in configmap_list:
            configmap['name'] = f"{batch_job_group.group_postfix}-{configmap['name']}"
        
        batch_job_group.configmaps = configmap_list
        batch_job_group.save()
        
        response = kube_exec.deploy_configmaps(
            configmap_list=batch_job_group.get_configmaps()
        )
        
        # Create single jobs
        create_kuberos_jobs(batch_job_group=batch_job_group)
        
    # switch the status to EXECUTING
    batch_job_dep.status = BatchJobDeployment.StatusChoices.EXECUTING
    batch_job_dep.save()
    
    # trigger check the whole process.
    batch_job_deployment_controller.delay(batch_job_dep_uuid=batch_job_dep_uuid)



@shared_task()
def processing_batch_jobs(
    batch_job_dep_uuid: str) -> None:
    """
    Check the current status of the batch jobs. 
    
     - if there are pods in pending status, skip this itereation.
     
     - if all pods are in running status, schedule a new pod to this cluster.
    
    """
    
    batch_job_dep = BatchJobDeployment.objects.get(uuid=batch_job_dep_uuid)
    
    exec_cluser_list = batch_job_dep.exec_clusters.all()
    
    # Scheduling new jobs:
    scheduled_clusters_name = []
    for job_group in batch_job_dep.batch_job_group_set.all():
        exec_cluster = job_group.exec_cluster
        if exec_cluster.cluster_name in scheduled_clusters_name:
            continue
        
        scheduled_clusters_name.append(exec_cluster.cluster_name)
        print("Exec cluster list: ", scheduled_clusters_name)
        
        # sync
        sync_kubernetes_cluster(cluster_config=exec_cluster.cluster_config_dict, 
                                get_usage=True,
                                get_pods=True)
        
        c_state = exec_cluster.get_cluster_state_for_batchjobs()
        
        numb_of_allocatable_nodes = c_state['num_of_allocatable_nodes']
        
        next_jobs = job_group.get_next_jobs(num=numb_of_allocatable_nodes)
        
        scheduler = JobScheduler(
            next_job_list=next_jobs,
            deployment_manifest=job_group.deployment_manifest,
            cluster_state=c_state
        )
        
        scheduled_jobs = scheduler.schedule()
        
        update_scheduling_result(scheduled_jobs=scheduled_jobs)
        
        # trigger single job workflow control 
        for job in scheduled_jobs:
            single_job_workflow_control.delay(job_uuid=job['job_uuid'])
        


@transaction.atomic
def update_scheduling_result(scheduled_jobs: list) -> None:
    """
    Update the scheduling result to the database.
    """
    for job in scheduled_jobs:
        job_obj = KuberosJob.objects.get(uuid=job['job_uuid'])
        job_obj.update_scheduled_result(sc_result=job)


@shared_task()
def single_job_preparing(job_uuid: str) -> None:
    """
    Deploy configmap, dds, volume for the single job.
    """
    job = KuberosJob.objects.get(uuid=job_uuid)
    
    logger.debug("[Single Job] Preparing - %s", job.slug)
    
    kube_config = job.batch_job_group.exec_cluster.cluster_config_dict
    kube_exec = KuberosExecuter(kube_config=kube_config)
    
    discovery_server = job.scheduled_disc_server
    
    response = kube_exec.deploy_disc_server(
        disc_server_list=[discovery_server]
    )
    
    if response['status'] == 'success':
        logger.debug("[Single Job Preparing] Waiting for the dds discovery server to be ready")
        job.job_status = KuberosJob.StatusChoices.PREPARING
        
    else:
        logger.error("[Single Job Preparing] Failed to deploy the dds discovery server")
        logger.error(response['errors'])
        job.job_status = KuberosJob.StatusChoices.FAILED
    
    job.save()
    
    # check is again in 2 sec.
    check_single_job_status.apply_async(args=(job_uuid,),
                                            countdown=2)

@shared_task()
def single_job_deploying_rosmodules(job_uuid: str) -> None:
    """
    Deploy the rosmodules for the single job.
    """
    
    job = KuberosJob.objects.get(uuid=job_uuid)
    
    logger.debug("[Single Job] Deploying - %s", job.slug)
    
    kube_config = job.batch_job_group.exec_cluster.cluster_config_dict
    kube_exec = KuberosExecuter(kube_config=kube_config)
    
    pod_list = job.scheduled_rosmodules

    response = kube_exec.deploy_rosmodules(
        pod_list = pod_list,
    )
    
    # update status
    if response['status'] == 'success':
        logger.debug("ROS modules deployed")
        job.job_status = KuberosJob.StatusChoices.DEPLOYING
        
        print("DDDDDD" * 10)
        print("CHECK , JOB STATUS: ", job.job_status)
    
        job.save()
    else:
        logger.error("Failed to deploy ROS modules")
        logger.error(response['errors'])
        job.job_status = KuberosJob.StatusChoices.FAILED

    job.save()

    # check
    check_single_job_status.apply_async(args=(job_uuid,),
                                            countdown=4)
    

@shared_task()
def check_single_job_status(job_uuid: str) -> None:
    """
    Check each single job status.
    """
    job = KuberosJob.objects.get(uuid=job_uuid)
    
    logger.debug("[Single Job] Check - %s", job.slug)
    logger.debug("[Job Status ] - %s - %s", job.slug, job.job_status)
    
    kube_config = job.batch_job_group.exec_cluster.cluster_config_dict
    kube_exec = KuberosExecuter(kube_config=kube_config)
    
    pod_list = job.pod_status
    svc_list = job.svc_status
    pod_res = kube_exec.check_deployed_pod_status(pod_list)
    pod_status = pod_res['data']
    svc_res = kube_exec.check_deployed_svc_status(svc_list)
    svc_status = svc_res['data']
    
    
    next_action = job.update_pod_status(pod_status=pod_status,
                          svc_status=svc_status)
    if next_action == 'next':
        single_job_workflow_control.apply_async(args=(job_uuid,),)
    else:
        check_single_job_status.apply_async(args=(job_uuid,),
                                            countdown=4)


@shared_task()
def clean_single_job(job_uuid: str) -> None:
    """
    Delete the single job.
    """
    job = KuberosJob.objects.get(uuid=job_uuid)
    
    logger.debug("[Single Job] Cleaning - %s", job.slug)
    
    kube_config = job.batch_job_group.exec_cluster.cluster_config_dict
    kube_exec = KuberosExecuter(kube_config=kube_config)
    
    pod_list = job.get_all_deployed_pods()
    svc_list = job.get_all_deployed_svcs()
    
    response = kube_exec.delete_rosmodules(
        pod_list=pod_list,
        svc_list=svc_list
    )

    if response['status'] == 'success':
        logger.debug("ROS modules deleted")
        job.job_status = KuberosJob.StatusChoices.CLEANING

    else:
        logger.error("Failed to delete ROS modules")
        logger.error(response['errors'])
        job.job_status = KuberosJob.StatusChoices.FAILED
        
    # switch status to CLEANING
    job.job_status = KuberosJob.StatusChoices.CLEANING
    job.save()



@shared_task()
def single_job_workflow_control(job_uuid: str) -> None:
    """
    Control the workflow of a single job.
    """
    
    job = KuberosJob.objects.get(uuid=job_uuid)
    
    logger.debug("[Single Job] Workflow control %s", job.slug)
    
    if job.job_status == KuberosJob.StatusChoices.SCHEDULED:
        single_job_preparing.delay(job_uuid=job_uuid)
    
    elif job.job_status == KuberosJob.StatusChoices.PREPARED:
        single_job_deploying_rosmodules.delay(job_uuid=job_uuid)
    
    elif job.job_status == KuberosJob.StatusChoices.SUCCEED:
        clean_single_job.delay(job_uuid=job_uuid)
    
    elif job.job_status in [KuberosJob.StatusChoices.PREPARING, 
                        KuberosJob.StatusChoices.DEPLOYING,
                        KuberosJob.StatusChoices.CLEANING]:
        check_single_job_status.delay(job_uuid=job_uuid)
        
    elif job.job_status == KuberosJob.StatusChoices.RUNNING:
        check_single_job_status.apply_async(args=(job_uuid,),
                                            countdown=4)
    
    elif job.job_status in [KuberosJob.StatusChoices.FAILED, 
                        KuberosJob.StatusChoices.CLEANED]:
        logger.info("[Single Job] Job %s is in %s status, skip", job_uuid, job.job_status)

    elif job.job_status == KuberosJob.StatusChoices.SUCCEED:
        logger.info("[Single Job] Job %s is in %s status, cleaning", job_uuid, job.job_status)
        clean_single_job(job_uuid=job_uuid)
        
    
@shared_task()
def batch_job_deployment_controller(
    batch_job_dep_uuid: str) -> None:
    """
    High level controller to control the entire workflow of batch job deployment.
    """
    logger.debug("[Batch Job Deployment] Processing batch jobs")
    
    batch_job_dep = BatchJobDeployment.objects.get(uuid=batch_job_dep_uuid)
    
    status = batch_job_dep.status
    
    # if in pending status, trigger the job units generation.
    if status == BatchJobDeployment.StatusChoices.PENDING:
        generate_job_queues.delay(batch_job_dep_uuid=batch_job_dep_uuid)
    
    # if the preprocessing is not finished, return failure.
    if status == BatchJobDeployment.StatusChoices.EXECUTING:
        processing_batch_jobs.delay(batch_job_dep_uuid=batch_job_dep_uuid)
    
