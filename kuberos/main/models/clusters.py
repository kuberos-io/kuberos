# Python
import base64
import logging
from typing import Union, List

# Django
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.timesince import timesince
from django.utils import timezone

# KubeROS
from .base import BaseTagModel, BaseModel, UserRelatedBaseModel
from .hosts import Host



__all__ = [
    'Cluster',
    'ClusterNode',
    'ClusterServiceAccount',
]

logger = logging.getLogger('kuberos.main.models')



def cluster_ca_file_path(instance, filename):
    """
    Return the path to store the cluster CA certificate
    """
    suffix = 'crt'
    return f'clusters/{instance.cluster_name}/ca_cert/\
            {instance.cluster_name}_{str(instance.uuid)}.{suffix}'


class Cluster(BaseTagModel):
    """
    Cluster that be managed by KubeROS
    
    KubeROS supports the management of multiple clusters, 
    from cluster for development, testing, staging, to production.
    
    To enable this, KubeROS needs a service account token for each cluster, 
    and with appropriate permissions to access the cluster resources.
    
    In first prototype, we use the admin token for each cluster. 
    In the future, the permission of the service account token will be refined.
    
    Idea for the future: 
        - Support for K0s, K3s, K8s, and other Kubernetes distributions?
        - K3s can be used for drones and robots with limited resources
    """

    class ClusterDistributionChoices(models.IntegerChoices):
        """
        Cluster Distribution Type
        
        Support for K0s, K3s, K8s, and other Kubernetes distributions.
        Some KubeROS jobs depend on the cluster distribution type.
        """
        NATIVE_K8S = 1, _('k8s')
        K3S = 2, _('k3s')
        
    class EnvTypeChoices(models.IntegerChoices):
        """
        Environment type choices. 
        
        In the entire software lifecycle, the software modules are 
        deployed in different environments in different stages, and 
        for different purpose, for instance: development, testing, staging, and production.
        """
        DEV = 1, _('dev')
        TEST = 2, _('test')
        STAG = 3, _('stag')
        PROD = 4, _('prod')
        
        __empty__ = _('(unknown env)')
    
    class ClusterStatusChoices(models.IntegerChoices):
        """
        Cluster Status
         - pending: the cluster is registered, but not synchronized yet
         - ready: the cluster is synchronized
         - conn. error: the cluster API server is not reachable
         - node offline: some nodes are not reachable
         - deleting: the cluster is being deleted
        """
        PENDING = 1, _('pending')
        READY = 2, _('ready')
        CONN_ERROR = 3, _('conn. error')
        NODE_ERROR = 4, _('node offline')
        DELETING = 5, _('deleting')
        
        __empty__ = _('(unknown status)')
    
    # unique name in KubeROS database
    cluster_name = models.CharField(
        max_length=64,
        unique=True,
        help_text='cluster name'
    )

    # cluster status in KubeROS
    cluster_status = models.IntegerField(
        choices = ClusterStatusChoices.choices,
        default = ClusterStatusChoices.PENDING,
    )

    # cluster type:
    # Usually, we want test our application in a test or staging environment
    # before deploying it to production.
    env_type = models.IntegerField(
        choices=EnvTypeChoices.choices,
        default=EnvTypeChoices.DEV,
    )

    # cluster distribution
    # K8s, K3s, etc.
    distribution = models.IntegerField(
        choices=ClusterDistributionChoices.choices,
        default=ClusterDistributionChoices.NATIVE_K8S,
    )

    # cluster distribution version
    # e.g. 1.21.2
    # API can change between versions
    distribution_version = models.CharField(
        max_length=128,
        default='0.0.0'
    )

    # access endpoints
    host_url = models.CharField(
        max_length=1024,
        null=False,
        blank=False
    )

    # cluster CA certificate
    # can be found in /etc/kubernetes/pki/ca.crt
    ca_pem = models.TextField(
        max_length=4096,
        null=True,
        blank=True,
        help_text='PEM format (base64 decoded), can be saved as Text (Data)'
    )

    # cluster CA certificate
    # can be found in /etc/kubernetes/pki/ca.crt
    # recommend to use this format
    ca_crt_file = models.FileField(
        null=True,
        blank=True,
        upload_to=cluster_ca_file_path,
        help_text='CA public certificate file, can be found in /etc/kubernetes/pki/ca.crt'
    )

    # service account token for admin user
    # Adequate permission is required. 
    # FOR SECURITY REASON.
    # once this token has been imported into the cluster, it cannot be retrieved again.
    # TODO: refine the permission of the service account token and write DOC
    # Service account token for admin user, can be found in /var/run/secrets/kubernetes.io/serviceaccount/token
    service_token_admin = models.CharField(
        max_length=2048,
        null=False,
        blank=False,
        help_text='Service Account Token'
    )

    # Sync settings
    sync_period = models.IntegerField(
        default=60,
        verbose_name="Auto sync period (seconds)",
    )

    auto_sync = models.BooleanField(
        default=False
    )
    
    last_sync_time = models.DateTimeField(
        null=False,
        blank=False,
        verbose_name="last sync time",
        default=timezone.now
    )
    
    is_available = models.BooleanField(
        default=False,
    )
    
    sync_errors = models.JSONField(
        null=True,
        blank=True,
        verbose_name="current sync errors",
    )
    
    last_error_timestamp = models.DateTimeField(
        null=False,
        blank=False,
        verbose_name="last error timestamp",
        default=timezone.now
    )
    
    class Meta:
        verbose_name = 'Cluster'
        verbose_name_plural = 'Clusters'
        ordering = ['cluster_name', 'created_time']

    def __str__(self) -> str:
        return str(self.cluster_name)

    def __repr__(self) -> str:
        return str(self.cluster_name)

    @property
    def cluster_config_dict(self) -> dict:
        """
        Get the cluster config dict to connect to the k8s cluster api server
        Use admin token for now
        ONLY FOR INTERNAL USE
        Don't change the return format!
        """
        return {
            'name': self.cluster_name,
            'host_url': self.host_url,
            'service_token': self.service_token_admin,
            'ca_cert_path': self.ca_crt_file.path,
        }

    @property
    def last_sync_since(self) -> str:
        """
        Return the time since last synchronization
        """
        if not self.cluster_status == self.ClusterStatusChoices.READY:
            return 'N/A'
        if not self.last_sync_time:
            return 'N/A'
        return timesince(self.last_sync_time)

    @property
    def alive_age(self) -> str:
        """
        Return the cluster alive age
        """
        if not self.last_error_timestamp:
            return 'N/A'
        if not self.is_available:
            return 'Unavailable'
        return timesince(self.last_error_timestamp)

    def update_sync_timestamp(self) -> None:
        """ Update last sync time """
        self.last_sync_time = timezone.now()
        self.is_available = True
        self.cluster_status = self.ClusterStatusChoices.READY
        self.save()

    def report_error(self,
                     errors: Union[dict, list]) -> None:
        """
        Called when the cluster is not reachable or other errors occur
        """
        # if self.is_available:
        self.is_available = False
        self.sync_errors = errors
        
        if self.is_available:
            # timestamp, from available to unavailable
            self.last_error_timestamp = timezone.now()
        
        self.save()

    def get_cluster_node_uuid_list(self) -> list:
        """
        Get cluster node uuid list
        """
        cluster_node_uuid_list = []
        for node in self.cluster_node_set.all():
            cluster_node_uuid_list.append(str(node.uuid))
        return cluster_node_uuid_list

    def get_cluster_node_name_list(self) -> list:
        """
        Get cluster node name list
        """
        cluster_node_name_list = []
        for node in self.cluster_node_set.all():
            cluster_node_name_list.append(node.hostname)
        return cluster_node_name_list

    def get_cluster_node_labels(self) -> List[dict]:
        """
        Return the labels of the cluster ndoes. 
        The labels is used to filter and select the nodes for scheduling. 
        Two ways to upate the labels:
            - through the inventory description 
            - through the creation, update, or deletion of the fleet nodes
        
        Return:
            labels: dict of labels
        """
        node_labels_list = [node.get_node_labels() for node in self.cluster_node_set.all()]
        return node_labels_list


    def get_available_edge_node_state(self) -> List[dict]:
        """
        Return the available edge nodes for scheduling
        """
        ava_edge_nodes = []
        for node in self.cluster_node_set.all():
            if node.is_available_edge_node():
                node_state = node.get_node_state_for_scheduling()
                ava_edge_nodes.append(node_state)
        return ava_edge_nodes


    def find_c_node_by_robot_name(self, 
                                  robot_name: str) -> List[dict]:
        """
        Find the cluster node by given robot name
        """
        node_l = []
        for node in self.cluster_node_set.all():
            if node.robot_name == robot_name:
                node_l.append(node)
        return node_l


    def reset_cluster(self,
                      hard_reset: bool = False) -> None:
        for node in self.cluster_node_set.all():
            node.reset()


