# Python 
import logging

# Django 
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.timesince import timesince
from django.core.exceptions import ValidationError

# KubeROS
from .base import UserRelatedBaseModel, BaseModel
from .clusters import Cluster, ClusterNode

logger = logging.getLogger('kuberos.main.models')


class Fleet(UserRelatedBaseModel):
    """
    Fleet refers to a logical group of robot's onboard devices and edge nodes,
    providing a single interface for developers to deploy the ROS 2 software. 
    (For each deployment, a target fleet must be selected.)
    
    To estabilish a fleet, the user must designate a main cluster, 
    as well as a list of fleet nodes.
    
    Edge nodes are the nodes that located in the edge server (on-premise). 
    Once these edge nodes are incorporated into a fleet, 
    they cannot be allocated to other fleets.

    We recommend that fleet creation and management be performed by 
    a system administrator to ensure proper maintenance and organization of the fleets.
    
    """

    class FleetStatusChoices(models.IntegerChoices):
        """
        Fleet status
        """
        PENDING = 1, _('pending')
        IDLE = 2, _('idle')
        PART_USED = 3, _('partially used')
        FULL_USED = 4, _('fully used')
        IN_PROGRESS = 5, _('in progress')
        ERROR = 6, _('error')

    # fleet name
    fleet_name = models.CharField(
        max_length=128,
        unique=True,
        null=False,
        blank=False,
        help_text='name of fleet'
    )
    
    # Whether all fleet nodes are active and online
    healthy = models.BooleanField(
        default=False
    )

    alive_at = models.DateTimeField(
        blank=True,
        null=True,
        default=timezone.now, # TODO: Update this timestamp after the fleet is created and checked
    )
    
    fleet_status = models.IntegerField(
        choices=FleetStatusChoices.choices,
        default=FleetStatusChoices.PENDING
    )
    
    # Each fleet is associated with a main cluster
    # Each cluster can contain multiple fleets
    k8s_main_cluster = models.ForeignKey(
        Cluster,
        on_delete=models.SET_NULL,
        null=True
    )
    
    description = models.CharField(
        max_length=256,
        null=True,
        blank=True)
    
    # def clean(self):
    #     print("Cleaning fleet")
    #     if True:
    #         raise ValidationError('Fleet is not valid')
        
    def __str__(self):
        return '{} -- {}'.format(self.fleet_name, self.uuid)
    # def deactivate_robot_fleet(self):

    def __repr__(self) -> str:
        return self.fleet_name
    
    def check_fleet_node_availability(self, 
                                      fleet_node_name_list: list):
        # check if all fleet nodes are available
        # if not, raise exception
        # get all node names in fleet
        fleet_nodes = self.fleet_nodes.all()
        return True

    def get_fleet_node_set(self):
        return self.fleet_node_set.all()
    
    def get_fleet_state_for_scheduling(self):
        """
        Return the fleet state for scheduling
        
        Don't change the key name in the returned dict. 
        The key names are used in the scheduler: 
        """
        fleet_state = {
            'fleet_name': self.fleet_name,
            'uuid': str(self.uuid),
            'active': self.healthy, # TODO Change the active tag in returned fleet state for scheduling
            'deployable': self.is_fleet_deployable,
            'main_cluster_name': self.k8s_main_cluster.cluster_name,
            'fleet_node_state_list': [node.get_fleet_node_state_for_scheduling() for node in self.fleet_node_set.all()],
        }
        return fleet_state
    
    def is_deployable(self):
        """
        TO DELETE TODO
        """
        return True
    
    @property
    def created_since(self):
        """
        Return the time since fleet is created.
        """
        return timesince(self.created_time)
    
    @property
    def alive_age(self):
        """
        Return the time since last alive heartbeat of all fleet nodes. 
        """
        if self.fleet_status == self.FleetStatusChoices.PENDING:
            return 'N/A'
        if not self.healthy:
            return 'N/A'
        return timesince(self.alive_at)

    
    @property
    def is_entire_fleet_healthy(self):
        """
        Check if the entire fleet is healthy.
        """
        if not self.healthy:
            for f_node in self.fleet_node_set.all():
                if not f_node.is_fleet_node_alive:
                    self.healthy = False
            self.healthy = True
            self.save()
        return self.healthy
    
    @property
    def current_status(self):
        """
        Return the current status of the fleet.
        """
        num_fleet_nodes = self.fleet_node_set.all().count()
        num_deployable = self.fleet_node_set.filter(status='deployable').count()
        
        if num_deployable == num_fleet_nodes:
            self.fleet_status = self.FleetStatusChoices.IDLE
        elif num_deployable == 0:
            self.fleet_status = self.FleetStatusChoices.FULL_USED
        else:
            self.fleet_status = self.FleetStatusChoices.PART_USED
        self.save()
        
        return self.fleet_status
        

    @property
    def is_fleet_deployable(self):
        """
        TODO CHECK it 
        """
        if not self.healthy:
            return False
        if len(self.fleet_node_set.all()) == 0:
            return False
        return True

    def check_fleet_healthy_status(self):
        """
        Check the node status of the fleet.
        """
        
        pass
    
    def get_main_cluster_kube_config(self):
        """
        Return the main cluster kube config dict 
        FOR Celery tasks.
        """
        return self.k8s_main_cluster.cluster_config_dict
    
    def get_fleet_status_for_scheduler(self) -> dict:
        """
            Get the fleet status for scheduler
            
            Return:
                dict: 
        """
        return {
            'name': self.fleet_name,
            'uuid': self.uuid,
            'active': self.healthy,   # TODO Change the key name
            # 'status': self.status,
            'k8s_main_cluster': self.k8s_main_cluster.uuid,
            'fleet_node_set': [node.get_status_for_scheduler() for node in self.fleet_node_set.all()],
        }
    
    def check_for_deletion(self):
        """
        Deprecated TODO 
        Check if the fleet is ready to be deleted. 
        """
        res = True
        msg = ''
        f_nodes = self.fleet_node_set.all()
        for f_node in f_nodes: 
            if f_node.status in ['deploying', 'releasing', 'active']:  # Keep consitent with the status in fleet_node.py
                res = False
                msg += 'Fleet node <{}> is still in [{}] status. \n'.format(f_node.name, f_node.status)
        return {
            'success': res,
            'msg': msg
        }
    
    
    def safe_delete(self):
        """
        Safe delete the fleet.
        Before deleting the fleet, check whether all fleet nodes are in the deployable status.
        return: 
            {
                'status': 'success' or 'rejected',
                'msg': ''
            }
        """
        result = {
            'status': '',
            'errors': [],
            'msgs': []
        }
        
        # get active fleet nodes
        f_nodes = self.fleet_node_set.all()
        check_msgs = []
        for f_node in f_nodes:
            if f_node.status in ['deploying', 'releasing', 'active']:
                check_msgs.append(
                    f'Fleet node <{f_node.name}> is in [{f_node.status}] status.'
                )
        # TODO check the related deployments
        
        if len(check_msgs) > 0:
            # reject the deletion
            result['status'] = 'rejected'
            result['errors'].append({
                'reason': 'FleetInUse',
                'msg': '\n'.join(check_msgs)
            })

        else:
            # clean labels in the cluster nodes
            self.clean_cluster_labels()
            # TODO: trigger the update cluster labels tasks
            # delete the fleet
            self.delete()
            
            result['status'] = 'accepted'
            result['msgs'] = [f'Deleting fleet <{self.fleet_name}> is in processing.']
    
        return result

    def clean_cluster_labels(self) -> None:
        """
        Clean the fleet labels in the cluster nodes.
        """
        # get all fleet nodes
        f_nodes = self.fleet_node_set.all()
        for f_node in f_nodes:
            f_node.cluster_node.clean_labels_on_fleet_node_delete()

    
