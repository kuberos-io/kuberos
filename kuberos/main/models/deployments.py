# Python 
import uuid
import logging

# Django 
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.timesince import timesince
from django.contrib.auth.models import User

# KubeROS 
from main.models.base import UserRelatedBaseModel, get_sentinel_user
from main.models import Fleet


logger = logging.getLogger('kuberos.main.models')


def random_string(length=10):
    import random
    import string
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(length))


class Deployment(UserRelatedBaseModel):
    
    STATUS_CHOICES = (
        ('deploying', 'Deploying'),
        ('running', 'Running'),
        ('updating', 'Updating'),
        ('deleting', 'Deleting'),
        ('deleted', 'Deleted'),
        ('failed', 'Failed')
    )
    
    name = models.CharField(
        max_length=128, 
        null=False,
        blank=False
    )
    
    fleet = models.ForeignKey(
        Fleet,
        null=True,
        on_delete=models.SET_NULL,
        related_name='deployment_set',
    )
    
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default='deploying',
    )
    
    active = models.BooleanField(
        default=True
    )
    
    running_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    
    deployment_description = models.TextField(
        blank=True,
        null=True
    )
    
    config_maps = models.JSONField(
        blank=True, 
        null=True, 
        verbose_name='ConfigMaps for entire deployment'
    )
    
    configmaps_in_cluster = models.JSONField(
        blank=True, 
        null=True,
    )
    
    # True if the configmaps for the entire deployment are created 
    # False if the configmaps are deleted or not created yet
    configmaps_created = models.BooleanField(
        default=False
    )

    # last_check_time = models.DateTimeField(
    #     default=timezone.now
    # )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['name'],
                                    condition=models.Q(active=True), 
                                    name='unique_active_name')
        ]
        ordering = ['-created_time', 'name']

    def __str__(self) -> str:
        return str(self.name)
    
    def get_uuid(self) -> str:
        return str(self.uuid)
    
    def get_main_cluster_config(self) -> dict:
        """
        Return the main cluster config dict for kuberos/kubernetes executors
        """
        return self.fleet.get_main_cluster_kube_config()
    
    
    @property
    def running_since(self):
        """
        Return the run time since deployment
        """
        if self.running_at:
            return timesince(self.running_at)
        else:
            return 'Not running'
    
    
    @property
    def fleet_name(self):
        """
        Return the target fleet name
        """
        return self.fleet.fleet_name


    def get_config_maps(self) -> list:
        return self.config_maps
    
    def update_status_as_running(self):
        self.status = 'running'
        self.running_at = timezone.now()
        self.active = True
        self.save()
    
    def update_status_as_deleted(self):
        print("Delete")
        self.active = False
        self.status = 'deleted'
        self.name = f'{self.name}-deleted-{random_string(5)}', 
        self.save()
        print("Can not save? ")
        
    def update_status_as_failed(self):
        self.status = 'failed'
        self.active = False
        self.save()
        
    def update_deleted_configmaps(self):
        self.config_maps = {}
        self.configmaps_created = False
        self.save()
        
    def update_created_configmaps(self, configmaps_status):
        # self.configmaps_in_cluster = configmaps_status
        self.configmaps_created = True
        self.save()
        print("Save updated configmaps")
    
    def update_entire_deployment_status(self):
        """
        Check the phase of all deployment jobs and update the deployment status.
        """

        # if all deployment job is deleted -> make the deployment inactive 
        phases = []
        
        for job in self.deployment_job_set.all():
            phases.append(job.job_phase)
        
        logger.debug("CHECK All DEPLOYMENT JOBS' Phase: %s", phases)
        
        if all(phase == 'delete_success' for phase in phases):
            
            self.active = False
            self.status = 'deleted'
            self.name = f'{self.name}-deleted-{random_string(5)}', 
            self.save()
            logger.debug("[Deployment Model] Delete the entire deployment: %s", self.name)
            return True
        
        if all(phase == 'deploy_success' for phase in phases):
            self.status = 'running'
            self.running_at = timezone.now()
            self.active = True
            self.save()
            return True

        # if any deployment job is failed -> make the deployment failed
        if any(phase in ['disc_server_failed', 
                         'daemon_failed', 
                         'rosmodule_failed',
                         'deploy_failed', 
                         'delete_failed'] for phase in phases):
            self.status = 'failed'
            self.active = True
            self.save()
            return True
                
        # self.deployment.status = 'deleted'
        #         self.deployment.active = False
        #         self.deployment.name = f'{self.deployment.name}-deleted-{random_string(5)}', 
        #         self.deployment.save()

    def is_cluster_cleaned(self) -> bool:
        if self.configmaps_created:
            return False
        dep_jobs = self.deployment_job_set.all()
        if len (dep_jobs) > 0:
            return False
        return True
        

    def safe_delete(self):
        self.update_status_as_deleted()


