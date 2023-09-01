"""
KubeROS Batch Jobs processes the predefined non-permanent deployment. 
It mainly aims to evaluate and investigate the ROS2 software module with simulation at large scale. 
You can vary the algorithms, parameters in you entire software stack. 

No modification of the predefined ROSModue is required. 
What you need to do, is only add the `JobSpec` section into the deployment manifest. 

Example: 
    jobSpec:
    - name: batch-evaluation-nav2
        maxParallelism: 10
        maxRetry: 3
        timeout: 5m
        lifeCycleModule: task_controller
        
        varyingParameter:
        # KubeROS generates job set with all possible combinations of following parameters
        - toRosParamMap: nav2-launch-parameters
            keyName: slam_algorithms
            valueList: ['amcl', 'rtabmap']

        - toRosParamMap: nav2-launch-parameters
            keyName: map
            valueList: ['maze', 'aws-warehouse-1', 'lab-6-floor']

        repeatRosModule:
        - rosModuleName: task_controller
            repeatNum: 100
"""

# Python 
import uuid
import logging
import json

# Django 
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.timesince import timesince
from django.utils.crypto import get_random_string

# KubeROS 
from main.models.base import UserRelatedBaseModel
from main.models import Cluster


logger = logging.getLogger('kuberos.main.scheduler')
logger.propagate = False


