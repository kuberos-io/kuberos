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

from pykuberos.scheduler.rosparameter import RosParamMapList

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


DEFAULT_JOB_CHECK_PERIOD = 2 # seconds
DEFAULT_JOB_CHECK_PERIOD_AT_RUNNING = 2 # seconds - reduce the check frequency

DEFAULT_BATCH_JOB_SCHEDULING_PERIOD = 3 # seconds




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


# Database operations
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
    
    queue_num = 0
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
            group_postfix = get_random_string(length=10, allowed_chars='abcdefghijklmnopqrstuvwxyz'),
            queue_number = queue_num,
            deployment = batch_job_deployment,
            deployment_manifest = job_dep_manifest,
            repeat_num = lifecycle_module.get('repeatNum', 1),
            lifecycle_rosmodule_name = lifecycle_module.get('rosModuleName', '')
        )
        
        queue_num += 1

    return True


# Database operations
# @transaction.atomic
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
                # deployment_manifest = batch_job_group.deployment_manifest,
                slug = f"{get_random_string(length=10, allowed_chars='abcdefghijklmnopqrstuvwxyz')}",
                startup_timeout = batch_job_group.deployment.startup_timeout,
                running_timeout = batch_job_group.deployment.running_timeout,
                volume = batch_job_group.deployment.volume_spec,
            )
            repeat_num -= 1
        except IntegrityError:
            continue


@shared_task()
def generate_job_queues(
    batch_job_dep_uuid: str) -> None:
    """
    Generate the batch job deployment unit.
    
    Combination of varyingParameter.

    """
    logger.debug("[Generate Job Queues] Start to generate job queues")
    
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
        
        # deploy configmaps
        response = kube_exec.deploy_configmaps(
            configmap_list=batch_job_group.get_configmaps()
        )
        
        if response['status'] == 'success':
            logger.debug("[Generate Job Queues] Reponse Configmaps: ", response['data'])

            # Create single jobs
            create_kuberos_jobs(batch_job_group=batch_job_group)

            # switch the status to EXECUTING
            batch_job_dep.switch_status_to_executing()
            
        else: 
            logger.error("[Generate Job Queues] Failed to create configmaps")
            logger.error(response['errors'])
            batch_job_dep.status = BatchJobDeployment.StatusChoices.FAILED
            batch_job_dep.save()
    
    # back to the workflow control
    batch_job_deployment_control.apply_async(args=(batch_job_dep_uuid,),
                                             countdown=0)


# Database operations
# @transaction.atomic
def update_scheduling_result(scheduled_jobs: list) -> None:
    """
    Update the scheduling result to the database.
    """
    for job in scheduled_jobs:
        
        job_obj = KuberosJob.objects.get(uuid=job['job_uuid'])
        job_obj.update_scheduled_result(sc_result=job)
    logger.debug("[Batch Job Scheduling] Updating results in DB is finished.")
        

# Change name to scheduling_batch_jobs
@shared_task()
def scheduling_batch_jobs(
    batch_job_dep_uuid: str) -> None:
    """
    Check the current status of the batch jobs. 
    
     - if there are pods in pending status, skip this itereation.
     
     - if all pods are in running status, schedule a new pod to this cluster.
    
    """
    
    batch_job_dep = BatchJobDeployment.objects.get(uuid=batch_job_dep_uuid)

    logger.debug("[Batch Job Scheduling] - Scheduling: %s ", batch_job_dep.name)
    
    # Scheduling new jobs:
    scheduled_clusters_name = []
    
    for job_group in batch_job_dep.batch_job_group_set.all():
        
        # check pending jobs
        # if no pending jobs, skip
        pending_num = job_group.get_pending_jobs_num()
        logger.debug("[Batch Job Scheduling] Job queue <%s> - pending jobs : %s",
                      job_group.group_postfix, pending_num)
        
        if pending_num == 0:
            logger.debug("[Batch Job Scheduling] Skip this job queue <%s>", 
                         job_group.group_postfix)
            continue
            
        exec_cluster = job_group.exec_cluster
        
        if exec_cluster.cluster_name in scheduled_clusters_name:
            logger.debug("[Batch Job Scheduling] This cluster <%s> is already scheduled", 
                         exec_cluster.cluster_name)
            continue
        
        scheduled_clusters_name.append(exec_cluster.cluster_name)
        
        # sync
        sync_kubernetes_cluster(cluster_config=exec_cluster.cluster_config_dict, 
                                get_usage=True,
                                get_pods=True,
                                record_usage=True)
        c_state = exec_cluster.get_cluster_state_for_batchjobs(
            use_robot=batch_job_dep.use_robot, 
            edge_resource_group=batch_job_dep.edge_resource_group,
            )
        numb_of_allocatable_nodes = c_state['num_of_allocatable_nodes']
        
        logger.debug("[Batch Job Scheduling] Exec cluster : %s", scheduled_clusters_name)
        logger.debug("[Batch Job Scheduling] num_of_allocatable_nodes: %s", 
                     numb_of_allocatable_nodes)
        # logger.debug("[Scheduling Batch Jobs] Cluster state: %s", c_state)

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
            job_workflow_control.delay(job_uuid=job['job_uuid'])

    # back to the workflow control
    batch_job_deployment_control.apply_async(args=(batch_job_dep_uuid,),
                                        countdown=DEFAULT_BATCH_JOB_SCHEDULING_PERIOD)
    
    logger.debug("[Batch Job Scheduling] This iteration finished.")

