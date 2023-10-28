# Django
from django.urls import path

# KubeROS
from main.api.cluster_operating import(
	ClusterInventoryManagementViewSet,
     ContainerRegistryAccessTokenManagementViewSet,
 
)

urls = [
	path('cluster_inventory_management/',
		ClusterInventoryManagementViewSet.as_view(
               {
                    'post': 'post',
               }
     )),
     
     path('cluster_inventory_management/<str:cluster_name>/',
          ClusterInventoryManagementViewSet.as_view(
               {
                    'delete': 'reset',
               }
     )),

    path('container_registry_access_token/', 
         ContainerRegistryAccessTokenManagementViewSet.as_view(
            {
                'post': 'post',
                'get': 'get',   
            }
    )),
]
