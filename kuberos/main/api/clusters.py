# Python
import logging

# Django
from rest_framework import generics, permissions, viewsets, status
from rest_framework.response import Response

# KubeROS
from main.models import(
    Cluster,
    ClusterNode,
    ContainerRegistryAccessToken
)
from main.serializers.clusters import (
    ClusterSerializer,
    ClusterNodeSerializer,
    ContainerRegistryAccessTokenSerializer
)
from main.tasks.cluster_operating import (
    sync_kubernetes_cluster
    )
from main.api.base import KuberosResponse


logger = logging.getLogger('kuberos.main.api')



class ClusterViewSet(viewsets.ViewSet):
    """
    Cluster View Set provides create, list, retrieve, and delete the managed clusters.
    """

    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        """
        List all clusters
        
        GET /api/clusters/
        """
        
        response = KuberosResponse()
        
        clusters = Cluster.objects.filter(created_by=request.user)
        serializer = ClusterSerializer(clusters, many=True)
        
        response.set_data(serializer.data)
        response.set_success()
        
        return Response(response.to_dict(),
                        status=status.HTTP_200_OK)


    def create(self, request):
        """
        Register a new cluster in KubeROS platform
        
        POST /api/clusters/
        """

        logger.debug('Received request to register a new cluster in KubeROS')
        logger.debug('Received data: %s', request.data)

        response = KuberosResponse()

        # check whether the cluster is already registered
        cluster_name = request.data['cluster_name']
        clusters = Cluster.objects.filter(cluster_name=cluster_name)
        if len(clusters) > 0:
            response.set_rejected(
                reason='ClusterAlreadyRegistered',
                err_msg=f'Cluster <{cluster_name}> is already registered in KubeROS.'
            )
            return Response(response.to_dict(), status=status.HTTP_202_ACCEPTED)

        # serialize the data
        serializer = ClusterSerializer(
            data=request.data,
            context={
                'created_by': request.user, 
            },
            partial=False
        )
        # logger.debug("Serializer: %s", serializer)

        # check the validation
        if not serializer.is_valid():
            # return failed response
            logger.error(serializer.errors)
            response.set_failed(
                reason='ValidationFailed',
                err_msg=f'Cluster validation error - {serializer.errors}'
            )
            return Response(response.to_dict(),
                            status=status.HTTP_202_ACCEPTED)

        # save the data
        serializer.save()
        response.set_data(serializer.data)
        response.set_success(
            msg='New cluster is registered in KubeROS'
        )

        # synchronize the new cluster state
        cluster = Cluster.objects.get(cluster_name=cluster_name)
        sync_kubernetes_cluster.delay(cluster_config=cluster.cluster_config_dict)

        return Response(response.to_dict(), 
                        status=status.HTTP_201_CREATED)


    def retrieve(self, request, cluster_name):
        """
        Get cluster status by cluster_name
        """
        # sync the cluster to get the latest status
        force_sync = request.data['sync'] ## type: str, value: 'True' or 'False'

        response = KuberosResponse()

        try:
            cluster = Cluster.objects.get(cluster_name=cluster_name)
            if force_sync == 'True':
                cluster_config = cluster.cluster_config_dict
                sync_res = sync_kubernetes_cluster(cluster_config=cluster_config)

                # return the error message if the sync failed
                if sync_res['status'] == 'failed':
                    for err in sync_res['errors']:
                        response.set_failed(
                            reason=err['reason'],
                            err_msg=err['err_msg']
                        )
                    return Response(
                        response.to_dict(),
                        status=status.HTTP_202_ACCEPTED)

            # return the cluster ojbect data
            cluster = Cluster.objects.get(cluster_name=cluster_name)
            serializer = ClusterSerializer(cluster)
            response.set_data(serializer.data)
            response.set_success()
            return Response(response.to_dict(),
                            status=status.HTTP_202_ACCEPTED)

        # return the error message if the cluster does not exist
        except Cluster.DoesNotExist:
            response.set_failed(
                reason='ClusterDoesNotExist',
                err_msg=f"Cluster <{cluster_name}> does not exist."
            )
            return Response(response.to_dict(), status=status.HTTP_202_ACCEPTED)


    def delete(self, request, cluster_name):
        """
        Delete the managed cluster from KubeROS
        
        Before deleting the cluster. Check the cluster status and related fleet. 
        If the cluster is used by a fleet, it cannot be deleted. 
        
        Deleting process:
            - trigger the celery task to remove the cluster labels
            - delete the cluster object
        """
        
        logger.debug("Request to delete the cluster in KubeROS: <%s>", cluster_name)
        
        response = KuberosResponse()
        
        try:
            cluster = Cluster.objects.get(cluster_name=cluster_name)
            
            # check the related fleet
            fleet_set = cluster.fleet_set.all()

            if len(fleet_set) > 0:
                # reject the deletetion
                fleet_name_list = [fleet.fleet_name for fleet in fleet_set]
                response.set_rejected(
                    reason='ClusterInUse',
                    err_msg=(f'The cluster is used by following fleet: {fleet_name_list} \n' 
                        f'Please delete the fleet first. ')
                )

            else:
                # delete the cluster
                cluster.delete()
                response.set_accepted(
                    msg=f'Deleting <{cluster.cluster_name}>'
                )

            return Response(response.to_dict(), status=status.HTTP_202_ACCEPTED)

        except Cluster.DoesNotExist:
            # return the error message
            response.set_failed(
                reason='ClusterDoesNotExist',
                err_msg=f"Cluster <{cluster_name}> does not exist."
            )
            return Response(response.to_dict(),
                            status=status.HTTP_202_ACCEPTED)


class ClusterNodeViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]
    
    # GET list 
    def list(self, request):
        cluster_nodes = ClusterNode.objects.filter(cluster__uuid=request.cluster_uuid)
        serializer = ClusterNodeSerializer(cluster_nodes, many=True)
        return Response(serializer.data)
    
    # POST
    def create(self, request): 
        # check the wether the cluster is existed and user is authorized to create node
        serializer = ClusterNodeSerializer(
            data=request.data,
            context={
                'created_by': request.user
            },
            partial=False
        )
        is_valid =serializer.is_valid(raise_exception=True)
        serializer.save()
        response = {
            'status': 'success',
            'data': serializer.data
        }
        return Response(response, status=status.HTTP_201_CREATED)
    
    # GET by uuid
    def retrieve(self, request, uuid):
        cluster_node = ClusterNode.objects.get(uuid=uuid)
        serializer = ClusterNodeSerializer(cluster_node)
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)




class ListFreeClusterNodeView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ClusterNodeSerializer
    
    def get_queryset(self):
        cluster_nodes = ClusterNode.objects.filter(in_fleet=False)
        logger.debug(cluster_nodes)
        return cluster_nodes
        

# SCM 
class ContainerRegistryAccessTokenViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]
    
    # GET list 
    def list(self, request):
        access_tokens = ContainerRegistryAccessToken.objects.filter(created_by=request.user)
        serializer = ContainerRegistryAccessTokenSerializer(access_tokens, many=True)
        return Response(serializer.data)
    
    # POST
    def create(self, request):
        serializer = ContainerRegistryAccessTokenSerializer(
            data=request.data,
            context={
                'created_by': request.user
            },
            partial=False
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        response = {
            'status': 'success',
            'uuid': serializer.data['uuid'],
            'name': serializer.data['name'],
        }
        return Response(response, status=status.HTTP_201_CREATED)
    
    # GET by uuid
    def retrieve(self, request, uuid):
        access_token = ContainerRegistryAccessToken.objects.get(uuid=uuid)
        serializer = ContainerRegistryAccessTokenSerializer(access_token)
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)
    