@shared_task()
def batch_job_cleaning(batch_job_dep_uuid: str) -> None:
    
    batch_job_dep = BatchJobDeployment.objects.get(uuid=batch_job_dep_uuid)

    logger.debug("[Batch Job Cleaning] Cleaning %s", batch_job_dep.name)
    
    cleaning_completed = True
    
    for job_group in batch_job_dep.batch_job_group_set.all():
        kube_exec = KuberosExecuter(kube_config=job_group.exec_cluster.cluster_config_dict)
        response = kube_exec.delete_deployed_configmaps(configmap_list=job_group.configmaps)
        
        # set cleaning_completed to False
        if not response['status'] == 'success':
            logger.error("[Batch Job Clearning] Failed to delete configmaps in queue <%s>", job_group.group_postfix)
            logger.error(response['errors'])
            job_group.add_error_msg(response['errors'])
            cleaning_completed = False
    
    # clean unfinished jobs
    unfinished_jobs = batch_job_dep.get_all_unfinished_jobs()
    logger.warning("[Batch Job Cleaning] Unfinished jobs: %s", unfinished_jobs)
    for job in unfinished_jobs:
        logger.warning("[Batch Job Cleaning] Terminating unfinished job <%s>", job.slug)
        single_job_terminating.apply_async(args=(job.uuid,))
        cleaning_completed = False
        
    # update batch job status
    if cleaning_completed:
        batch_job_dep.switch_status_to_completed()
        logger.debug("[Batch Job Cleaning] Cleaning success, switch to completed")
        batch_job_deployment_control.apply_async(args=(batch_job_dep_uuid,))
        
    else:
        logger.warning("[Batch Job Cleaning] Not finished, check again in %s secs", 3)
        # back to workflow control
        batch_job_deployment_control.apply_async(args=(batch_job_dep_uuid,),
                                                countdown=3)

    
@shared_task()
def batch_job_deployment_control(batch_job_dep_uuid: str) -> None:
    """
    High level controller to control the entire workflow of batch job deployment.
    Trigger the new scheduling process if there are pending jobs.
    """

    batch_job_dep = BatchJobDeployment.objects.get(uuid=batch_job_dep_uuid)
    status = batch_job_dep.status
    
    logger.debug("[Batch Job Deployment] Workflow - State: %s", status)
    
    # if in pending status, trigger the job units generation.
    if status == BatchJobDeployment.StatusChoices.PENDING:
        generate_job_queues.delay(batch_job_dep_uuid=batch_job_dep_uuid)
    
    # if the preprocessing is not finished, return failure.
    if status == BatchJobDeployment.StatusChoices.EXECUTING:
        # check job status
        batch_jobs_statistic = batch_job_dep.get_job_statistics()
        
        num_pending = batch_jobs_statistic['num_pending']
        
        if num_pending == 0:
            logger.debug("[Scheduling Batch Jobs] No pending jobs, switch to wait for finishing")
            batch_job_dep.switch_status_to_waiting_for_finishing()
            # Check the batch job deployment state in 5 seconds
            batch_job_deployment_control.apply_async(args=(batch_job_dep_uuid,),
                                                     countdown=5)
        else:
            logger.info("[Batch Job Deployment] Pending: %s, In Processing: %s -> Schedule new jobs", 
                    num_pending,
                    batch_jobs_statistic['num_processing'])
            scheduling_batch_jobs.delay(batch_job_dep_uuid=batch_job_dep_uuid)
    
    if status == BatchJobDeployment.StatusChoices.WAITING_FOR_FINISHING:
        
        batch_jobs_statistic = batch_job_dep.get_job_statistics()
        
        num_processing = batch_jobs_statistic['num_processing']
        
        if num_processing == 0:
            logger.info("[Batch Job Deployment] All jobs are finished, switch to cleaning")
            batch_job_dep.switch_status_to_cleaning()
            
            
        if batch_job_dep.chech_timeout_waiting_for_finishing():
            logger.info("[Batch Job Deployment] Timeout waiting for finishing, force switch to cleaning")
            batch_job_dep.switch_status_to_cleaning()

        batch_job_deployment_control.apply_async(args=(batch_job_dep_uuid,),
                                                 countdown=5)
        
    # DEPRECATED
    if status == BatchJobDeployment.StatusChoices.FINISHED:
        # trigger the cleaning process
        logger.info("[Batch Job Deployment] Cleaning deployed resources")
        batch_job_cleaning.delay(batch_job_dep_uuid=batch_job_dep_uuid)

    if status == BatchJobDeployment.StatusChoices.STOPPED:
        logger.warning("[Batch Job Deployment] Received stop signal, stop scheduling new jobs")
    
    if status == BatchJobDeployment.StatusChoices.CLEANING:
        # check the cleaning status
        logger.info("[Batch Job Deployment] Cleaning deployed resources")
        batch_job_cleaning.delay(batch_job_dep_uuid=batch_job_dep_uuid)

    # Completed
    if status == BatchJobDeployment.StatusChoices.COMPLETED:
        logger.info("[Batch Job Deployment] Batchjob completed.")