def cluster_secret_path(instance, filename):
    # TODO: Check duplication of file name
    # print(instance.robot_model, instance.robot_model.pk)
    suffix = 'srt'
    return f'clusters/{instance.created_by.name}/secret/{instance.name}.{suffix}'


class ClusterServiceAccount(UserRelatedBaseModel):
    """
    Secret for cluster non-root user TODO
    
    The standard user in KubeROS can only access resources they have been granted permissions for. 
   
    User authorization is verified in the KubeROS API server.
   
    For security reasons, the user account's permissions to Kubernetes (K8s) are also restricted.
    """

    name = models.CharField(
        max_length=255,
        null=False,
        blank=False,
        verbose_name="name"
        )

    # authentification 
    # created by KubeROS admin user 
    # TODO: Automate the process of creating a service account token
    service_token = models.CharField(
        max_length=2048,
        null=False,
        blank=False
    )

    # ca file
    secret_file = models.FileField(
        upload_to=cluster_secret_path,
        blank=True,
        null=True,
    ) # TODO: PEM format, can be saved as Text, see gitlab

    description = models.TextField(
        null=True,
        blank=True
    )

    # each cluster owns multiple service accounts for different users
    cluster = models.ForeignKey(
        Cluster,
        on_delete=models.CASCADE,
        related_name='cluster_sa_set'
    )


