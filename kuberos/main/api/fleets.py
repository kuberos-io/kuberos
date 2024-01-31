# Python
import yaml
import logging

# Django
from django.utils import timezone
from rest_framework import views, permissions, viewsets, status, generics
from rest_framework.response import Response

# KubeROS
from main.api.base import KuberosResponse
from main.models import(
    Fleet,
    FleetNode,
    Cluster,
    ClusterNode,
)
from main.serializers.fleets import (
    FleetSerializer,
    FleetNameSerializer,
    FleetNodeSerializer
)

from main.tasks.cluster_operating import (
    update_cluster_node_labels,
    sync_kubernetes_cluster
)


logger = logging.getLogger('kuberos.main.api')



class ManageFleetViewSet(viewsets.ViewSet):
    """
    Fleet Management API
    For create, update, delete fleets through the CLI and Web UI.
    """

    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        """
        Return a list of fleets created by the user.
        """

        response = KuberosResponse()

        fleets = Fleet.objects.filter(created_by=request.user)
        serializer = FleetSerializer(fleets, many=True)

        response.set_data(serializer.data)
        response.set_success()

        return Response(response.to_dict(), status=status.HTTP_200_OK)


    def create(self, request):
        """
        Create fleet from the fleet manifest.
        """
        
        # logger.debug("Received a request to create a fleet")

        response = {
            'status': 'unknown',
            'data': {},
            'errors': [],
            'msgs': []
        }

        # load fleet manifest
        fleet_dict = yaml.safe_load(
            request.data['fleet_manifest'].read().decode('utf-8'))
        fleet_meta = fleet_dict.get('metadata')
        
        # check fleet existence.
        exist_check = self.check_fleet_existence(fleet_meta['name'])
        if exist_check['existed']:
            # REJECTED: fleet already exists
            response['status'] = 'rejected'
            response['errors'].append({
                'reason': 'FleetAlreadyExists',
                'msg': f'Fleet <{fleet_meta["name"]}> already exists.'
            })
            return Response(response, status=status.HTTP_202_ACCEPTED)
        
        # get main cluster
        cluster = Cluster.objects.get(cluster_name=fleet_meta['mainCluster'])
        
        c_node_l = []
        
        rob_name_list = fleet_dict.get('robot', [])
        for name in rob_name_list:
            nodes = cluster.find_c_node_by_robot_name(name.get('name', ''))
            c_node_l.extend(nodes)
            
        # TODO can be removed ! redundant 
        # 3. check cluster nodes (robot) availability
        hostnames = []
        node_ava_check_res =self.batch_check_cluster_node_availability(hostnames)
                
        if not node_ava_check_res['res']:
            response['status'] = 'failed'
            response['errors'].append({
                'reason': 'ClusterNodeNotAvailable',
                'msg': f'Cluster node <{node_ava_check_res["msg"]}> are not available.'
            })
            return Response(response, status=status.HTTP_202_ACCEPTED)
        
        # Create fleet instance in KubeROS
        fleet = Fleet.objects.create(
            fleet_name = fleet_meta['name'],
            k8s_main_cluster = cluster,
            description = fleet_meta['description'],
            created_by = request.user,
            alive_at = timezone.now()
        )
        fleet.save()
        
        # sync cluster to update the cluster node status
        sync_kubernetes_cluster.delay(cluster.cluster_config_dict)
        
        # 5. create fleet nodes (onboards) in KubeROS
        #for node_name in hostnames:
        for c_node in c_node_l:
            #c_node = ClusterNode.objects.get(hostname=node_name)
            fleet_node = FleetNode.objects.create(
                fleet = fleet,
                name = c_node.hostname,
                cluster_node = c_node,
                status = 'deployable',
            )
            fleet_node.save()
            
            # label the cluster node
            c_node.update_labels_for_fleet(
                fleet_name=fleet.fleet_name,
                fleet_node_uuid=str(fleet_node.uuid)
            )

        # trigger labeling the cluster nodes in Kubernetes.
        update_cluster_node_labels.delay(cluster.cluster_config_dict)
        
        # Accept the request
        response['status'] = 'accepted'
        response['msgs'].append({f'Creating fleet <{fleet_meta["name"]}>'})
        
        return Response(response, status=status.HTTP_202_ACCEPTED)
    
    
    # GET <fleet_name>
    def retrieve(self, request, fleet_name):
        """
        Get the fleet instance with the given fleet name.
        """
        logger.debug("Received a request to get fleet <%s> ", fleet_name)

        response = KuberosResponse()
        
        # check existence
        exist_res = self.check_fleet_existence(fleet_name)
        if not exist_res['existed']:
            # Failed, if the fleet does not exist
            response.set_failed(
                reason='FleetDoesNotExist',
                err_msg=f'Fleet {fleet_name} not found.'
            )
            return Response(response.to_dict(),
                            status=status.HTTP_202_ACCEPTED)
        
        # return serialized fleet instance
        serializer = FleetSerializer(exist_res['fleet'])
        response.set_data(serializer.data)
        response.set_success()
        return Response(response.to_dict(),
                        status=status.HTTP_200_OK)
    
    # UPDATE <fleet_name>
    def patch(self, request, fleet_name):
        """
        Update a fleet through the CLI action.
            operations: add, remove
        """
        # check existence
        exist_res = self.check_fleet_existence(fleet_name)
        if not exist_res['existed']:
            return Response({
                'res': 'failed',
                'msg': 'Fleet {} does not exist.'.format(fleet_name),
            }, status=status.HTTP_200_OK)
        
        fleet = exist_res['fleet']
        operation = request.data['operation']
        c_nodes_changed = request.data['cluster_nodes']
        
        # Add nodes to the fleet
        if operation == 'add':
            # check the availability of the cluster nodes
            node_ava_check_res =self.batch_check_cluster_node_availability(c_nodes_changed)
            if not node_ava_check_res['res']:
                msg = 'Following robot nodes are not available: \n {}'.format(node_ava_check_res['msg'])
                return Response({
                    'res': 'failed',
                    'msg': msg,
                }, status=status.HTTP_200_OK)
            else:
                # add the nodes
                for node_name in c_nodes_changed:
                    c_node = ClusterNode.objects.get(name=node_name)
                    fleet_node = FleetNode.objects.create(
                        fleet = fleet,
                        name = node_name,
                        cluster_node = c_node,
                        node_type = 'onboard',
                        status = 'deployable',
                    )
                    fleet_node.save()
                    
                    # label the cluster node
                    c_node.update_labels_for_fleet(
                        fleet_name=fleet.name,
                        fleet_node_uuid=str(fleet_node.uuid)
                    )
                return Response({
                    'res': 'success',
                    'msg': 'Fleet {} updated successfully.'.format(fleet_name)
                    })
        
        # remove nodes from the fleet
        elif operation == 'remove':
            pass
        
        # upspoorted operation
        else: 
            return Response(
                {'res': 'failed', 
                 'message': 'Operation {} not supported'.format(operation)},
                status=status.HTTP_200_OK)
    
    # DELETE <fleet_name>
    def delete(self, request, fleet_name):
        """
        Delete the fleet with all its nodes. 
        Reject the request, if all the fleet nodes are not in the deployable status. 
        """
        logger.debug("Received a request to delete fleet <%s> ", fleet_name)
        
        response = {
            'status': 'pending',
            'data': {},
            'errors': [],
            'msgs': []
        }
        
        # check existence
        # fleet_name = 'dummy'
        exist_res = self.check_fleet_existence(fleet_name)
        if not exist_res['existed']:
            # response failed, if the fleet does not exist
            response['status'] = 'failed'
            response['errors'].append({
                'reason': 'FleetDoesNotExist',
                'msg': f'Fleet <{fleet_name}> does not exist.'
            })
            return Response(response, status=status.HTTP_202_ACCEPTED)
        
        
        fleet = exist_res['fleet']
        
        # check wether all the fleet nodes are in the deployable status
        
        delete_result = fleet.safe_delete()
        response.update(delete_result)
        return Response(response, status=status.HTTP_202_ACCEPTED)
    
        if not deletion_check['success']:
            return Response({
                'res': 'failed',
                'msg': deletion_check['msg'],
            }, status=status.HTTP_200_OK)
        else:
            cluster = fleet.k8s_main_cluster
            
            # delete the fleet nodes and fleet: 
            # 1. remove the labels from the cluster nodes
            # 2. after finishing the label removal, delete the fleet nodes and fleet. 
            # OR: delete the fleet nodes and fleet, force cluster update!
            # Problem should be avoid is that the . 
            fleet.delete()
            # trigger labeling the cluster nodes in Kubernetes.
            # TODO: Cache the event in the database, in which the update not sucessful.
            update_cluster_node_labels.delay(cluster.cluster_config_dict)
            
            return Response({
                'res': 'success',
                'msg': 'Fleet deleted successfully.',},
                            status.HTTP_200_OK)
    
    
    ### check the availability of cluster nodes and the validity of the request
    def batch_check_cluster_node_availability(self, c_node_list: list):
        """
        Batch check the availability of the cluster nodes.
        TODO: Force sync the cluster status!
        """
        success = True
        msg = ''
        for node in c_node_list:
            ava = self.check_cluster_node_availabilty(node)
            if not ava['available']:
                success = False
                msg += '<{}>\n'.format(node)
        return {
            'res': success,
            'msg': msg,
        }
    
    def check_cluster_node_availabilty(self, cluster_node_name):
        """
        Check whether the cluster node is available or not.
        """
        res = {
            'hostname': cluster_node_name,
            'available': False,
            'msg': ''
        }
        try: 
            node = ClusterNode.objects.get(hostname=cluster_node_name)
            res['available'] = True
        except ClusterNode.DoesNotExist:
            res['available'] = False
            res['msg'] = 'Cluster node [{}] does not exist.'.format(cluster_node_name)
        return res
    
    def check_fleet_existence(self, fleet_name):
        """
        Check whether the fleet exists or not.
        """
        res = {
            'existed': False,
            'fleet': None,
        }
        try:
            fleet = Fleet.objects.get(fleet_name=fleet_name)
            res['existed'] = True
            res['fleet'] = fleet
        except:
            res['existed'] = False
        
        return res



