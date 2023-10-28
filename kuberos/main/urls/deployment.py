# Django
from django.urls import path

#KubeROS
from main.api.deployment import (
    DeploymentViewSet,
    DeploymentNameListView,
    DeploymentAdminViewSet
)

urls = [

    path('deployments/', DeploymentViewSet.as_view(
        {
            'get': 'list',
        }
    )),

    path('deployments/<str:deployment_name>/', DeploymentViewSet.as_view(
        {
            'get': 'retrieve',
        }
    )),
    
    # deployment name list for auto completion
    path('deployments_name_list/', 
         DeploymentNameListView.as_view()
    ),

    # Interface for the system admin to delete the deployment that is in stuck status.
    path('admin_only/deployments/<str:deployment_name>/', DeploymentAdminViewSet.as_view(
        {
            'delete': 'delete',
        }
    )),
]
