# Django
from django.urls import path, include, re_path
# KubeROS
from main.api.hosts import(
    HostCredentialViewSet,
    HostViewSet
)

urls = [
    path('host_credentials/', HostCredentialViewSet.as_view(
        {
            'get': 'list',
            'post': 'create'
         }
    )),
    path('host_credentials/<str:uuid>/', HostCredentialViewSet.as_view(
        {
            'get': 'retrieve',    
        }
    )),
    path('hosts/', HostViewSet.as_view(
        {
            'get': 'list',
            'post': 'create'
        }
    ))
]