class BatchJobDeployment(UserRelatedBaseModel):
    
    class StatusChoices(models.TextChoices):

        # Entire batch job deployment is in pending. Due to no cluster is free or available.
        PENDING = 'PENDING', _('pending')
        
        # Entire batch job deployment is in executing. This process may take a long time.
        EXECUTING = 'EXECUTING', _('Batch jobs in executing')
        
        # Wait for finishing the running jobs.
        WAITING_FOR_FINISHING = 'WAITING_FOR_FINISHING', _('Waiting for finishing the running jobs')
        
        # Stop the execution, instead of deleting the deployment.
        STOPPED = 'STOPPED', _('Batch jobs stopped')
        
        # Finished: All jobs are completed.
        FINISHED = 'FINISHED', _('Batch jobs finished')
        
        # Clearning the deployed global resources
        #  - configmaps per job queue
        #  - attached volumes.
        CLEANING = 'CLEANING', _('Cleaning global resources')
        
        # Terminating state
        # Completed, all jobs are completed or terminated if in failure.
        COMPLETED = 'COMPLETED', _('Entire deployment completed')
        # Failed. 
        # Possible reasons: Manifest is not correct, failure rate is too high.
        FAILED = 'FAILED', _('Batch jobs failed')

    name = models.CharField(
        max_length=128,
        null=False,
        blank=False,
    )
    
    subname = models.CharField(
        max_length=128,
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(
        default=True
    )
    
    status = models.CharField(
        max_length=32,
        choices=StatusChoices.choices,
        default=StatusChoices.PENDING
    )
    
    job_spec = models.JSONField(
        blank=False,
        null=False,
        verbose_name='Job Specification'
    )
    
    volume_spec = models.JSONField(
        blank=True,
        null=True,
    )
    
    deployment_manifest = models.JSONField(
        blank=False,
        null=False,
        verbose_name='Deployment Manifest'
    )
    
    custom_rosparam_yaml_files = models.JSONField(
        blank=True,
        null=True
    )
    
    startup_timeout = models.IntegerField(
        default = 60,
        verbose_name='Startup timeout, unit: sec'
    )
    
    running_timeout = models.IntegerField(
        default=180,
        verbose_name='Running timeout, unit: sec'
    )
    
    exec_clusters = models.ManyToManyField(
        Cluster, 
        blank=False,
        related_name='job_exec_cluster_set'
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True
    )
    
    completed_at = models.DateTimeField(
        null=True,
        blank=True
    )
    
    description = models.TextField(
        blank=True,
        null=True
    )
    
    scheduling_done_at = models.DateTimeField(
        blank=True,
        null=True,
    )
    
    logs = models.JSONField(
        blank=True,
        null=True,
        default=list,
    )
    
    
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['name', 'subname'],
                                    condition=models.Q(is_active=True), 
                                    name='unique_active_name_batch_job_deployment')
        ]
        ordering = ['-created_time', 'name']
    
    def get_all_running_jobs(self):
        
        running_jobs = []
        
        for job_group in self.batch_job_group_set.all():
            for job in job_group.batch_kuberos_job_set.all():
                if job.job_status == KuberosJob.StatusChoices.EXECUTING:
                    running_jobs.append(job)
        return running_jobs
    
    def get_next_jobs(self, num=1):
        """
        Get jobs to run.
        """
        jobs = []
        job_groups = self.batch_job_group_set.all()
        for group in job_groups:
            jobs_in_group = group.batch_kuberos_job_set.filter(
                job_status=KuberosJob.StatusChoices.PENDING)
            jobs.extend(jobs_in_group)
            if len(jobs) > num:
                jobs = jobs[:num]
                break
        
        jobs_manifest = [job.get_job_description_for_scheduling() for job in jobs]    
        
        return jobs_manifest
    
    def get_job_statistics(self):
        queues = [group.job_statistics for group in self.batch_job_group_set.all()]
        num_pending = 0
        num_processing = 0
        for queue in queues:
            num_pending += queue['pending']
            num_processing += queue['processing']
        return {
            'num_pending': num_pending,
            'num_processing': num_processing,
            'queues': queues
        }
    
    def get_all_unfinished_jobs(self):
        jobs = []
        for group in self.batch_job_group_set.all():
            jobs.extend(group.batch_kuberos_job_set.exclude(job_status=KuberosJob.StatusChoices.COMPLETED))
        return jobs
    
    def get_volume_spec(self):
        vol_spec = self.volume_spec
        try:
            vol_spec['type'] = self.job_spec['volume']['type']
            vol_spec['username'] = self.job_spec['volume']['username']
        except KeyError:
            logger.warning("KeyError by getting volume spec. %s", self.job_spec)
        return self.volume_spec


    def chech_timeout_waiting_for_finishing(self):
        """
        Check the timeout of the entire deployment.
        If timeout, switch to force cleaning.
        """
        if not self.scheduling_done_at:
            self.logs.append({'[Error]': f'[WAITING_FOR_FINISHING] Scheduling done time is not found. Set to now.'})
            self.scheduling_done_at = timezone.now()
            self.save()
            
        if self.status == self.StatusChoices.WAITING_FOR_FINISHING:
            if (timezone.now() - self.scheduling_done_at).seconds > self.running_timeout + self.startup_timeout:
                return True
        return False
    
    def get_all_configmaps(self):
        """
        Get all configmaps
        For cleaning the global resources
        """
        configmaps = []
        for group in self.batch_job_group_set.all():
            configmaps.extend(group.configmaps)
        return configmaps

    def switch_status_to_executing(self):
        self.status = BatchJobDeployment.StatusChoices.EXECUTING
        self.started_at = timezone.now()
        self.save()
        
    def switch_status_to_waiting_for_finishing(self):
        self.status = BatchJobDeployment.StatusChoices.WAITING_FOR_FINISHING
        self.scheduling_done_at = timezone.now()
        self.save()
    
    def switch_status_to_finished(self):
        """
        All jobs are completed.
        Next: clean the global resources
        """
        self.status = BatchJobDeployment.StatusChoices.FINISHED
        self.save()
    
    def switch_status_to_cleaning(self):
        self.status = BatchJobDeployment.StatusChoices.CLEANING
        self.save()
    
    def switch_status_to_stopped(self):
        self.status = BatchJobDeployment.StatusChoices.STOPPED
        self.save()
    
    def switch_status_back_to_executing(self):
        self.status = BatchJobDeployment.StatusChoices.EXECUTING
        self.save()
    
    def switch_status_to_completed(self):
        self.status = BatchJobDeployment.StatusChoices.COMPLETED
        self.completed_at = timezone.now()
        self.save()
        
        logger.debug("Batch job deployment completed in %s", (self.completed_at - self.started_at).seconds)

    @property
    def use_robot(self) -> bool:
        """
        Check whether using robots for batchjob execution.
        Default: False
        """
        use_robot = False
        metadata = self.deployment_manifest.get('metadata', None)
        
        if metadata:
            use_robot = metadata.get('useRobotResource', False)
        
        return use_robot
    
    @property
    def started_since(self):
        if not self.started_at:
            return 'N/A'
        if self.status == self.StatusChoices.COMPLETED:
            return 'Completed'
        return timesince(self.started_at)


    @property
    def execution_time(self):
        if not self.status == self.StatusChoices.COMPLETED:
            return 'Running'
        if (self.completed_at - self.started_at).seconds <= 600:
            return f'{(self.completed_at - self.started_at).seconds} secs'
        return timesince(self.started_at, self.completed_at)
        

