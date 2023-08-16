"""
All of interactions with the Kubernetes cluster are implemented as Celery tasks. 
This is the only interface between KubeROS and Kubernetes cluster. 
The tasks can be executed directly without using Celery, and can be executed 
by using Celery as well. 
"""

# Python
import logging

# Django 
from django.db import transaction

# Pykuberos
from pykuberos.kuberos_executer import KubernetesExecuter

# Celery
from celery import shared_task, Task
from pykuberos.kubernetes_client import KubernetesClient
from main.tasks.base import KubeROSBaseTask

from main.models import Cluster, ClusterNode, ClusterSyncLog


logger = logging.getLogger('kuberos.main.tasks')



def convert_list_to_key_based_dict(
    list_of_dict: list,
    key: str,
):
    """
    Convert a list of dict to a key based dict.
    """
    dict_ = {}
    for item in list_of_dict:
        dict_[item[key]] = item
    return dict_


@shared_task
def update_cluster_node_labels(cluster_config: dict,
                               selected_nodes: list = None) -> None:
    """
    Update the node labels in the K8s cluster.
    
    Args:
        cluster_config: dict - contains the cluster api, credentials, etc.
        selected_nodes: list - the list of node names to be updated.
        
    Return: 
        response: dict - generic response format
    """

    logger.debug("Celery Task - Update cluster node labels. %s", cluster_config['name'])

    cluster = Cluster.objects.get(cluster_name=cluster_config['name'])

    kube_exec = KubernetesExecuter(cluster_config)

    for cluster_node in cluster.cluster_node_set.filter(is_label_synced=False):
        # print(cluster_node)
        response = kube_exec.label_node(
                    node_name = cluster_node.hostname,
                    labels = cluster_node.labels)

        if response['status'] == 'success':
            # confirm the update result
            cluster_node.check_label_update_result(response['data'])

        else:
            # update failed
            logger.error("Celery Task - Update cluster node labels failed.")
            logger.error("Error: %s", response['errors'])
            cluster_node.cluster.report_error(errors=response['errors'])
            ClusterSyncLog.log_sync_error(
                cluster=cluster,
                errors=response['errors']
            )


class SyncKubernetesClusterBaseTask(Task):
    """
    Base task class for sync kubernetes cluster. 
    """
    
    def on_success(self, retval, task_id, args, kwargs):
        """
        If the task is successful, update the cluster node status in KubeROS DB.
        args: 
            args: input arguments from the task. The first one is the cluster config dict. 
        """
        print("ON SUCCESS")
        return super().on_success(retval, task_id, args, kwargs)
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """
        Problems that may occur:
            - Kubernetes cluster is not reachable.
            - Labeling of nodes is failed.
        
        How to handle the failure? 
            - Cluster Logs: Add a log history to the clusters. 
            
        Args: 
            exc: The exception raised by the task.
        Return:
            - Set the cluster status to 'warning'.
            - Report the error message. 
            
        """
        print("ON FAILURE")
        super().on_failure(exc, task_id, args, kwargs, einfo)
        
        return {
                'data': 'None',}
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        return super().on_retry(exc, task_id, args, kwargs, einfo)



@transaction.atomic
def process_nodes(cluster: Cluster,
                  kube_nodes: list):
    """
    Process all nodes returned from Kubernetes cluster. 
    
    Args: 
        - cluster: Cluster - the cluster instance in the DB
        - kube_nodes: list - the list of nodes returned from Kubernetes cluster.
    """
    
    new_nodes_name_list = []
    
    # get the list of known nodes in KubeROS database
    known_node_name_list = cluster.get_cluster_node_name_list()
    
    for node in kube_nodes:
        if node['name'] not in known_node_name_list:
            # add the new ndoe to the cluster in the database
            ClusterNode.objects.create(
                cluster=cluster,
                hostname=node['name'],
                labels=node['labels'],
                node_state=node['status'],
                is_alive=node['ready']
            )
            logger.info("Add new node <%s> to cluster <%s>.",
                        {node['name']}, {cluster.cluster_name})
            new_nodes_name_list.append(node['name'])
        else:
            # update the node status
            kros_node = ClusterNode.objects.get(hostname=node['name'], cluster=cluster)
            kros_node.update_status(node['status'])

    # add log, if new nodes are found
    if len(new_nodes_name_list) > 0:
        ClusterSyncLog.log_found_new_nodes(
            cluster=cluster,
            new_node_name_list=new_nodes_name_list
        )


@shared_task
def sync_kubernetes_cluster(
    cluster_config: dict
) -> dict:
    """
    Synchronize the Kubernetes cluster with the KubeROS platform.
    
    Args:
        cluster_config: dict - contains the cluster api, credentials, etc.
    
    Return: 
        response: dict - generic response format

    This task is invoked:
        - periodically to sync the status of the cluster nodes.
        - before each deployment, check the status of the cluster nodes.
        - after new cluster is registered. 
    
    Possible failures:
        - api server is not reachable
        - invalid sa token
        - invalid ca cert
    """

    cluster = Cluster.objects.get(cluster_name=cluster_config['name'])

    # connect to the cluster and get the node list
    kube_exec = KubernetesExecuter(cluster_config)
    response = kube_exec.get_nodes_status()

    if response['status'] == 'success':
        cluster.update_sync_timestamp()
        kube_nodes = response['data']
        # process nodes: add new node to the KubeROS and update node status
        process_nodes(cluster, kube_nodes)

    else:
        # synchronization failed
        logger.error("Celery Task - Sync cluster <%s> failed.", cluster_config['name'])
        logger.error("Error: %s", response['errors'])

        # update the cluster status
        cluster.report_error(errors=response['errors'])
        ClusterSyncLog.log_sync_error(
            cluster=cluster,
            errors=response['errors']
        )
    return response



# @shared_task(base=KubeROSBaseTask)
@shared_task()
def manage_container_access_token(
        cluster_config: dict,
        secret_name: str,
        action: str = 'get',
        namespace: str = 'ros-default',
        config_json: dict = None,
    ):
    """
    manage container access token in Kubernetes cluster.
    """
    logger.debug("Celery Task - {} {} secret.".format(action, secret_name))
    kube_client = KubernetesClient(cluster_config)

    res = False,
    msg = ''
    if action == 'get':
        res, msg = kube_client.get_container_access_token(
            namespace=namespace,
            secret_name=secret_name, 
            docker_config_json=config_json,
        )
    elif action in ('create', 'update'):
        res, msg = kube_client.create_or_update_container_access_token(
            namespace=namespace,
            secret_name=secret_name, 
            docker_config_json=config_json,
            update=True if action == 'update' else False,
        )
    else:
        msg = f'Action {action} not supported.'
    return res, msg




# Notes:
# Why not use the class methods as tasks. Celery introduces the task_methods from 
# celery.contrib.methods. from 3.0, however it is deprecated since 4.0.
# due to too buggy as it could be useful.
# https://docs.celeryq.dev/en/3.1/reference/celery.contrib.methods.html