@shared_task()
def single_job_preparing(job_uuid: str) -> None:
    """
    Deploy configmap, dds, volume for the single job.
    """
    job = KuberosJob.objects.get(uuid=job_uuid)
    
    logger.debug("[Job Preparing] - %s", job.slug)
    
    kube_config = job.batch_job_group.exec_cluster.cluster_config_dict
    kube_exec = KuberosExecuter(kube_config=kube_config)
    
    discovery_server = job.scheduled_disc_server
    
    response = kube_exec.deploy_disc_server(
        disc_server_list=[discovery_server]
    )
    
    if response['status'] == 'success':
        logger.debug("[Job Preparing] Waiting for the dds discovery server to be ready")
        job.job_status = KuberosJob.StatusChoices.PREPARING
        job.save()

    else:
        logger.error("[Job Preparing] Failed to deploy the dds discovery server")
        logger.error(response['errors'])
        job.add_error_msg(response['errors'])
        job.job_status = KuberosJob.StatusChoices.FAILED
        job.save()
    
    # back to the workflow control
    job_workflow_control.apply_async(args=(job_uuid,), 
                                     countdown=DEFAULT_JOB_CHECK_PERIOD)


@shared_task()
def single_job_deploying_rosmodules(job_uuid: str) -> None:
    """
    Deploy the rosmodules for the single job.
    """
    
    job = KuberosJob.objects.get(uuid=job_uuid)
    
    logger.debug("[Job Deploying] - %s", job.slug)
    
    kube_config = job.batch_job_group.exec_cluster.cluster_config_dict
    kube_exec = KuberosExecuter(kube_config=kube_config)
    
    pod_list = job.scheduled_rosmodules

    response = kube_exec.deploy_rosmodules(
        pod_list = pod_list,
    )

    # update status
    if response['status'] == 'success':
        logger.debug("[Job Deploying] ROS modules deployed")
        job.switch_status_to_deploying()

    else:
        logger.error("[Job Deploying] Failed to deploy ROS modules")
        logger.error(response['errors'])
        job.add_error_msg(response['errors'])
        job.job_status = KuberosJob.StatusChoices.FAILED

    job.save()

    # back to the workflow control
    job_workflow_control.apply_async(args=(job_uuid,),
                                     countdown=2)

    

@shared_task()
def check_single_job_status(job_uuid: str) -> None:
    """
    Check each single job status.
    """
    job = KuberosJob.objects.get(uuid=job_uuid)
    
    # logger.debug("[Single Job] Check - %s", job.slug)
    # logger.debug("[Job Status ] - %s - %s", job.slug, job.job_status)
    
    kube_config = job.batch_job_group.exec_cluster.cluster_config_dict
    kube_exec = KuberosExecuter(kube_config=kube_config)
    
    pod_list = job.pod_status
    svc_list = job.svc_status
    pod_res = kube_exec.check_deployed_pod_status(pod_list)
    pod_status = pod_res['data']
    svc_res = kube_exec.check_deployed_svc_status(svc_list)
    svc_status = svc_res['data']
    
    
    job.update_pod_status(pod_status=pod_status,
                          svc_status=svc_status)
    
    # back to the workflow control
    job_workflow_control.apply_async(args=(job_uuid,),
                                     countdown=DEFAULT_JOB_CHECK_PERIOD)