class ClusterNode(BaseModel):
    """
    KubeROS platform manages all cluster nodes from all cluster.
    
    ClusterNode in the KubeROS platform can be only created by
    the task: sync_cluster_nodes. 
    
    For dev purpose, you can delete the cluster node and run the task again. 
    
    KubeROS labels for cluster node: 
        
        kuberos.io/role: <role>
        
        device.kuberos.io/hostname: <hostname>  UNIQUE
        device.kuberos.io/uuid: <uuid> of cluster-node UNIQUE
        device.kuberos.io/group: <device_group> 
            - onboard, edge, cloud
            - customized: computer_for_arm, computer_for_platform
        
        robot.kuberos.io/name: <robot_name> UNIQUE
        robot.kuberos.io/id: <robot_id> UNIQUE (Defined in your organization)
        
        fleet.kuberos.io/name: <fleet_name> UNIQUE
        fleet.kuberos.io/uuid: <uuid> UNIQUE
        
        peripheral.kuberos.io/device_list: <peripheral_device_list> 
        
        status.kuberos.io/kuberos_registered: True/False
    """

    class ROLE_CHOICES(models.IntegerChoices):
        """
        Role of the cluster node in KubeROS
        """
        ONBOARD = 1, _('onboard')
        EDGE = 2, _('edge')
        CLOUD = 3, _('cloud')
        CONTROL_PLANE = 4, _('control_plane')
        UNASSIGNED = 5, _('unassigned')


    # Unique name in the cluster
    hostname = models.CharField(
        max_length=255,
        null=False,
        blank=False,
        verbose_name="hostname"
    )

    # Alias provides a another way to identify the cluster node.
    # If the hostname in the local network has to fulfill the DNS naming convention, 
    # which may not convient for the KubeROS users to remember.
    hostname_alias = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        unique=True
    )

    # Host is the physical machine can be managed direclty by KubeROS
    # [Experimental feature] This feature is still under development
    # Idea: Using SSH to connect to the host and execute the scripts for
    #       installing, updating Kubenetes and plugins.
    host = models.ForeignKey(
        Host,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    # KubeROS supports the management of multiple clusters.
    # Robots and computers in a local network can be segmented into various clusters.
    # However, we advise to minimize the number of the clusters within a local network,
    # as each cluster requires at least one dedicated computer for the control-plane.
    # In the event of a large number of robots, or there's need to isolate different applications, 
    # we recommend partioning them into multiple clusters
    cluster = models.ForeignKey(
        Cluster,
        on_delete=models.CASCADE,
        null=True,
        related_name='cluster_node_set'
    )

    # [Experimental feature]: for fog robotics
    # If it is a shared resource, this cluster node can be used by multiple fleets
    shared = models.BooleanField(
        default=False,
        null=False
    )

    # It is possible that several nodes in the k8s 
    # don't match any devices in the hardware resource description. 
    # The unregistered node can be dynamically added or removed from the cluster
    # In each sync process, KubeROS will discover the new node and 
    # add it into the cluster as an UNREGISTERED node.
    # If a registered node is not found during the sync process,
    # KubeROS will mark it as an unreachable node with is_alive = False
    kuberos_registered = models.BooleanField(
        default=False,
        help_text='If the node is registered in kuberos cluster'
    )

    # If the node in sync process is founded -> is_alive = True
    # Else -> is_alive = False
    is_alive = models.BooleanField(
        default=False,
        help_text='If the node is alive'
    )


    # type of the node in the cluster for KubeROS 
    # - control-plane: control plane node: no rosmodule can be deployed on this node
    # - onboard: dedicated onboard device on the robot. 
    # - edge: edge node
    # - cloud: cloud node (VMs through VPN)
    # - unassigned: unassigned node
    kuberos_role = models.IntegerField(
        choices=ROLE_CHOICES.choices,
        default=ROLE_CHOICES.UNASSIGNED,
    )

    # device group: only for robot that has multiple onboard computers
    # e.g. a mobile manipulator might have 
    # one dedicated computer for the arm and another one for the platform
    device_group = models.CharField(
        max_length=64,
        blank=True,
        null=True
    )

    # Future feature: group based quotas for shared resources
    resource_group = models.CharField(
        max_length=64,
        default='public'
    )

    # labels that will be injected into the cluster node label. 
    # check this in K8s: kubectl get nodes --show-labels
    # parameter that labeled by initalizing with hardware resource description
    #   - kuberos.io/role
    #   - device.kuberos.io/
    #   - robot.kuberos.io/
    # Parameters need to be updated: 
    #   - fleet.kuberos.io/
    #   - status.kuberos.io/registered
    # Accessible by following methods:
    #  - node.metadata.labels  
    labels = models.JSONField(
        null=True
    )

    # tag to determine whether the labels need to be synchronized to the cluster.
    is_label_synced = models.BooleanField(
        default=False
    )

    # k8s cluster node state
    # refer to https://kubernetes.io/docs/concepts/architecture/nodes/#condition
    # the cluster node condition presents the status of the node in the cluster 
    # for scheduling
    node_state = models.JSONField(
        null=True,
    )

    # last sync time
    # sync period: see in kuberos_settings
    last_sync_time = models.DateTimeField(
        null=False,
        blank=False,
        verbose_name="last sync time",
        default=timezone.now
    )

    # node info
    # - architecture: arm64 / amd64
    # - container runtime: docker://20.10.7 / containerd://1.6.15
    # - kubelet_version: kubelet_version: v1.22.13
    # - addressess: {'internal_ip':  }
    node_info = models.JSONField(
        null=True,
        blank=True,
        verbose_name="node info",
    )

    peripheral_devices = models.JSONField(
        null=True,
        blank=True,
        verbose_name='peripheral devices',
        help_text="Peripheral devices connected to the physical machine, such as camera, liard",
    )

    # TOOD: network state for cloud nodes through VPN


    class Meta:
        ordering = ['kuberos_registered', 'is_alive']
        constraints = [
            models.UniqueConstraint(fields=['hostname', 'cluster'], 
                                    name='unique_node_name_in_cluster')
        ]

    def __str__(self):
        return f'{self.hostname} -- {self.uuid}'

    def is_available(self) -> bool:
        """
        Check if the cluster node is available to be assigned to a fleet.
        Rule: 
            - If the node is a control plane node, it is not available
            - If the node is not registred in KubeROS with inventory manifest
            - If the node is already assigned to a fleet, it is not available
        """
        
        if self.kuberos_role in [self.ROLE_CHOICES.CONTROL_PLANE, self.ROLE_CHOICES.UNASSIGNED]:
            return False
        if not self.kuberos_registered:
            return False
        
        # get the related fleet node
        fleet_nodes = self.cluster_node_set.all()
        if len(fleet_nodes) == 0 or self.shared==True:
            return True
        else:
            return False

    def get_current_fleet(self):
        fleet = self.cluster_node_set.all()
        if len(fleet) == 0:
            return None
        elif len(fleet) > 1:
            raise Exception('Multiple fleets for this node')
        else:
            return fleet[0]

    def get_labels(self) -> dict:
        return {
                'hostname': self.hostname,
                'labels': self.labels,
                }

    def check_label_update_result(self,
                                  new_labels: dict) -> None:
        """
        Check the labels returned by the cluster node after the update
        """
        # TODO Compared the new labels and cached labels
        # print("New labels:", new_labels)
        self.is_label_synced = True
        self.save()
        
    def update_from_inventory_manifest(self,
                                       kuberos_role: str,
                                       robot_name: str,
                                       robot_id: str,
                                       onboard_computer_group: str = None,
                                       periphal_devices: dict = None,
                                       shared: bool = False) -> None:
        """
        Update the node labels in KubeROS database from the inventory manifest
        """
        labels = {
            'kuberos.io/role': kuberos_role.lower(),
            'device.kuberos.io/hostname': self.hostname,
            'device.kuberos.io/uuid': str(self.uuid),
            'device.kuberos.io/group': onboard_computer_group,
            'robot.kuberos.io/name': robot_name,
            'robot.kuberos.io/id': robot_id,
        }
        self.labels = labels
        self.shared = shared
        self.kuberos_role = getattr(self.ROLE_CHOICES, kuberos_role.upper())
        self.device_group = onboard_computer_group
        self.peripheral_devices = periphal_devices
        self.kuberos_registered = True
        self.is_label_synced = False
        self.save()


    def update_labels_for_fleet(self, 
                                fleet_name: str,
                                fleet_node_uuid: str,
                                ) -> None:
        """
        After the node is assigned or removed from a fleet.
        Label the node with fleet name and fleet node uuid. 
        Keep the consistency with the fleet node. 
        Mainly for debugging purpose directly with kubectl. 
        """
        self.labels['fleet.kuberos.io/name'] = fleet_name
        self.labels['fleet.kuberos.io/uuid'] = fleet_node_uuid
        self.is_label_synced = True
        self.save()


    def clean_labels_on_fleet_node_delete(self) -> None:
        """
        Clean the labels on the cluster node after the fleet is deleted
        """
        self.labels['fleet.kuberos.io/name'] = ''
        self.labels['fleet.kuberos.io/uuid'] = ''
        self.is_label_synced = True
        self.save()


    def update_status(self, status) -> None:
        """
        Update the node status
        """
        self.node_state = status
        self.last_sync_time = timezone.now()
        self.save()

    def update_sync_timestamp(self) -> None:
        """ Update last sync time """
        self.last_sync_time = timezone.now()
        self.save()

    def reset(self,
              soft_reset: bool = False) -> None:
        self.kuberos_registered = False
        self.is_alive = True
        self.kuberos_role = self.ROLE_CHOICES.UNASSIGNED
        self.save()

    def get_node_state(self) -> dict:
        """
        Return the node state for general purpose
        Like as the response for the request via REST API
        """
        state = {
            "available": self.is_available(),
            'computer_group': self.device_group,
            'peripheral_devices': self.peripheral_devices,
            'is_alive': self.is_alive,
            'ready': self.get_node_readiness(),
            'architecture': self.node_state['nodeInfo'].get('architecture', 'Unknown'),
            'kubelet_version': self.node_state['nodeInfo'].get('kubeletVersion', 'Unknown'),
            'container_runtime_version': self.node_state['nodeInfo'].get('containerRuntimeVersion', 'Unknown'),
            # 'cached_images': self.status['images']
        }
        return state

    def get_node_state_for_scheduling(self) -> dict:
        """
        Get the node state for scheduling
        For edge and cloud node
        """
        state = {
            'hostname': self.hostname, 
            'uuid': str(self.uuid), 
            'shared_resource': self.is_shared,
            'node_status': 'ready', 
            'cluster_node_state': self.get_node_state()
        }
        return state


    def get_node_readiness(self) -> bool:
        for condition in self.node_state['conditions']:
            if condition['type'] == 'Ready':
                return condition['status']
        return False

    def is_available_edge_node(self) -> bool:
        if self.kuberos_role == self.ROLE_CHOICES.EDGE and self.is_available():
            return True
        else:
            return False

    @property
    def peripheral_device_name_list(self) -> list:
        """
        Return the list of peripheral device names
        """
        if self.peripheral_devices is None:
            return []
        else:
            return [dev['deviceName'] for dev in self.peripheral_devices]

    @property
    def robot_name(self) -> str:
        """
        Return the robot name
        """
        if self.kuberos_role == self.ROLE_CHOICES.ONBOARD:
            return self.labels['robot.kuberos.io/name']
        return ''

    @property
    def robot_id(self) -> str:
        """
        Return the robot id, if the cluster node is onboard
        """
        if self.kuberos_role == self.ROLE_CHOICES.ONBOARD:
            return self.labels['robot.kuberos.io/id']
        return ''

    @property
    def assigned_fleet_name(self):
        """
        Return the fleet name if the onboard node is assigned to a fleet
        """
        if self.kuberos_role == self.ROLE_CHOICES.ONBOARD:
            return self.labels.get('fleet.kuberos.io/name', None)
        else:
            return None
    
    @property
    def is_shared(self) -> bool:
        """
        Return True is the node resource can be shared
        """
        if self.kuberos_role in [self.ROLE_CHOICES.EDGE, self.ROLE_CHOICES.CLOUD]:
            return self.shared
        return False

    @property
    def edge_cloud_resource_group(self):
        if self.kuberos_role in [self.ROLE_CHOICES.EDGE, self.ROLE_CHOICES.CLOUD]:
            return self.resource_group
        else:
            return None
    
    @property
    def node_info(self):
        return self.node_state.get('node_info', None)
    

class ContainerRegistryAccessToken(UserRelatedBaseModel):
    """
    Container registry for cluster
    
    You have may have a private container registry in your organization.
    
    To enable KubeROS to pull the image in each managed cluster, you need only to 
    upload the access token from your container registry into KubeROS. 
    
    KubeROS will encode the access token and inject it into the cluster as a secret.    
    """

    name = models.CharField(
        max_length=255,
        null=False,
        blank=False,
        verbose_name="token name",
        help_text='Name of secret in cluster. Must be unique within a namespace.'
        )

    # User name in your container registry
    user_name = models.CharField(
        max_length=64,
        null=False,
        blank=False,
        help_text='Your user name for container registry'
    )

    # Container registry url
    registry_url = models.CharField(
        max_length=1024,
        null=False,
        blank=False,
        help_text='Container registry url, e.g. <domain.com>/<registry>: 5050'
    )

    # Access token
    # Your Access token with at least read permission
    # After saving, the token cannot be retrieved by the user.
    # User can only renew the token! 
    # TODO: Trigger the token update process for related clusters.
    token = models.CharField(
        max_length=64,
        null=False,
        blank=False,
        help_text='Access token for container registry. \
                   ACCESS TOKEN ONLY! DONOT GIVE YOUR PASSWORD!'
    )

    # fulfill by KubeROS
    # User can not retrieve the encoded secret
    encoded_secret = models.TextField(
        blank=True,
        null=True,
        help_text='Encoded secret (base64 encoded token name and token)'
    )

    # comments
    description = models.TextField(
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = 'Container Registry'
        verbose_name_plural = 'Container Registries'
        ordering = ['name', 'created_time']
        constraints = [
            models.UniqueConstraint(fields=['name', 'created_by'],
                                    name='unique_token_name_with_user')
        ]

    def __str__(self) -> str:
        return _(self.name)

    def get_encode_docker_auth(self):
        """
        Encode the docker auth for k8s secret
        ref: https://kubernetes.io/docs/tasks/configure-pod-container/pull-image-private-registry/
        
        Return:
            base64 encoded docker string
        
        """
        encoded_auth = base64.b64encode(
            bytes('{}:{}'.format(self.user_name, self.token), 'utf-8')).decode('utf-8')
        dockerconfigjson = {
            "auths": {
                self.registry_url: {
                    "auth": encoded_auth, # self.token,
                    # "username": self.user_name
                }
            }
        }
        string = str(dockerconfigjson)
        string = string.replace(" ","").replace("'","\"")
        
        # logger.debug(string)
        
        # save in database
        self.encoded_secret = encoded_auth
        self.save()
        
        return base64.b64encode(
            bytes(string, 'utf-8')).decode('utf-8')


class ClusterSyncLog(BaseModel):
    """
    Cluster Synchronize Log
    Logging the result of tasks executed by KubeROS in the cluster. 
        - Sync failed 
        - Found new node
        - Node became not reachable or not ready
    """

    class LoggingType(models.IntegerChoices):
        SYNC_FAILED = 1, _('cluster sync failed')
        FOUND_NEW_NODES = 2, _('found_new_nodes')
        NODE_LOST = 3, _('node_lost')
        UNKNOWN = 4, _('unknown new category')

    class LoggingLevel(models.IntegerChoices):
        INFO = 1, 'info'
        SUCCESS = 2, 'success'
        WARNING = 3, 'warning'
        FAILED = 4, 'failed'
        FATAL = 5, 'fatal'

    logging_type = models.IntegerField(
        choices=LoggingType.choices,
        default=LoggingType.UNKNOWN
    )

    level = models.IntegerField(
        choices=LoggingLevel.choices,
        default=LoggingLevel.INFO
    )

    message = models.JSONField(
        blank=True,
        null=True,
    )

    cluster = models.ForeignKey(
        Cluster,
        related_name='sync_log_set',
        on_delete=models.CASCADE
    )

    def __str__(self):
        return '{} - {} - {}'.format(self.cluster.cluster_name, self.logging_type, self.level)

    @classmethod
    def log_sync_error(cls,
                       cluster: Cluster,
                       errors: Union[dict, list]) -> None:
        sync_log = cls.objects.create(
            cluster=cluster,
            logging_type=cls.LoggingType.SYNC_FAILED,
            level=cls.LoggingLevel.FAILED,
            message=errors
        )

    @classmethod
    def log_found_new_nodes(cls,
                            cluster: Cluster,
                            new_node_name_list: list) -> None:
        sync_log = cls.objects.create(
            cluster=cluster,
            logging_type=cls.LoggingType.FOUND_NEW_NODES,
            level=cls.LoggingLevel.INFO,
            message=f'Found new node {new_node_name_list}'
        )
