# Django
from django.urls import path

# KubeROS
from main.api.deploying import(
    DeployRosModuleViewSet,
)

urls = [
    path('deploy_rosmodule/', 
        DeployRosModuleViewSet.as_view({
            'post': 'post',     
        })
    ),
    
    path('deploy_rosmodule/<str:deployment_name>/', 
        DeployRosModuleViewSet.as_view({
            'delete': 'delete',
            'patch': 'update',
        })
    ),
]