@shared_task()
def single_job_terminating(job_uuid: str) -> None:
    """
    Terminate the single job.
    [Optional] Write metadata to the volume.
    """
    job = KuberosJob.objects.get(uuid=job_uuid)
    
    logger.debug("[Job Terminating] - Terminating <%s>", job.slug)
    
    kube_config = job.batch_job_group.exec_cluster.cluster_config_dict
    kube_exec = KuberosExecuter(kube_config=kube_config)

    pod_list = job.get_all_deployed_pods()
    svc_list = job.get_all_deployed_svcs()

    
    
    # write metadata into the volume
    mount_path = job.get_mount_path()
    data = []
    # configmap
    configmap = job.get_configmaps_for_logging(pretty_dict=True)
    data.append({
        'dst_path': f"{mount_path}/configmap.yaml",
        'content': [configmap]
    })
    
    # logs
    logs = job.get_logs(pretty_dict=True)
    data.append({
        'dst_path': f"{mount_path}/kuberos_job.log",
        'content': [logs]
    })

    # logger.debug("x"*50)
    logger.debug("[Job Termination]Writing metadata to the pod")
    
    # check discovery pod status: if not running, skip
    discovery_server_pod_name = job.discovery_server_pod_name
    if discovery_server_pod_name is None:
        logger.error("[Writing File] Discovery server pod name is None, scheduling failed")
    else:
        kube_exec.write_file_to_pod(
            pod_name=job.discovery_server_pod_name,
            data=data
        )
    # logger.debug("x"*50)
    

    # Delete the rosmodules 
    response = kube_exec.delete_rosmodules(
        pod_list=pod_list,
        svc_list=svc_list
    )

    if response['status'] == 'success':
        logger.debug("[Job Terminating] ROS modules deleted")
        job.job_status = KuberosJob.StatusChoices.TERMINATING
        job.save()

    else:
        logger.error("[Job Terminating] Failed to delete ROS modules")
        logger.error(response['errors'])
        job.add_error_msg(response['errors'])
        job.job_status = KuberosJob.StatusChoices.FAILED
        job.save()
    
    # back to the workflow control
    job_workflow_control.apply_async(args=(job_uuid,),
                                     countdown=DEFAULT_JOB_CHECK_PERIOD)


@shared_task()
def force_job_terminating(job_uuid: str) -> None:
    """
    Terminate the single job.
    """
    job = KuberosJob.objects.get(uuid=job_uuid)
    
    logger.debug("[Job Termintating] - Terminating <%s>", job.slug)
    
    kube_config = job.batch_job_group.exec_cluster.cluster_config_dict
    kube_exec = KuberosExecuter(kube_config=kube_config)
    
    pod_list = job.get_all_deployed_pods()
    svc_list = job.get_all_deployed_svcs()
    
    response = kube_exec.delete_rosmodules(
        pod_list=pod_list,
        svc_list=svc_list
    )

    if response['status'] == 'success':
        logger.debug("[Job Termintating] ROS modules deleted")
        job.job_status = KuberosJob.StatusChoices.TERMINATING
        job.save()

    else:
        logger.error("[Job Termintating] Failed to delete ROS modules")
        logger.error(response['errors'])
        job.add_error_msg(response['errors'])
        job.job_status = KuberosJob.StatusChoices.FAILED
        job.save()
    
    # back to the workflow control
    job_workflow_control.apply_async(args=(job_uuid,),
                                     countdown=DEFAULT_JOB_CHECK_PERIOD)


@shared_task()
def job_workflow_control(job_uuid: str) -> None:
    """
    Control the workflow of a single job.
    """
    
    job = KuberosJob.objects.get(uuid=job_uuid)
    
    logger.debug("[Job Workflow Control] Job <%s> status: %s", job.slug, job.job_status)
    
    if job.job_status == KuberosJob.StatusChoices.SCHEDULED:
        single_job_preparing.delay(job_uuid=job_uuid)
    
    elif job.job_status == KuberosJob.StatusChoices.PREPARED:
        single_job_deploying_rosmodules.delay(job_uuid=job_uuid)
    
    
    elif job.job_status in [KuberosJob.StatusChoices.PREPARING, 
                        KuberosJob.StatusChoices.DEPLOYING,
                        KuberosJob.StatusChoices.TERMINATING]:
        check_single_job_status.apply_async(args=(job_uuid,),
                                     countdown=DEFAULT_JOB_CHECK_PERIOD)
        
    elif job.job_status == KuberosJob.StatusChoices.RUNNING:
        check_single_job_status.apply_async(args=(job_uuid,),
                                            countdown=DEFAULT_JOB_CHECK_PERIOD_AT_RUNNING)
    
    elif job.job_status == KuberosJob.StatusChoices.FINISHED:
        single_job_terminating.apply_async(args=(job_uuid,),
                                     countdown=0)
    
    elif job.job_status in [KuberosJob.StatusChoices.COMPLETED, 
                        KuberosJob.StatusChoices.FAILED]:
        logger.info("[Job Workflow Control] Job <%s> is terminated with status: %s", 
                    job_uuid, job.job_status)

    else:
        logger.warning("[Job Workflow Control] Job <%s> is in unknown status: %s")



# Job_watch_dog
