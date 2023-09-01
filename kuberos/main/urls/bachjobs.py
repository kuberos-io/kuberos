# Django
from django.urls import path

# KubeROS
from main.api.batchjobs import (
    BatchJobDeploymentViewSet,
    BatchJobDataManagementViewSet,
)

urls = [
    path('batch_jobs/',
         BatchJobDeploymentViewSet.as_view({
             'get': 'list',
         })
         ),

    path('batch_jobs/<str:batch_job_name>/',
         BatchJobDeploymentViewSet.as_view({
             'get': 'retrieve',
             'patch': 'patch',
             'delete': 'delete'
         })
         ),
    
    path('data_management/<str:batch_job_name>/',
         BatchJobDataManagementViewSet.as_view({
             'get': 'retrieve',
         })
         )
]