class BatchJobGroup(models.Model):
    """
    Each batch job group is executed on a single cluster.
    
    """
    
    group_postfix = models.CharField(
        max_length=32,
        blank=True,
        null=True
    )
    
    queue_number = models.IntegerField(
        blank=True,
        null=True
    )
    
    uuid = models.UUIDField(
        primary_key=True,
        editable=False, 
        unique=True, 
        default=uuid.uuid4
    )
    
    deployment = models.ForeignKey(
        BatchJobDeployment,
        on_delete=models.CASCADE,
        related_name='batch_job_group_set'
    )
    
    exec_cluster = models.ForeignKey(
        Cluster,
        on_delete=models.CASCADE,
        related_name='batch_job_group_set',
        blank=True,
        null=True
    )

    deployment_manifest = models.JSONField(
        null=True,
        blank=True
    )
    
    configmaps = models.JSONField(
        null=True,
        blank=True,
        default=list
    )
    
    repeat_num = models.IntegerField(
        default=1
    )
    
    lifecycle_rosmodule_name = models.CharField(
        max_length=128,
        blank=True,
        null=True,        
    )
    
    logs = models.JSONField(
        blank=True,
        null=True,
        default=list,
    )


    def get_uuid(self) -> str:
        return str(self.uuid)
    
    def __str__(self) -> str:
        return f'{self.deployment.name}-{self.group_postfix}'
    

    def get_ros_param_maps(self) -> list:
        return self.deployment_manifest.get('rosParamMap', {})

    def get_configmaps(self) -> list:
        return self.configmaps
    
    def get_next_jobs(self, num=1):
        """
        Get pending jobs to be scheduled.
        """
        jobs = []

        jobs_in_pending = self.batch_kuberos_job_set.filter(
            job_status=KuberosJob.StatusChoices.PENDING)
        # jobs.extend(jobs_in_group)
        if len(jobs_in_pending) > num:
            jobs = jobs_in_pending[:num]
        else:
            jobs = jobs_in_pending

        jobs_manifest = [job.get_job_description_for_scheduling() for job in jobs]    

        return jobs_manifest

    def get_pending_jobs_num(self) -> int:
        return self.batch_kuberos_job_set.filter(job_status=KuberosJob.StatusChoices.PENDING).count()

    @property
    def job_statistics(self) -> dict:
        completed = self.batch_kuberos_job_set.filter(job_status=KuberosJob.StatusChoices.COMPLETED).count()
        pending = self.batch_kuberos_job_set.filter(job_status=KuberosJob.StatusChoices.PENDING).count()
        failed = self.batch_kuberos_job_set.filter(job_status=KuberosJob.StatusChoices.COMPLETED,
                                                   success_completed=False).count()
        processing = self.batch_kuberos_job_set.all().count() - completed - pending
        return {
            'queue_name': f'{self.group_postfix}',
            'exec_cluster': f'{self.exec_cluster.cluster_name}',
            'is_finished': True if processing == 0 else False,
            'completed': completed,
            'pending': pending,
            'failed': failed,
            'processing': processing,
        }



