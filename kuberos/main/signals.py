# Python 
import random
import string

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from main.models import (
    FleetNode,
    DeploymentEvent
)

def random_string(length=10):
    
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(length))


# update the deployment status 
@receiver(post_save, sender=DeploymentEvent)
def update_deployments(sender, instance, **kwargs):
    if instance.event_status == 'dispatched':
        if instance.event_type == 'deploy':
            instance.deployment.status = 'deploying'
        elif instance.event_type == 'delete':
            instance.deployment.status = 'deleting'
        elif instance.event_type == 'update':
            instance.deployment.status = 'updating'
        elif instance.event_type == 'scale':
            instance.deployment.status = 'scaling'
            pass # TODO: Implement api and task for scaling
        
    elif instance.event_status == 'failed':
        instance.deployment.status = 'failed'
        instance.deployment.alive = False
        
    elif instance.event_status == 'success':
        if instance.event_type == 'deploy':
            instance.deployment.status = 'active'
            instance.deployment.alive = True
        elif instance.event_type == 'delete':
            instance.deployment.status = 'deleted'
            instance.deployment.name = f'{instance.deployment.name}-{random_string(5)}'
            instance.deployment.alive = False
            instance.deployment.active = False
    
    instance.deployment.save()
    

@receiver(pre_delete, sender=FleetNode)
def clean_labels_on_fleet_node_delete(sender, instance, **kwargs):
    c_node = instance.cluster_node
    c_node.clean_labels_on_fleet_node_delete()
