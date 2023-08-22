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

# Django 
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.timesince import timesince
from django.contrib.auth.models import User
from django.utils.crypto import get_random_string

# KubeROS 
from main.models.base import UserRelatedBaseModel, get_sentinel_user
from main.models import Cluster


class BatchJobDeployment(UserRelatedBaseModel):
    
    class StatusChoices(models.TextChoices):
        
        PENDING = 'PENDING', _('pending')
        PREPROCESSING = 'PREPROCESSING', _('preprocess and generate job queue')
        PREPROCESS_SUCCESS = 'PREPROCESS_SUCCESS', _('job queue generated successfully')
        PREPROCESS_FAILED = 'PREPROCESS_FAILED', _('failed to generate job queue')
        EXECUTING = 'EXECUTING', _('execute batch jobs')
        COMPLETED = 'COMPLETED', _('all jobs completed')
        FAILED = 'FAILED', _('failure number execceed, check cluster')
        DELETING = 'DELETING', _('aborted and in deleting')
        DELETED = 'DELETED', _('deleted, jobs are not finished')

    name = models.CharField(
        max_length=128,
        null=False,
        blank=False,
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
    
    deployment_manifest = models.JSONField(
        blank=False,
        null=False,
        verbose_name='Deployment Manifest'
    )
    
    custom_rosparam_yaml_files = models.JSONField(
        blank=True,
        null=True
    )
    
    job_timeout = models.IntegerField(
        default = 300,
        verbose_name='Job timeout, unit: sec'
    )
    
    exec_clusters = models.ManyToManyField(
        Cluster, 
        blank=False,
        related_name='job_exec_cluster_set'
    )

    running_at = models.DateTimeField(
        null=True,
        blank=True
    )
    
    description = models.TextField(
        blank=True,
        null=True
    )
    
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['name'],
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
    
    
class BatchJobGroup(models.Model):
    """
    Each batch job group is executed on a single cluster.
    
    """
    
    group_postfix = models.CharField(
        max_length=32,
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
        blank=True
    )
    
    repeat_num = models.IntegerField(
        default=1
    )
    
    lifecycle_rosmodule_name = models.CharField(
        max_length=128,
        blank=True,
        null=True,        
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
        Get jobs to run.
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
    

class KuberosJob(models.Model):
    
    class StatusChoices(models.TextChoices):
        
        PENDING = 'PENDING', _('pending')
        SCHEDULED = 'SCHEDULED', _('scheduled')
        PREPARING = 'PREPARING', _('preparing') # Configmap, dds, volume.
        PREPARED = 'PREPARED', _('prepared') # Configmap, dds, volume.
        DEPLOYING = 'DEPLOYING', _('in deploying')
        RUNNING = 'RUNNING', _('running')
        SUCCEED = 'SUCCEED', _('job completed sucessfully')
        FAILED = 'FAILED', _('job failed')
        CLEANING = 'CLEANING', _('aborted and in deleting')
        CLEANED = 'CLEANED', _('deleted, jobs are not finished')
    
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
    
    deployment_manifest = models.JSONField(
        null=True,
        blank=True
    )
    
    running_timeout = models.IntegerField(
        default=300,
    )
    
    startup_timeout = models.IntegerField(
        default=300,
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
    
    scheduled_volume = models.JSONField(
        null=True,
        blank=True
    )
    
    scheduled_configmaps = models.JSONField(
        null=True,
        blank=True
    )
    
    ### STATUS ###
    configmaps_status = models.JSONField(
        null=True,
        blank=True
    )
    
    volume_status = models.JSONField(
        null=True,
        blank=True
    )
    
    disc_server_status = models.JSONField(
        null=True,
        blank=True
    )
    
    rosmodules_status = models.JSONField(
        null=True,
        blank=True,
    )
    
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
    
    ### TIMESTAMP ###
    last_check_time = models.DateTimeField(
        default=timezone.now
    )

    scheduled_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    
    starting_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    
    running_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    
    finished_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    
    ### MESSAGES ###
    job_msgs = models.JSONField(
        null=True,
        blank=True,
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
        
        self.save()
        
        # method copied, need to be refactored
        self.initialize()

    def update_pod_status(self, 
                          pod_status: list) -> None:
        self.pod_status = pod_status
        self.save()

    
    def get_job_description_for_scheduling(self) -> dict:
        res = {
            'job_uuid': self.get_uuid(),
            'group_postfix': self.batch_job_group.group_postfix,
            'job_postfix': self.slug,
            'manifest': self.deployment_manifest,
        }
        return res


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
    
    
    def update_pod_status(self,
                          pod_status: list,
                          svc_status: list = []) -> str:
        
        self.last_check_time = timezone.now()
        
        self.pod_status = pod_status
        self.svc_status = svc_status
        
        self.save()
        
        action = 'check'
        
        # print("Pod Status: ", self.pod_status)
        print(self.job_status)
        print(self.is_all_rosmodules_ready())
        
        # check startup timeout
        if self.job_status in [self.StatusChoices.PREPARING, 
                               self.StatusChoices.DEPLOYING]:
            if (timezone.now() - self.scheduled_at).seconds > self.startup_timeout:
                self.job_status = self.StatusChoices.FAILED
                self.job_msgs = {'error': 'Job startup timeout'}
                self.save()
                
                action = 'next'
                
        # check discovery server 
        if self.job_status == self.StatusChoices.PREPARING:
            if self.is_discovery_servers_ready():
                self.job_status = self.StatusChoices.PREPARED
                self.save()
                
                action = 'next'
                
        # check rosmodules
        if self.job_status == self.StatusChoices.DEPLOYING:
            if self.is_all_rosmodules_ready():
                self.running_at = timezone.now()
                self.job_status = self.StatusChoices.RUNNING
                self.save()

                action = 'next'
                
        # check lifcycle module
        if self.job_status == self.StatusChoices.RUNNING:
            
            print("Checking lifecycle module")
            
            # Running timeout
            if (timezone.now() - self.running_at).seconds > self.running_timeout:
                self.job_status = self.StatusChoices.FAILED
                self.job_msgs = {'error': 'Job timeout'}
                self.save()

                action = 'next'
                
            # Lifecycle module completed
            if self.is_lifecycle_module_completed():
                self.job_status = self.StatusChoices.SUCCEED
                self.finished_at = timezone.now()
                self.save()

                action = 'next'
                
            # Any rosmodules failed
            if self.is_any_rosmodules_failed():
                self.job_status = self.StatusChoices.FAILED
                self.job_msgs = {'error': 'ROS module failed'}
                self.save()

                action = 'next'
                
        # check deletion
        if self.job_status == self.StatusChoices.CLEANING:
            if self.is_all_modules_not_found():
                self.job_status = self.StatusChoices.CLEANED
                self.save()
                
                action = 'next'
        
        return action
        
    def is_lifecycle_module_completed(self) -> bool:
        pod_name = f'{self.batch_job_group.group_postfix}-{self.batch_job_group.lifecycle_rosmodule_name}-{self.slug}'
        print("lifecycle module pod name: ", pod_name)
        for pod in self.pod_status:
            if pod['name'] == pod_name:
                print("Lifecycly pod status: ", pod['status'])
                if pod['status'] == 'Succeeded':
                    return True
        return False        
        
    
    
    def is_discovery_servers_ready(self) -> bool:
        """
        Check if all discovery servers are ready.
        TODO: Check the service
        """
        try:
            for pod in self.pod_status:
                if pod['pod_type'] == 'discovery_server':
                    print("DDS STATUS: ", pod['status'])
                    if not pod['status'] in ['Running', 'Succeeded']:
                        return False
            return True
        except:
            return False
    
    def is_all_rosmodules_ready(self) -> bool:
        try: 
            for pod in self.pod_status:
                if pod['pod_type'] in ['onboard_module', 'edge_module', 'cloud_module']:
                    print("Pod Status: ", pod['status'])
                    if pod['status'] != 'Running':
                        return False
            return True
        except:
            return False
    
    def is_any_rosmodules_failed(self) -> bool: 
        try:
            for pod in self.pod_status:
                if pod['pod_type'] in ['onboard_module', 'edge_module', 'cloud_module']:
                    print("Pod Status: ", pod['status'])
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
    