class KuberosJob(models.Model):
    
    class StatusChoices(models.TextChoices):
        
        # Job created, wait for scheduling to the cluster node
        PENDING = 'PENDING', _('pending')
        # Job is scheduled to the cluster node
        SCHEDULED = 'SCHEDULED', _('scheduled')
        # Deploying discovery server, presets
        PREPARING = 'PREPARING', _('preparing')
        # Environment is prepared, wait to deploy the rosmodules
        PREPARED = 'PREPARED', _('prepared') # Configmap, dds, volume.
        # Deploying rosmodules
        DEPLOYING = 'DEPLOYING', _('deploying')
        # Job is running
        RUNNING = 'RUNNING', _('running')
        # Lifecycle module is finished
        FINISHED = 'FINISHED', _('job finished')
        # Job is finished, deleting the resources
        TERMINATING = 'TERMINATING', _('in terminating')
        
        # Terminating state
        # Change to completed after all resources are deleted
        COMPLETED = 'COMPLETED', _('job execution completed')
        # Job failed
        FAILED = 'FAILED', _('job failed')


    uuid = models.UUIDField(
        primary_key=True,
        editable=False, 
        unique=True, 
        default=uuid.uuid4
    )
    
    slug = models.SlugField(
        max_length=64,
        default=f'{get_random_string(6)}-{get_random_string(6)}',
        unique=True
    )
    
    batch_job_group = models.ForeignKey(
        BatchJobGroup,
        on_delete=models.CASCADE,
        related_name='batch_kuberos_job_set'
    )
    
    job_status = models.CharField(
        max_length=32,
        choices=StatusChoices.choices,
        default=StatusChoices.PENDING
    )
    
    running_timeout = models.IntegerField(
        default=360,
    )
    
    startup_timeout = models.IntegerField(
        default=360,
    )
    
    # updated by job controller
    scheduled_disc_server = models.JSONField(
        null=True,
        blank=True,
        default=list, 
        verbose_name='discovery server'
    )
    
    # updated by job controller
    scheduled_rosmodules = models.JSONField(
        null=True,
        blank=True,
        default=list,
        verbose_name='scheduled rosmodules'
    )
    
    ### STATUS ###
    pod_status = models.JSONField(
        null=True,
        blank=True,
        default=list,
        verbose_name='Pod status'
    )
    
    svc_status = models.JSONField(
        null=True,
        blank=True,
        default=list,
        verbose_name='Service status'
    )
    
    # executed on which cluster node
    node_status = models.JSONField(
        null=True,
        blank=True,
        default=list,
    )
    
    # volume to be attached to the job
    # {   'name': 'volume-name',
    #       'mountPath': '/path/to/mount',
    #       'hostPath': 'sub/path/to/mount',
    # }
    volume = models.JSONField(
        null=True,
        blank=True,
        default=dict,
    )
    
    ### TIMESTAMP ###
    last_check_time = models.DateTimeField(
        default=timezone.now
    )

    scheduled_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    
    prepared_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Env prepared: discovery server, configmaps, volumes, util nodes are ready'
    )
    
    deployment_started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Deployment started at'
    )

    running_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Job running at'
    )
    
    finished_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Lifecycle probe module finished at'
    )
    
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Job completed, all resources are deleted'
    )
    
    ### MESSAGES ###
    success_completed = models.BooleanField(
        default=True
    )
    
    logs = models.JSONField(
        null=True,
        blank=True,
        default=list,
    )


    def get_uuid(self) -> str:
        return str(self.uuid)

    def update_scheduled_result(self, 
                                sc_result: dict) -> None:
        self.scheduled_disc_server = sc_result['disc_server']
        self.scheduled_configmaps = sc_result['configmaps']
        self.scheduled_volume = sc_result['volumes']
        self.scheduled_rosmodules = sc_result['rosmodules']
        self.scheduled_at = timezone.now()
        
        self.job_status = self.StatusChoices.SCHEDULED
        self.node_status = sc_result['cluster_node_info']
        
        self.logs.append({'Scheduling': f"[INFO] {self.scheduled_at} - Job scheduled to cluster node {sc_result['cluster_node_info']}"})
        
        self.save()
        
        # method copied, need to be refactored
        self.initialize()

    
    def get_job_description_for_scheduling(self) -> dict:
        res = {
            'job_uuid': self.get_uuid(),
            'group_postfix': self.batch_job_group.group_postfix,
            'job_postfix': self.slug,
            'manifest': self.batch_job_group.deployment_manifest,
            'volume': self.get_job_volume(),
        }
        return res

    def get_job_volume(self) -> dict:
        
        volume = self.volume
        if not volume:
            return {}

        if volume['type'] == 'nfs':
            if self.group_data_in_storage:
                volume['volume_mount']['subPath'] = f"{volume['volume_mount']['subPath']}/queue_{self.batch_job_group.queue_number}/job_{self.slug}"
            else:
                volume['volume_mount']['subPath'] = f"{volume['volume_mount']['subPath']}/job_{self.slug}"
        
        return volume
    
    def get_mount_path(self) -> str:
        if self.volume:
            return self.volume['volume_mount']['mountPath']
    
    def get_configmaps_for_logging(self, pretty_dict=True) -> list:
        
        configmaps = []
        for cm in self.batch_job_group.configmaps:
            name = cm['name']
            # remove the group postfix
            name = name.replace(f'{self.batch_job_group.group_postfix}-', '')
            configmaps.append({
                'name': name,
                'type': cm['type'],
                'data': cm['content']
            })
        if pretty_dict:
            configmaps = json.dumps(configmaps, indent=4, sort_keys=False)
        
        return configmaps
    
    def get_logs(self, pretty_dict=True) -> list:
        if not self.save_logs_in_volume:
            return 'Disabled'
        if pretty_dict:
            return json.dumps(self.logs, indent=4, sort_keys=False)
        return self.logs
    
    def initialize(self):
        """
        Initialize the job, set status as pending
        """
        pod_status_list = []
        svc_status_list = []
        
        # discovery server
        pod_status_list.append({
            'name': self.scheduled_disc_server['pod']['metadata']['name'],
            'pod_type': 'discovery_server', 
            'status': 'Pending'
        })

        svc_status_list.append({
            'name': self.scheduled_disc_server['svc']['metadata']['name'],
            'svc_type': 'discovery_server', 
            'status': 'Pending'
        })

        # rosmodule
        for module in self.scheduled_rosmodules:
            pod_status_list.append({
                'name': module['metadata']['name'],
                'pod_type': 'ros_module',
                'status': 'Pending'
            })

        self.pod_status = pod_status_list
        self.svc_status = svc_status_list
        self.save()
    
    
    def switch_status_to_deploying(self):
        self.deployment_started_at = timezone.now()
        self.job_status = self.StatusChoices.DEPLOYING
        self.save()
    
    def switch_status_to_prepared(self):
        self.prepared_at = timezone.now()
        self.job_status = self.StatusChoices.PREPARED
        self.save()
        
    def switch_status_to_running(self):
        self.running_at = timezone.now()
        self.job_status = self.StatusChoices.RUNNING
        self.save()
    
    def switch_status_to_finished(self):
        self.finished_at = timezone.now()
        self.job_status = self.StatusChoices.FINISHED
        self.save()

    def switch_status_to_completed(self):
        self.completed_at = timezone.now()
        self.job_status = self.StatusChoices.COMPLETED
        if self.completed_at and self.running_at:
            self.logs.append({'[INFO]': f'Job completed in {(self.completed_at-self.deployment_started_at).seconds} secs'})
        else:
            self.logs.append({'[Error]': f'Job completed, but no running time recorded: Started: {self.deployment_started_at}, Completed: {self.completed_at}'})
        self.save()
    
    def switch_status_to_failed(self, err_msg: str):
        self.success_completed = False
        
        # switch to state finished, which will trigger the termination of the job
        self.job_status = self.StatusChoices.FINISHED
        
        self.save()


    def update_pod_status(self,
                          pod_status: list,
                          svc_status: list = []) -> str:
        
        self.last_check_time = timezone.now()
        self.pod_status = pod_status
        self.svc_status = svc_status
        # self.logs.append({'POD Status': f'[INFO] {timezone.now()} - {pod_status}'})
        # self.logs.append({'SVC Status': f'[INFO] {timezone.now()} - {svc_status}'})
        self.save()
        
        action = 'next'
        
        # check startup timeout
        if self.job_status in [self.StatusChoices.PREPARING, 
                               self.StatusChoices.DEPLOYING]:
            if (timezone.now() - self.scheduled_at).seconds > self.startup_timeout:
                self.switch_status_to_failed(
                    err_msg=f'Job startup timeout: {self.startup_timeout} secs'
                )
                
        # check discovery server 
        if self.job_status == self.StatusChoices.PREPARING:
            if self.is_discovery_servers_ready():
                self.switch_status_to_prepared()
                
        # check rosmodules
        if self.job_status == self.StatusChoices.DEPLOYING:
            if self.is_all_rosmodules_ready():
                self.switch_status_to_running()

        # check lifcycle module
        if self.job_status == self.StatusChoices.RUNNING:

            # Running timeout
            if (timezone.now() - self.running_at).seconds > self.running_timeout:
                self.switch_status_to_failed(
                    err_msg=f'Job running timeout: {self.running_timeout} secs'
                )
                
            # Lifecycle module finished
            if self.is_lifecycle_module_completed():
                self.switch_status_to_finished()
                
            # Any rosmodules failed
            if self.is_any_rosmodules_failed():
                self.switch_status_to_failed(err_msg='One of the rosmodules failed')
                
        # check terminating status
        if self.job_status == self.StatusChoices.TERMINATING:
            if self.is_all_modules_not_found():
                self.switch_status_to_completed()
                
        return action


    def is_lifecycle_module_completed(self) -> bool:
        pod_name = f'{self.batch_job_group.group_postfix}-{self.batch_job_group.lifecycle_rosmodule_name}-{self.slug}'
        # print("lifecycle module pod name: ", pod_name)
        for pod in self.pod_status:
            if pod['name'] == pod_name:
                # print("Lifecycly pod status: ", pod['status'])
                if pod['status'] == 'Succeeded':
                    return True
        return False        

    @property
    def lifecycle_pod_name(self):
        return f'{self.batch_job_group.group_postfix}-{self.batch_job_group.lifecycle_rosmodule_name}-{self.slug}'

    @property
    def save_logs_in_volume(self) -> bool:
        """
        Check whether saving logs in volume.
        """
        try:
            return self.batch_job_group.deployment_manifest['jobSpec']['advances']['saveLogsInVolume']
        except KeyError:
            self.logs.append({'[Warning]': f'{timezone.now()} - KeyError by getting saveLogsInVolume. Set to False'})
            return False
        
    @property
    def group_data_in_storage(self) -> bool:
        """
        Check whether the group data is in storage.
        """
        try:
            return self.batch_job_group.deployment_manifest['jobSpec']['advances']['groupDataInStorage']
        except KeyError:
            self.logs.append({'[Warning]': f'{timezone.now()} - KeyError by getting groupDataInStorage. Set to False'})
            return False

    @property
    def discovery_server_pod_name(self):
        return self.scheduled_disc_server['pod']['metadata']['name']
    
    def is_discovery_servers_ready(self) -> bool:
        """
        Check if all discovery servers are ready.
        TODO: Check the service
        """
        try:
            for pod in self.pod_status:
                if pod['pod_type'] == 'discovery_server':
                    # print("DDS STATUS: ", pod['status'])
                    if not pod['status'] in ['Running', 'Succeeded']:
                        return False
            return True
        except:
            return False


    def is_all_rosmodules_ready(self) -> bool:
        try: 
            for pod in self.pod_status:
                if pod['pod_type'] in ['onboard_module', 'edge_module', 'cloud_module']:
                    # print("Pod Status: ", pod['status'])
                    if pod['status'] != 'Running':
                        return False
            return True
        except:
            return False


    def is_any_rosmodules_failed(self) -> bool: 
        try:
            for pod in self.pod_status:
                if pod['pod_type'] in ['onboard_module', 'edge_module', 'cloud_module']:
                    if pod['status'] == 'Failed':
                        return True
            return False
        except:
            return False


    def is_all_modules_not_found(self) -> bool:
        try:    
            for pod in self.pod_status:
                if pod['status'] != 'NotFound':
                    return False
            return True
        except:
            return False


    def get_all_deployed_pods(self) -> list:
        pod_name_list = []
        
        for status in self.pod_status:
            pod_name_list.append(status['name'])
        return pod_name_list


    def get_all_deployed_svcs(self) -> list:
        
        return [self.scheduled_disc_server['svc']['metadata']['name']]

    def get_pod_status(self):
        return self.pod_status
    
    def get_svc_status(self):
        return self.svc_status
    
    def get_last_check_time(self):
        return self.last_check_time
    
    def get_running_at(self):
        return self.running_at
    
    def get_elapsed_time(self):
        return timesince(self.running_at)
