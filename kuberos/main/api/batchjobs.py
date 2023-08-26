# Python
import logging

# Django
from rest_framework import permissions, viewsets, status
from rest_framework.response import Response

# KubeROS
from main.models import(
    Cluster,
    BatchJobDeployment
)

from main.serializers.batchjobs import (
    BatchJobDeploymentSerializer
)

from main.api.base import KuberosResponse

from main.tasks.batch_job_controller import (
    batch_job_deployment_control
)


logger = logging.getLogger('kuberos.main.api')


DEFAULT_STARTUP_TIMEOUT = 66
DEFAULT_RUNNING_TIMEOUT = 188


class BatchJobDeploymentViewSet(viewsets.ViewSet):

    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        """
        List all active deployments
        
        GET /api/<version>/batchjobs/batchjobs/
        """

        response = KuberosResponse()

        deployments = BatchJobDeployment.objects.filter(created_by=request.user, is_active=True)
        serializer = BatchJobDeploymentSerializer(deployments, many=True)

        response.set_data(serializer.data)
        response.set_success()

        return Response(response.to_dict(), 
                        status=status.HTTP_200_OK)
        
    def post(self, request):
        """
        Create batch jobs
        """
        
        response = KuberosResponse()
        
        # using json format
        manifest_dict = request.data.get('deployment_manifest', None)

        if manifest_dict is None:
            response.set_failed(
                reason='InvalidDeploymentManifest',
                err_msg='Invalid deployment manifest.'
            )
            return Response(response.to_dict(),
                            status=status.HTTP_202_ACCEPTED)
            
        meta_data = manifest_dict.get('metadata', None)
        batch_job_dep_name = meta_data.get('name', None)
        
        # Check batch job name
        existed_batch_jobs = BatchJobDeployment.objects.filter(name=batch_job_dep_name, 
                                                               is_active=True)
        if len(existed_batch_jobs) > 0:
            response.set_failed(
                reason='DeploymentAlreadyExists',
                err_msg=f'Deployment <{batch_job_dep_name}> already exists.'
            )
            return Response(response.to_dict(),
                            status=status.HTTP_202_ACCEPTED)
            
        job_spec = manifest_dict.get('jobSpec', None)
        
        # Get cluster list
        # TODO: check whether the cluster is valid
        exec_clusters = []
        for cluster in meta_data['execClusters']:
            cluster_obj = Cluster.objects.get(cluster_name=cluster)
            exec_clusters.append(cluster_obj)

        # create batch job deployment
        batch_job_dep = BatchJobDeployment.objects.create(
            name=meta_data['name'],
            created_by=request.user,
            deployment_manifest=manifest_dict,
            job_spec=job_spec,
            startup_timeout = job_spec.get('startupTimeout', DEFAULT_STARTUP_TIMEOUT),
            running_timeout = job_spec.get('runningTimeout', DEFAULT_RUNNING_TIMEOUT),
        )
        
        # Add clusters 
        for cluster in exec_clusters:
            batch_job_dep.exec_clusters.add(cluster)
        # save
        batch_job_dep.save()
        
        # dispatch to job controllers
        batch_job_deployment_control.delay(
            batch_job_dep_uuid=batch_job_dep.get_uuid()
        )
        
        response.set_accepted(
            msg=f"Request accepted, created batch job <{batch_job_dep.name}> -> Scheduling jobs"
        )
        
        return Response(response.to_dict(),
                        status=status.HTTP_200_OK)
        
    def list(self, request):
        """
        List all batch jobs
        GET /api/<version>/batchjobs/batchjobs/
        """
        
        response = KuberosResponse()
        
        batch_job_deps = BatchJobDeployment.objects.filter(
            created_by=request.user,
            is_active=True)
        serializer = BatchJobDeploymentSerializer(batch_job_deps, many=True)
        
        response.set_data(serializer.data)
        response.set_success()
        
        return Response(response.to_dict(),
                        status=status.HTTP_200_OK)
        
    
    def retrieve(self, request, batch_job_name):
        """
        Get batch job status by batch_job_name
        """
            
        response = KuberosResponse()
        
        try:
            batch_job = BatchJobDeployment.objects.get(name=batch_job_name,
                                                       is_active=True)
            
            serializer = BatchJobDeploymentSerializer(batch_job)
            
            response.set_data(serializer.data)
            response.set_success()
            return Response(response.to_dict(),
                            status=status.HTTP_200_OK)
        
        # return error msg, if the batch job does not exist
        except BatchJobDeployment.DoesNotExist:
            logger.warning(f'Batch job {batch_job_name} does not exist')
            response.set_failed(
                reason='BatchJobDeploymentNotExist',
                err_msg=f'Batch job {batch_job_name} does not exist'
            )
            return Response(response.to_dict(),
                            status=status.HTTP_202_ACCEPTED)
    
    
    def patch(self, request, batch_job_name):
        """
        Stop / resume the batch jobs by name
        """
        response = KuberosResponse()
        cmd = request.data.get('cmd', None)
        
        # reject if cmd is not provided correctly
        if cmd not in ['stop', 'resume']: 
            response.set_rejected(
                reason='InvalidCommand',
                err_msg=f"Invalid command <{cmd}>. Supported: 'stop', 'resume'")
            return Response(response.to_dict(),
                            status=status.HTTP_202_ACCEPTED)
        
        # get the batch job
        try:
            bj_dep = BatchJobDeployment.objects.get(
                name=batch_job_name,
                is_active=True,
            )
        except BatchJobDeployment.DoesNotExist:
            response.set_rejected(
                reason='BatchJobDeploymentNotExist',
                err_msg=f'Batch job deployment <{batch_job_name}> does not exist.'
            )
    
        # stop the batch job
        if cmd == 'stop':
            print("Stop the batch job")
            
            response.set_success()
            return Response(response.to_dict(),
                            status=status.HTTP_200_OK)
        
        if cmd == 'resume':
            print("Resume the batch job")
            
            response.set_success()
            return Response(response.to_dict(),
                            status=status.HTTP_200_OK)
        

    def delete(self, request, batch_job_name):
        """
        Delete the batch jobs by name
        """
        
        response = KuberosResponse()
        
        try:
            bj_dep = BatchJobDeployment.objects.get(
                name=batch_job_name,
                is_active=True
            )
        except BatchJobDeployment.DoesNotExist:
            # return error msg
            response.set_failed(
                reason='BatchJobDeploymentNotExist',
                err_msg=f'Batch job deployment <{batch_job_name}> does not exist.'
            )
            return Response(response.to_dict(),
                            status=status.HTTP_202_ACCEPTED)
        
        # terminate and delete the batch jobs
        bj_dep.delete()
        response.set_success()
        
        return Response(response.to_dict(),
                        status=status.HTTP_200_OK)