class FleetNameListView(generics.ListAPIView):

    def list(self, request):
        fleets = Fleet.objects.filter(created_by=request.user)
        serializer = FleetNameSerializer(fleets, many=True)
        return Response(serializer.data, 
                        status=status.HTTP_200_OK)



class FleetViewSet(viewsets.ViewSet):
    
    permission_classes = [permissions.IsAuthenticated]
    
    # POST
    def create(self, request):
        
        # before instantiating serializer, check the request data
        is_valid, msg = self.validate_create_request(request)
        if not is_valid:
            return Response(
                {'status': 'error', 'message': msg},
                status=status.HTTP_400_BAD_REQUEST
            )
        else:
            logger.debug("Data is valid")
            serializer = FleetSerializer(
                data=request.data,
                context={
                    'created_by': request.user, 
                },
                partial=False
            )
            is_valid = serializer.is_valid(raise_exception=True)
            # logger.debug("Is valid: {}".format(is_valid))
            if not is_valid:
                logger.error("Invalid data: \n {}".format(serializer.errors))
            serializer.save()
            response = {
                'status': 'success',
                'uuid': serializer.data['uuid'],
                'name': serializer.data['name']
            }
            return Response(response, status=status.HTTP_201_CREATED)

    # PATCH
    def patch(self, request, fleet_name):
        msgs = []
        try:
            fleet = Fleet.objects.get(name=fleet_name)
        except Fleet.DoesNotExist:
            return Response(
                {'status': 'error', 'message': 'Fleet [{}] does not exist'.format(fleet_name)},
                status=status.HTTP_400_BAD_REQUEST)
        operation = request.data['operation']
        changed_cluster_nodes = request.data['cluster_nodes']
        
        # check the validity of the patch request
        # add nodes
        if operation == 'add':
            for node in changed_cluster_nodes:
                try:
                    cluster_node = ClusterNode.objects.get(uuid=node['uuid'])
                    if not cluster_node.is_available():
                        msgs.append("Cluster node with uuid {} is already in another fleet and is not a shared resource".format(node['uuid']))
                except ClusterNode.DoesNotExist:
                    msgs.append("Cluster node with uuid {} does not exist".format(node['uuid']))

            # patch changes, if there are no errors
            if len(msgs) == 0:
                for node in changed_cluster_nodes:
                    fleet_node = FleetNode(
                        fleet=fleet,
                        name=node['name'],
                        cluster_node=ClusterNode.objects.get(uuid=node['uuid'])
                    )
                    fleet_node.save()
                return Response({
                    'status': 'success', 
                    'data': FleetSerializer(fleet).data}, 
                    status=status.HTTP_202_ACCEPTED)
                    
            else:
                return Response(
                    {'status': 'error', 'message': msgs},
                    status=status.HTTP_400_BAD_REQUEST)
        
        # remove or rename nodes
        elif operation in ['remove', 'rename']:
            # check weather the nodes are in the fleet
            for node in changed_cluster_nodes:
                try:
                    fleet.fleet_node_set.get(cluster_node=node['uuid'])
                except FleetNode.DoesNotExist:
                    msgs.append("Cluster node with uuid {} does not exist in this fleet".format(node['uuid'])) 

            if len(msgs) == 0:
                for node in changed_cluster_nodes:
                    fleet_node = fleet.fleet_node_set.get(cluster_node=node['uuid'])
                    if operation == 'rename':
                        fleet_node.name = node['name']
                        fleet_node.save()
                    elif operation == 'remove':
                        fleet_node.delete()
                return Response({
                    'status': 'success', 
                    'data': FleetSerializer(fleet).data}, 
                    status=status.HTTP_202_ACCEPTED)
            else:
                return Response(
                    {'status': 'error', 'message': msgs},
                    status=status.HTTP_400_BAD_REQUEST)
        
        # unsupported operation
        else:
            return Response(
                {'status': 'error', 'message': 'Operation {} not supported'.format(operation)},
                status=status.HTTP_400_BAD_REQUEST)
    
    
    def validate_create_request(self, request):
        msg = []
        # Check cluster uuid
        try:
            Cluster.objects.get(uuid=request.data['k8s_main_cluster'])
        except Cluster.DoesNotExist:
            error_msg = "Cluster with uuid {} does not exist".format(request.data['k8s_main_cluster'])
            logger.error(error_msg)
            msg.append(error_msg)
        # check fleet uuid
        for node in request.data['fleet_node_set']:
            try:
                node = ClusterNode.objects.get(uuid=node['cluster_node'])
                if not node.is_available():
                    error_msg = "Cluster node with uuid {} is already in a fleet".format(node.uuid)
                    logger.error(error_msg)
                    msg.append(error_msg)
            except ClusterNode.DoesNotExist:
                error_msg = "Cluster node with uuid {} does not exist".format(node.uuid)
                logger.error(error_msg)
                msg.append(error_msg)
        if len(msg) == 0:
            return True, 'Valid request'
        else:
            return False, msg
    
    
class FleetNodeView(views.APIView):
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        nodes = FleetNode.objects.all()
        serializer = FleetNodeSerializer(nodes, many=True)
        return Response(serializer.data, 
                        status=status.HTTP_202_ACCEPTED)