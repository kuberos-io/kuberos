# Python 

# Django 
from django.db import models


# KubeROS 
from .base import UserRelatedBaseModel

__all__ = [
    'HostCredential',
    'Host',
]



### Credential
class HostCredential(UserRelatedBaseModel):
    
    CREDENTIAL_TYPE_CHOICES = (
    ('password', 'Password'),
    ('ssh', 'SSH')
    )
    
    name = models.CharField(
        max_length=255, 
        null=False, 
        blank=False, 
        verbose_name="name"
    )
    
    credential_type = models.CharField(
        max_length=32, 
        choices=CREDENTIAL_TYPE_CHOICES, 
        default='password',
    )
    username = models.CharField(
        max_length=64, 
        null=True,
        blank=True,
        verbose_name='username',
    )
    password = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        verbose_name='password'
    )
    ssh_public=models.CharField(
        max_length=2048, 
        null=True, 
        blank=True,
    )
    ssh_private=models.CharField(
        max_length=2048, 
        null=True, 
        blank=True,
    )
    # TODO Description
    
    class Meta: 
        abstract=False



class Host(UserRelatedBaseModel):
    
    HOST_OS_TYPE_CHOICES = (
        ('ubuntu20', 'Ubuntu 20.04'),
        ('ubuntu18', 'Ubuntu 18.04'),
        ('ubuntu22', 'Ubuntu 20.04'),
    )
    DEVICE_TYPE_CHOICES = (
        ('onboard_main', 'Onboard Main Device'), 
        ('onboard_secondary', 'Onboard Secondary Device'),
        ('edge', 'Edge VM'),
        ('cloud', 'Cloud VM'),
    )
    
    # TODO: Change to hostname 
    name = models.CharField(
        max_length=255, 
        null=False, 
        blank=False, 
        verbose_name="name"
        )
    
    
    # Meta
    device_type = models.CharField(
        max_length=32,
        choices=DEVICE_TYPE_CHOICES, 
        default='onboard_main',
    )
    
    # Hardware information
    os = models.CharField(
        max_length=32, 
        choices=HOST_OS_TYPE_CHOICES, 
        default='ubuntu20',
    )
    cpu_core_num = models.IntegerField(
        default=4
    )
    
    # Network
    ip_v4_public = models.GenericIPAddressField(
        protocol='IPv4',
    )
    ip_v4_in_cluster = models.GenericIPAddressField(
        protocol='IPv4',
        blank=True, 
        null=True
    )
    
    # Access
    main_credential = models.ForeignKey(
        HostCredential, 
        related_name='host_main_credential',
        null=True,
        on_delete=models.SET_NULL,
    )
    credentials = models.ManyToManyField(
        HostCredential,
        related_name='host_credentials',
    )
    
    # Status
    is_in_cluster = models.BooleanField(
        default=False
    )
    is_online = models.BooleanField(
        default=False
    )
    
    # Health check started 
    # Health check pending 
    # last health check 
    
    # Errors 
    
    
    def get_host_config(self):
        pass
    
    def get_host_credential(self):
        # Get host credential for various purpose: adding to cluster, execute bash script etc.
        pass
    
    def check_host_liveness(self):
        pass
    
    