class DeploymentEvent(models.Model):
    
    class EventTypeChoices(models.TextChoices):
        """
        Deployment type choices. 
        In the entire robotic application lifecycle, kubeROS supports multiple deployment types.
        """
        DEPLOY = 'DEPLOY', _('initial deployment')
        UPDATE = 'UPDATE', _('update existing rosmodule')
        DELETE = 'DELETE', _('delete entire application')
        SCALE = 'SCALE', _('scale software module')
        
        @classmethod
        def get_value(cls, member):
            return cls[member].value[0]
        
    class EventStatusChoices(models.TextChoices):
        """
        Deployment event status choices.
        This status is used to track the deployment event.
        """
        CREATED = 'CREATED', _('created')
        FAILED = 'FAILED', _('failed')
        SUCCESS = 'SUCCESS', _('success')
    
    
    uuid = models.UUIDField(
        primary_key=True,
        editable=False,
        unique=True,
        default=uuid.uuid4
    )

    event_status = models.CharField(
        max_length=32,
        choices=EventStatusChoices.choices,
        default=EventStatusChoices.CREATED,
    )

    event_type = models.CharField(
        max_length=32,
        choices=EventTypeChoices.choices,
        default=EventTypeChoices.DEPLOY,
    )

    deployment = models.ForeignKey(
        Deployment,
        on_delete=models.CASCADE,
        related_name='deployment_event_set'
    )
    
    created_at = models.DateTimeField(
        null=False, 
        blank=False,
        verbose_name="created time",
        default=timezone.now
    )
    
    finished_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    
    created_by = models.ForeignKey(
        User, 
        related_name='%s(class)s_created+',
        editable=False,
        on_delete=models.SET(get_sentinel_user),
    )

    deployment_description = models.TextField(
        null=True,
        blank=True,
        help_text="Yaml file for this deployment"
    )
    
    def __str__(self):
        return str(self.uuid)

    def get_uuid(self) -> str:
        return str(self.uuid)

    def update_dep_event_status(self):
        """
        Check the phase of all deployment jobs and update the deployment status.
        """

        # if all deployment job is deleted -> make the deployment inactive 
        phases = []
        
        for job in self.deployment_job_set.all():
            phases.append(job.job_phase)
        
        logger.debug("CHECK All DEPLOYMENT JOBS' Phase: %s", phases)
        
        # For Deploy event
        if self.event_type == self.EventTypeChoices.DEPLOY:        
            if all(phase == 'deploy_success' for phase in phases):
                self.event_status = self.EventStatusChoices.SUCCESS
                self.finished_at = timezone.now()
                self.save()
                
                # update deployment status
                self.deployment.update_status_as_running()
                return True

        # For delete event 
        if self.event_type == self.EventTypeChoices.DELETE:
            if all(phase == 'delete_success' for phase in phases):
                self.event_status = self.EventStatusChoices.SUCCESS
                self.finished_at = timezone.now()
                self.save()
                
                # update deployment status
                self.deployment.update_status_as_deleted()
                return True
        
        # if any deployment job is failed -> make the deployment failed
        if any(phase in ['disc_server_failed', 
                         'daemon_failed', 
                         'rosmodule_failed',
                         'deploy_failed', 
                         'delete_failed'] for phase in phases):
            self.event_status = self.EventStatusChoices.FAILED
            self.finished_at = timezone.now()
            self.save()
            
            # update deployment status
            self.deployment.update_status_as_failed()
            return True


