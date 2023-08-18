# Django
from django.urls import path

#KubeROS
from main.api.clusters import (
    ClusterViewSet,
    ClusterNodeViewSet,
    ListFreeClusterNodeView,
    ContainerRegistryAccessTokenViewSet
)

urls = [
    # Clusters
    path('clusters/', ClusterViewSet.as_view(
        {
            'get': 'list',
            'post': 'create'
        }
    )), 
    path('clusters/<str:cluster_name>/', ClusterViewSet.as_view(
        {
            'get': 'retrieve',
            'delete': 'delete'
        }
    )),
    
    # Cluster Nodes
    path('cluster_nodes/', ClusterNodeViewSet.as_view(
        {
            'get': 'list',
            'post': 'create',
        }
    )),
    path('cluster_nodes/<str:uuid>/', ClusterNodeViewSet.as_view(
        {
            'get': 'retrieve',
        }
    )),
    
    path('list_free_cluster_nodes/', ListFreeClusterNodeView.as_view()),
    
    
    # Container Registry Access Tokens
    path('container_registry_access_tokens/', ContainerRegistryAccessTokenViewSet.as_view(
        {
            'get': 'list',
            'post': 'create'
        }
    )),
    path('container_registry_access_tokens/<str:uuid>/', ContainerRegistryAccessTokenViewSet.as_view(
        {
            'get': 'retrieve',
        } 
    )),
]
