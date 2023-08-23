# Django
from django.urls import path

# KubeROS
from main.api.batchjobs import(
    BatchJobDeploymentViewSet,
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
             'delete': 'delete'
         }))    

]