class DeploymentJob(models.Model):
    """
    The entire deployment is divided into jobs. 
    Each job is responsible for one robot with its entire software modules aross all physical machines.
    """
    
    # Don't change the keys!!!
    JOB_PHASE_CHOICES = (
        ('pending', 'pending'),
        # Discovery server
        ('disc_server_in_progress', 'Discovery server in progress'),
        ('disc_server_failed', 'Failed to deploy discovery server'),
        ('disc_server_success', 'discovery server ready'),
        # DaemonSet like rosbridge, monitor, etc. introduced in beta release
        ('daemon_in_progress', 'DaemonSet dispatchted to K8s'),
        ('daemon_failed', 'Failed to dispatch daemon set'),
        ('daemon_success', 'Success to dispatch daemon set'),
        # ROS Modules
        ('rosmodule_in_progress', 'ROS Modules in progress'),
        ('rosmodule_failed', 'Failed to dispatch ROS Modules'),
        ('rosmodule_success', 'Success to dispatch ROS Modules'),
        # Job Terminator
        ('deploy_success', 'Deployment success'),
        ('deploy_failed', 'Deployment failed'),
        ('job_completed', 'Job execution completed'),
        # Delete
        ('request_for_delete', 'Request for deleting deployment Job'),
        ('delete_in_progress', 'Delete in progress'),
        ('delete_failed', 'Delete failed'),
        ('delete_success', 'Delete success'),
    )

    uuid = models.UUIDField(
        primary_key=True,
        editable=False, 
        unique=True, 
        default=uuid.uuid4
    )

    robot_name = models.CharField(
        max_length=128,
        default='robot',
    )

    disc_server = models.JSONField(
        null=True,
        blank=True,
        default=list, 
        verbose_name='Scheduled discovery server'
    )
    
    onboard_modules = models.JSONField(
        null=True,
        blank=True,
        default=list,
        verbose_name='Scheduled onboard modules'
    )
    
    edge_modules = models.JSONField(
        null=True,
        blank=True,
        default=list,
        verbose_name='Scheduled edge modules'
    )
    
    cloud_modules = models.JSONField(
        null=True,
        blank=True,
        default=list,
        verbose_name='Scheduled cloud modules'
    )
    
    # ConfigMaps used for this deployment job
    config_maps = models.JSONField(
        null=True, 
        blank=True, 
        default=list,
        verbose_name='ConfigMaps'
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

    job_phase = models.CharField(
        max_length=32,
        choices=JOB_PHASE_CHOICES,
    )
    
    deployment = models.ForeignKey(
        Deployment,
        on_delete=models.CASCADE,
        related_name='deployment_job_set'
    )
    
    # deployment_event = models.ForeignKey(
    #     DeploymentEvent,
    #     on_delete=models.CASCADE,
    #     related_name='deployment_job_set'
    # )
    
    deployed_resources = models.JSONField(
        null=True,
        blank=True,
        verbose_name='Deployed resources'
    )
    
    last_check_time = models.DateTimeField(
        default=timezone.now
    )

    running_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    
    def __str__(self) -> str:
        return str(self.uuid) + ' ' + self.deployment.name
    
    def __repr__(self) -> str:
        return 'self.uuid' + ' ' + self.job_phase

    def get_uuid(self) -> str:
        return str(self.uuid)
    
    def intialize(self):
        pod_status_list = []
        svc_status_list = []
        
        for module in self.disc_server:
            pod_status_list.append({
                'name': module['pod']['metadata']['name'],
                'pod_type': 'discovery_server', 
                'status': 'Pending'
            })
            svc_status_list.append({
                'name': module['svc']['metadata']['name'],
                'svc_type': 'discovery_server', 
                'status': 'Pending'
            })
            
        for module in self.onboard_modules:
            pod_status_list.append({
                'name': module['metadata']['name'],
                'pod_type': 'onboard_module',
                'status': 'Pending'
            })
            
        for module in self.edge_modules:
            pod_status_list.append({
                'name': module['metadata']['name'],
                'pod_type': 'edge_module',
                'status': 'Pending'
            })

        self.pod_status = pod_status_list
        self.svc_status = svc_status_list
        self.save()
    
    def update_phase_request_for_delete(self):
        self.job_phase = 'request_for_delete'
        self.save()
    
    def get_uuid(self) -> str: 
        return str(self.uuid)
    
    def get_disc_server(self):
        return self.disc_server
    
    def get_all_rosmodules(self) -> list:
        return self.onboard_modules + self.edge_modules + self.cloud_modules
    
    def get_all_deployed_pods(self) -> list:
        pod_name_list = []
        
        for status in self.pod_status:
            pod_name_list.append(status['name'])
        return pod_name_list
    
    def get_all_deployed_svcs(self) -> list:
        svc_name_list = []
        
        for disc_server in self.disc_server:
            svc_name_list.append(disc_server['svc']['metadata']['name'])
        return svc_name_list


    @property
    def all_pods_status(self, ) -> dict:
        """
        Return the status of all pods for serializers
        """
        return self.pod_status
    
    @property
    def all_svcs_status(self, ) -> dict:
        """
        Return the status of all services for serializers
        """
        return self.svc_status
    
    
    def require_next_status_check(self) -> bool:
        """
        DEPRECATED
        """
        if self.job_phase in ['disc_server_in_progress', 
                              'rosmodule_in_progress', 
                              'delete_in_progress']:
        
            return True
        else:
            return False
    
    def since_last_check(self) -> int:
        """
        Return the time since last check in seconds.
        """
        return (timezone.now() - self.last_check_time).seconds
    
    def update_configmaps_status(self, 
                                 configmaps: list) -> None:
        """
        Update the configmaps status
        """
        self.config_maps = configmaps
        self.save()
        
    def update_pod_status(self,
                          pod_status: list,
                          svc_status: list = []) -> str:
        """
        Return next actions: check | next | finished
        """
                
        # check the last check time, to avoid unnecessary check process        
        self.last_check_time = timezone.now()
        
        # update pod status
        self.pod_status = pod_status
        self.svc_status = svc_status
        self.save()
        
        # update deployment status
        action = 'finished'
        
        # on deleting 
        if self.job_phase == 'delete_in_progress':
            if self.is_all_modules_not_found():
                self.job_phase = 'delete_success'
                self.save()
                self.deployment.update_entire_deployment_status()
                # self.deployment_event.update_dep_event_status()
                action = 'finished'
            else:
                action = 'check'
            return action
        
         # check discovery server status
        elif self.job_phase == 'disc_server_in_progress':
            if self.is_discovery_servers_ready():
                self.job_phase = 'disc_server_success'
                self.save()
                action = 'next'
            else:
                action = 'check'
            return action
        
        elif self.job_phase == 'rosmodule_in_progress':
            if self.is_all_rosmodules_ready():
                self.job_phase = 'deploy_success'
                self.running_at = timezone.now()
                self.save()
                self.deployment.update_entire_deployment_status()
                # self.deployment_event.update_dep_event_status()
                action = 'finished'
            
            elif self.is_any_rosmodules_failed():
                self.job_phase = 'deploy_failed'
                self.save()
                self.deployment.update_entire_deployment_status()
                action = 'finished'

            else:
                action = 'check'

            return action

        else:
            # logger.error("Unknown job phase: {}".format(self.job_phase))
            return action
        
        
    def get_pod_list(self) -> list:
        """
        MAYBE DEPRECATED
        USED in check_deployment_job_status
        Return the list of pods to check the status.
        """
        pod_list = []
        for module in self.disc_server:
            pod_list.append({
                'name': module['pod']['metadata']['name'],
                'pod_type': 'discovery_server'
            })
        for module in self.onboard_modules:
            pod_list.append({
                'name': module['metadata']['name'],
                'pod_type': 'onboard_module'
            })
        for module in self.edge_modules:
            pod_list.append({
                'name': module['metadata']['name'],
                'pod_type': 'onboard_module'
            })
        # self.deployed_resources['pods'].extend(pod_list)
        # self.save()
        return pod_list 
    
    
    def get_svc_name_list(self) -> list:
        svc_name_list = []
        
        for svc in self.svc_status:
            svc_name_list.append({'name': svc['name'], 
                                  'svc_type': svc['svc_type']})    
        return svc_name_list
    
    
    def is_discovery_servers_ready(self) -> bool:
        """
        Check if all discovery servers are ready.
        TODO: Check the service
        """
        try:
            for pod in self.pod_status:
                if pod['pod_type'] == 'discovery_server':
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
