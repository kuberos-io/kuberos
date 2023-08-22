# Python
import logging

# Django
from rest_framework import generics, permissions, viewsets, status
from rest_framework.response import Response

# KubeROS
from main.models import(
    Deployment, 
    DeploymentEvent
)
from main.serializers.deployments import (
    DeploymentSerializer,
)
from main.api.base import KuberosResponse


logger = logging.getLogger('kuberos.main.api')



class DeploymentViewSet(viewsets.ViewSet):

    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        """
        List all active deployments
        
        GET /api/<version>/deployment/deployments/
        """

        response = KuberosResponse()

        deployments = Deployment.objects.filter(created_by=request.user, active=True)
        serializer = DeploymentSerializer(deployments, many=True)

        response.set_data(serializer.data)
        response.set_success()

        return Response(response.to_dict(), 
                        status=status.HTTP_200_OK)


    def retrieve(self, request, deployment_name):
        """
        Get deployment status by deployment_name
        
        GET /api/<version>/deployment/deployments/<deployment_name>/
        """
        
        response = KuberosResponse()
        
        try:
            deployment = Deployment.objects.get(name=deployment_name,
                                                active=True)
            serializer = DeploymentSerializer(deployment)
            
            response.set_data(serializer.data)
            response.set_success()
            return Response(response.to_dict(),
                            status=status.HTTP_200_OK)
        
        # return error msg, if the deployment does not exist
        except Deployment.DoesNotExist:
            logger.warning(f'Deployment {deployment_name} does not exist')
            response.set_failed(
                reason='DeploymentDoesNotExist',
                err_msg=f'Deployment {deployment_name} does not exist'
            )
            return Response(response.to_dict(),
                            status=status.HTTP_202_ACCEPTED)


class DeploymentAdminViewSet(viewsets.ViewSet):

    permission_classes = [permissions.IsAdminUser]
    
    def delete(self, request, deployment_name):
        """
        Delete deployment directly in KubeROS database, 
        without checking the status of the deployment.
        
        For the case when the deployment is stuck in the deleting state 
        due to the unknown failure with Kubernetes.

        DELETE /api/<version>/deployment/admin_only/deployments/<deployment_name>/
        """
        
        response = KuberosResponse()

        try:
            deployment = Deployment.objects.get(name=deployment_name)
            deployment.delete()
            response.set_success(
                msg=f'Deleting the deployment {deployment_name} directly in database'
            )
            return Response(response.to_dict(),
                            status=status.HTTP_200_OK)

        # deployment not found
        except Deployment.DoesNotExist:
            logger.warning(f'Deployment {deployment_name} does not exist')
            response.set_failed(
                reason='DeploymentDoesNotExist',
                err_msg=f'Deployment {deployment_name} does not exist'
            )
            return Response(response.to_dict(),
                            status=status.HTTP_202_ACCEPTED)
