# Django
from django.urls import path

#KubeROS
from main.api.clusters import (
    ClusterViewSet,
    ClusterNameListView,
    ClusterNodeViewSet,
    ListFreeClusterNodeView,
    ContainerRegistryAccessTokenViewSet,
    RegistryTokenNameListView,
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
    
    # Cluster name list for auto completion
    path('clusters_name_list/', 
         ClusterNameListView.as_view()
    ),
    
    path('registry_token_name_list/',
        RegistryTokenNameListView.as_view()     
    ),
    
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
    
    path('container_registry_access_tokens/<str:token_name>/', ContainerRegistryAccessTokenViewSet.as_view(
        {
            'get': 'retrieve',
            'delete': 'delete',
        } 
    )),
]