# Introduce this model as a middleware model.
# ClusterNode in the Edge or cloud can be shared by multiple fleets. 
# This will be checked in FleetNode.clean()? 
class FleetNode(BaseModel):
    """
    A fleet node encapsulates a cluster node that is to 
    be integrated into a fleet. It is created based on a cluster node
    to construct a fleet and will be subsequently removed once the fleet is deleted. 
    
    Fleet nodes incorporate the cluster node into the fleet and
    maintains it throughout the deployment process.

    Fleet nodes can be categorized into three types, mirroring the classification of cluster nodes:
        - onboard
        - edge
        - cloud (VMs, accessible via VPN)
    
    During each deployment, the fleet node delivers all essential system state 
    to scheduler and controller and caches the deployment event update in NODE_STATUS. 
    
    The fleet node serves as a middleware, bringing the KubeROS fleet and the underlying cluster. 
    """
    
    FLEET_NODE_STATUS_CHOICES = (
        # healthy states
        ('deployable', 'Deployable'),
        ('active', 'Active'),
        # transient states
        ('deploying', 'Deploying'),
        ('releasing', 'Releasing'), 
        # unhealthy states
        ('offline', 'Offline'),
        ('error', 'Error'),
        ('unknown', 'Unknown'),
        ('deactivated', 'Deactivated'),
    )
    
    # must be unique in a fleet
    # use the hostname in the cluster node
    name = models.CharField(
        max_length=128,
        null=False,
        blank=False,
        help_text='hostname of the cluster node, unique in a fleet'
    )
    
    fleet = models.ForeignKey(
        Fleet,
        on_delete=models.CASCADE,
        related_name='fleet_node_set'
    )
    
    # using one-to-one relationship? 
    cluster_node = models.ForeignKey(
        ClusterNode,
        on_delete=models.CASCADE,
        related_name='cluster_node_set'
    )
    
    
    # customized device type
    # For the robot that may have multiple onboard computers
    device_type = models.CharField(
        max_length=32,
        default='onboard'
    )
    
    # for future deployment -> fog robotics
    shared_resource = models.BooleanField(
        default=False,
    )
    
    # status of the fleet node
    # 3 categories: healthy, unhealthy, transient
    # this is the status the user retrieves from the KubeROS api server
    # and the status the scheduler uses to schedule the fleet node
    status = models.CharField(
        max_length=32,
        choices=FLEET_NODE_STATUS_CHOICES, 
        default='deployable'
    )
    
    # Fleet Node State
    # cluster node condition: retrieved directly from the cluster node  
    # fleet node state: extra metrics from third party tools (e.g., prometheus)
    fleet_node_state = models.JSONField(
        blank=True,
        null=True
    )
    
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['name', 'fleet'], 
                                    name='unique_fleet_node_name_in_fleet')
        ]

    def __str__(self):
        return '{} - {} - {}'.format(self.fleet.fleet_name, self.name, self.cluster_node.hostname)

    def get_status_for_scheduler(self):
        return {
            'hostname': self.name,
            'uuid': self.uuid,
            'cluster_node': self.cluster_node.uuid,
            'node_type': self.get_fleet_node_type(),
            'shared_resource': self.shared_resource,
            'status': self.status
        }
    
    def get_fleet_node_state_for_scheduling(self):
        state = {
            'hostname': self.name,
            'uuid': str(self.uuid),
            'robot_id': self.robot_id,
            'robot_name': self.robot_name,
            'onboard_comp_group': self.onboard_comp_group,
            'shared_resource': self.shared_resource,
            'node_status': self.status
        }
        # cluster node state 
        state['cluster_node_state'] = self.cluster_node.get_node_state()
        return state        
        
    def get_fleet_node_type(self):
        """
        return the node type: 
          - onboard-device_type
          - edge
          - cloud 
        """
        return self.node_type

    @property
    def robot_name(self):
        return self.cluster_node.robot_name
    
    @property
    def robot_id(self):
        return self.cluster_node.robot_id
    
    @property
    def onboard_comp_group(self):
        return self.cluster_node.device_group

    @property
    def is_fleet_node_alive(self):
        """
        Check if the fleet node is healthy.
        """
        return self.cluster_node.is_alive

class FleetHardwareOperationEvent(UserRelatedBaseModel):
    # create, update, delete robot nodes (todo - low priority)
    # excution through ansible-runner (todo - low priority)
    # label all robot nodes with fleet_id 
    
    name = models.CharField(
        max_length=255, 
        null=False, 
        blank=False, 
        verbose_name="name"
    )
    
    fleet = models.ForeignKey(
        Fleet,
        on_delete=models.CASCADE,
        null=False
    )
    
    event_type = models.CharField(
        max_length=64, 
        null=False, 
        blank=False
    )
    
    event_data = models.CharField(
        max_length=256, 
        null=True, 
        blank=True
    )
    
    description = models.CharField(
        max_length=256, 
        null=True, 
        blank=True
    )
    
    finished = models.BooleanField(
        default=True
    )
    
    success = models.BooleanField(
        default=False
    )
    
    class Meta: 
        abstract=False
    