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
logger.propagate = False


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
        # Check whether the cluster is valid
        exec_clusters, non_exist_clusters = self.check_the_cluster_existences(meta_data['execClusters'])
        if len(non_exist_clusters) > 0:
            response.set_failed(
                reason='ClusterNotExist',
                err_msg=f'Following clusters <{non_exist_clusters}> do not exist.'
            )
            return Response(response.to_dict(),
                            status=status.HTTP_202_ACCEPTED)
        
        # create batch job deployment
        batch_job_dep = BatchJobDeployment.objects.create(
            name=meta_data['name'],
            subname=meta_data.get('subname', ''),
            created_by=request.user,
            deployment_manifest=manifest_dict,
            job_spec=job_spec,
            startup_timeout = job_spec.get('startupTimeout', DEFAULT_STARTUP_TIMEOUT),
            running_timeout = job_spec.get('runningTimeout', DEFAULT_RUNNING_TIMEOUT),
        )
        
        # volume 
        volume_spec = job_spec.get('volume', None)
        if volume_spec:
            host_path = f"/kuberos/data/batchjobs/{meta_data['name']}"
            volume = self.parse_volume(volume_spec=volume_spec, 
                                           host_path=host_path,
                                           subpath=f"{batch_job_dep.name}__{batch_job_dep.subname}")
        else:
            volume = {}
        batch_job_dep.volume_spec = volume
        batch_job_dep.save()    
        
        
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

        bj_status = bj_dep.status
        
    
        ### Stop the batch job
        if cmd == 'stop':
            logger.info(f"Stopping batch job <%s>", batch_job_name)
            
            # reject if the batch job is not running
            if bj_status != BatchJobDeployment.StatusChoices.EXECUTING:
                response.set_rejected(
                    reason='BatchJobNotRunning',
                    err_msg=f'Batch job deployment <{batch_job_name}> is in status <{bj_status}>. Cannot stop it.'
                )
                return Response(response.to_dict(), status=status.HTTP_202_ACCEPTED)
            
            else:
                bj_dep.switch_status_to_stopped()
                response.set_accepted(
                    msg=f"Request accepted, Stopping batch job <{batch_job_name}>"
                )
                return Response(response.to_dict(),
                                status=status.HTTP_200_OK)
        
        ### Resume the batch job
        if cmd == 'resume':
            logger.info(f"Resuming batch job <%s>", batch_job_name)
            
            # reject if the batch job is not running
            if bj_status != BatchJobDeployment.StatusChoices.STOPPED:
                response.set_rejected(
                    reason='BatchJobNotInStoppedStatus',
                    err_msg=f'Batch job deployment <{batch_job_name}> is in status <{bj_status}>. Cannot resume it.'
                )
                return Response(response.to_dict(), status=status.HTTP_202_ACCEPTED)
            
            else:
                bj_dep.switch_status_back_to_executing()
                batch_job_deployment_control.delay(
                    batch_job_dep_uuid=bj_dep.get_uuid()
                )
                response.set_accepted(
                    msg=f"Request accepted, Resuming batch job <{batch_job_name}>"
                )
                return Response(response.to_dict(),
                                status=status.HTTP_200_OK)


    def delete(self, request, batch_job_name):
        """
        Delete the batch jobs by name
        """
        # is_hard_delete = request.data.get('hard_delete', False)
        # if is_hard_delete == 'true':
        #     is_hard_delete = True
        is_hard_delete = True if request.data['hard_delete'] == 'True' else False
        
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
        
        # delete the batch jobs
        if is_hard_delete:
            logger.info(f"Delete batch job <%s> from database!", batch_job_name)
            bj_dep.delete()
            response.set_success(
                msg=f"Hard deleting batch job <{batch_job_name}> successfully! Deleted from database."
            )
            return Response(response.to_dict(),
                            status=status.HTTP_200_OK)

        # soft delete
        bj_status = bj_dep.status
        if bj_status not in [BatchJobDeployment.StatusChoices.PENDING,
                             BatchJobDeployment.StatusChoices.COMPLETED,
                             BatchJobDeployment.StatusChoices.FAILED]:
            bj_dep.switch_status_to_cleaning()
            # trigger the deleting process
            batch_job_deployment_control.delay(
                    batch_job_dep_uuid=bj_dep.get_uuid()
                )
            response.set_accepted(
                msg=f"Request accepted, Deleting batch job <{batch_job_name}>, Current state: {bj_status}"
            )
            return Response(response.to_dict(),
                            status=status.HTTP_202_ACCEPTED)
            
        bj_dep.is_active = False
        bj_dep.save()
        response.set_success(
            msg=f"Soft deleting batch job <{batch_job_name}> successfully!"
        )
        return Response(response.to_dict(),
                        status=status.HTTP_200_OK)
        
    
    def check_the_cluster_existences(self, cluster_list):
        """
        Check whether the clusters exist
        """
        exist_clusters = []
        non_exist_clusters = []
        for cluster_name in cluster_list:
            try:
                cluster = Cluster.objects.get(cluster_name=cluster_name)
                exist_clusters.append(cluster)
            except Cluster.DoesNotExist:
                non_exist_clusters.append(cluster_name)
        return exist_clusters, non_exist_clusters

        
    @staticmethod
    def parse_volume(volume_spec: dict, host_path: str, subpath: str) -> dict:
        """
        Parse volume spec
        """
        if not volume_spec:
            return {}

        volume_name = volume_spec.get('name', 'temp-volume-for-batchjob')

        volume = {}
        volume_mount = {}
        if volume_spec['type'] == 'localhost':
            volume = {
                'name': volume_name,
                'hostPath': {
                    'path': host_path,
                    'type': 'DirectoryOrCreate'
                }
            }
            volume_mount = {
                'name': volume_name,
                'mountPath': volume_spec['mountPath'],
            }
        
        if volume_spec['type'] == 'nfs':
            
            root_path = volume_spec.get('nfsRootPath', '/srv/nfs4')
            
            volume = {
                'name': 'nfs-volume',
                'nfs': {
                    'server': volume_spec['nfsServer'],
                    'path': root_path
                }
            }
            volume_mount = {
                'name': 'nfs-volume',
                'mountPath': volume_spec['mountPath'],
                # 'readOnly': 'no',
                'subPath': subpath
            }

        return {
            'volume': volume,
            'volume_mount': volume_mount,
            'type': volume_spec['type'],
        }


class BatchJobDataManagementViewSet(viewsets.ViewSet):
    
    def retrieve(self, request, batch_job_name):
        """
        Request to collect the batch job data
        """
        
        response = KuberosResponse()
        
        try:
            batch_job = BatchJobDeployment.objects.get(name=batch_job_name,
                                                       is_active=True)
            
            volume_spec = batch_job.get_volume_spec()
            response.set_data(volume_spec)
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
            
