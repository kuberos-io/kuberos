

# python
import yaml
import logging

# Django
from rest_framework.response import Response
from rest_framework import viewsets, views, generics, status
from rest_framework import permissions

# KubeROS
from main.models import (
    Cluster,
    ClusterNode,
    ContainerRegistryAccessToken
)

from main.api.base import KuberosResponse

from main.tasks.cluster_operating import (
    sync_kubernetes_cluster,
    update_cluster_node_labels,
    manage_container_access_token,
)


logger = logging.getLogger('kuberos.main.api')



class ClusterInventoryManagementViewSet(viewsets.ViewSet):
    """
    Apply/Reset the cluster inventory manifest. 
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """
        Apply the cluster inventory manifest. 
         - check the cluster existence
         - synchronize the cluster and get current node status
         - check the validity of inventory manifest
         - update the cluster node labels in KubeROS database
         - trigger the update in Kubernetes cluster
        """
        res = 'pending'
        msg = ''
        data = {}
        
        inv_file = request.data['inventory_description'].read().decode('utf-8')
        inv_dict = yaml.safe_load(inv_file)
        
        metadata = inv_dict.get('metadata', None)
        cluster_name = metadata.get('clusterName', None)
        
        # 1. check cluster existence
        if not self.check_cluster_existence(cluster_name):
            return Response({
                'res': 'failed',
                'msg': 'Cluster {} does not exist.'.format(cluster_name),
                'data': {}}, 
                status=status.HTTP_200_OK)
        
        # 2. sync k8s cluster with kuberos 
        result = sync_kubernetes_cluster.delay(
            cluster_config=self.cluster.cluster_config_dict,
        )
        cluster_response = result.get(timeout=3, propagate=False)
        if not result.successful():
            return Response({'res': 'failed',
                             'msg': 'Failed to sync kubernetes cluster.',})
        
        # 3. check inventory manifest validity
        nodes_ava = cluster_response['data']
        for node in nodes_ava:
            print(node['name'], node['ready'])
        
        inv_ok, inv_warn = self.check_inventory_validity(inv_dict['hosts'], nodes_ava)
        
        if len(inv_warn) > 0:
            msg = 'Update failed: \n The following nodes are not labeled: {}'.format(inv_warn)
            res = 'failed'
        
        else:
            # 4. update the cluster node label in KubeROS 
            for inv in inv_dict['hosts']:
                cluster_node = ClusterNode.objects.get(cluster=self.cluster, hostname=inv['hostname'])
                
                # get the robot name and robot id, if the onboard computer is mounted in the robot 
                located_in_robot = inv.get('locatedInRobot', None)
                if located_in_robot is not None: 
                    robot_name = located_in_robot.get('name', None)
                    robot_id = located_in_robot.get('robotId', '-1')
                else:
                    robot_name = 'None'
                    robot_id = '0000'

                # update the labels in KubeROS database 
                kuberos_role = inv.get('kuberosRole', 'unknown').upper().replace('-', '_')
                cluster_node.update_from_inventory_manifest(
                    kuberos_role=kuberos_role,
                    robot_name=robot_name,
                    robot_id=str(robot_id),
                    onboard_computer_group=inv.get('onboardComputerGroup', None),
                    resource_group=inv.get('resourceGroup', 'public'),
                    periphal_devices=inv.get('peripheralDevices', {}),
                    shared=inv.get('shared', False),
                )
                
            res = 'success'
            msg = 'Update cluster inventory description successfully.'
            
            # trigger update in Kubernetes cluster
            update_cluster_node_labels.delay(
                cluster_config=self.cluster.cluster_config_dict)
            
        return Response({'res': res,
                         # 'data': response,
                         'msg': msg}, 
                         status=status.HTTP_201_CREATED)
        
    def check_inventory_validity(self, inv_list: list, nodes_ava: list):
        """
        Check the inventory description validity.
        inv: list of dict
            [{
                'hostname': 'node1', 
                'accessIp': '193.196.37.68', 
                'kuberosRole': 'onboard', 
                'deviceType': None,
                'robotName': 'sim-robot-1', 
                'robotId': 1, 
                'shared': False
            }]
        nodes_ava: list of dict from cluster
            [{
                'name': 'node2', 
                'ready': 'True'
                'labels': {
                    'beta.kubernetes.io/arch': 'amd64', 
                    'beta.kubernetes.io/os': 'linux', 
                    'kubernetes.io/arch': 'amd64', 
                    'kubernetes.io/hostname': 'node2', 
                    'kubernetes.io/os': 'linux', 
                    'resource.kuberos.io/type': 'onboard', 
                    'resource.kuberos.io/uuid': '633a26cb-2742-4297-908c-e24e2af42228', 
                    'robot.kuberos.io/robot': 'dummy-2'}, 
                'status': {
                    'NetworkUnavailable': {'status': False, 'reason': 'CalicoIsUp', 'msg': 'Calico is running on this node'}, 
                    'MemoryPressure': {'status': False, 'reason': 'KubeletHasSufficientMemory', 'msg': 'kubelet has sufficient memory available'}, 
                    'DiskPressure': {'status': False, 'reason': 'KubeletHasNoDiskPressure', 'msg': 'kubelet has no disk pressure'}, 
                    'PIDPressure': {'status': False, 'reason': 'KubeletHasSufficientPID', 'msg': 'kubelet has sufficient PID available'}, 
                    'Ready': {'status': True, 'reason': 'KubeletReady', 'msg': 'kubelet is posting ready status. AppArmor enabled'}}, 
            }]
        
        1. check the hostname is founded in the cluster
        2. check wether the ip address matches the hostname
        """
        nodes_ava_name_list = [node['name'] for node in nodes_ava]
        inv_valid = []
        inv_warn = []
        
        print(nodes_ava_name_list)
        
        for inv in inv_list:
            # check whether the hostname is founded in the cluster
            if inv['hostname'] not in nodes_ava_name_list:
                inv['check'] = 'warning'
                inv['msg'] = 'Node {} not found in the cluster.'.format(inv['hostname'])
                inv_warn.append(inv['hostname'])
                # check wehter the ip address matches the hostname

            else:
                inv['check'] = 'valid'
                inv['msg'] = 'Node {} is valid.'.format(inv['hostname'])
                inv_valid.append(inv['hostname'])
        return inv_valid, inv_warn
        

    def check_cluster_existence(self, cluster_name):
        try:
            self.cluster = Cluster.objects.get(cluster_name=cluster_name)
            return True
        except Cluster.DoesNotExist:
            return False
        
        
    def update(self):
        """
            Patch Inventory Description 
            For Web UI
        """
        pass 
    
    def reset(self, request, cluster_name):
        """
            Reset the cluster node labels in KubeROS 
            Remove all labels 
            Delete all nodes in database 
            Stop all pods in the Kubernetes cluster! TODO
        """
        cluster = Cluster.objects.get(cluster_name=cluster_name)
        
        # clean the cluster node in KubeROS 
        cluster.reset_cluster()
        
        # call the task to clean the node labels in the cluster
        return Response({'res': True,
                         # 'data': response,
                         'msg': 'reset the cluster nodes successfully.'}, 
                         status=status.HTTP_201_CREATED)



class ContainerRegistryAccessTokenManagementViewSet(viewsets.ViewSet):
    """
    Create container registry access token in given namespace
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """
        Check whether the access token is existed in the given namespace.
        """
        cluster, token, ns = self.parse_request(request)
        res, msg = crud_container_access_token(
            namespace=ns,
            cluster_config=cluster.cluster_config_dict,
            secret_name=token.name, # secret name in K8s
            action='get'
        )
        if res:
            return Response({'success': res,
                             'message': 'The access token - {} is existed.'.format(token.name)})
        else:
            return Response({'success': res,
                             'message': msg})

    # create the access token in the given namespace
    def post(self, request):
        """
        request: 
         - cluster_uuid:
         - namespace:
         - registry_url:
         - registry_username:
         - registry_password:
        """
        cluster, token, ns = self.parse_request(request)
        # print("Encoded docker auth: {}".format(token.get_encode_docker_auth()))
        encoded_docker_auth = token.get_encode_docker_auth()
        print(f'Encoded docker auth: {encoded_docker_auth}')

        task = manage_container_access_token.delay(
            namespace=ns,
            secret_name=token.name,
            cluster_config=cluster.cluster_config_dict,
            config_json={'.dockerconfigjson': encoded_docker_auth},
            action='create'
        )
        return Response({'celery_task_id': task.id}, 
                        status=status.HTTP_202_ACCEPTED)
        
        # 1. Check cluster connection
        # 2. Check resource description 
        # 3. Check resource status
        # 4. Check software module accessibility
        # 4.1 Store software module in central registry.
        # 5. Invocate deployment task via Celery
        # 6. Return task ID
        # 6.1 Write task ID to Deployment table

    def parse_request(self, request):
        """
        Parse the request
        """
        cluster_name = request.data['cluster_name']
        token_name = request.data['token_name']
        ns = request.data['namespace']
        cluster = Cluster.objects.get(cluster_name=cluster_name)
        token = ContainerRegistryAccessToken.objects.get(name=token_name)
        return cluster, token, ns


class ClusterIPReservationViewSet(viewsets.ViewSet):
    """
    Reserve a ip pool for deploying using cycloneDDS 
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        res = 'pending'
        msg = ''



class ClusterAutoDiscoveryViewSet(viewsets.ViewSet):
    """
    Apply/Reset the cluster inventory manifest. 
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """
        Apply the cluster inventory manifest. 
         - check the cluster existence
         - synchronize the cluster and get current node status
         - check the validity of inventory manifest
         - update the cluster node labels in KubeROS database
         - trigger the update in Kubernetes cluster
        """
        res = 'pending'
        msg = ''
        
        # 2. sync k8s cluster with kuberos 
        result = sync_kubernetes_cluster.delay(
            cluster_config=self.cluster.cluster_config_dict,
        )
        cluster_response = result.get(timeout=3, propagate=False)
        if not result.successful():
            return Response({'res': 'failed',
                             'msg': 'Failed to sync kubernetes cluster.',})
        
        # 3. check inventory manifest validity
        nodes_ava = cluster_response['data']
        for node in nodes_ava:
            print(node['name'], node['ready'])
        
        inv_ok, inv_warn = self.check_inventory_validity(inv_dict['hosts'], nodes_ava)
        
        if len(inv_warn) > 0:
            msg = 'Update failed: \n The following nodes are not labeled: {}'.format(inv_warn)
            res = 'failed'
        
        else:
            # 4. update the cluster node label in KubeROS 
            for inv in inv_dict['hosts']:
                cluster_node = ClusterNode.objects.get(cluster=self.cluster, hostname=inv['hostname'])
                
                # get the robot name and robot id, if the onboard computer is mounted in the robot 
                located_in_robot = inv.get('locatedInRobot', None)
                if located_in_robot is not None: 
                    robot_name = located_in_robot.get('name', None)
                    robot_id = located_in_robot.get('robotId', '-1')
                else:
                    robot_name = 'None'
                    robot_id = '0000'

                # update the labels in KubeROS database 
                kuberos_role = inv.get('kuberosRole', 'unknown').upper().replace('-', '_')
                cluster_node.update_from_inventory_manifest(
                    kuberos_role=kuberos_role,
                    robot_name=robot_name,
                    robot_id=str(robot_id),
                    onboard_computer_group=inv.get('onboardComputerGroup', None),
                    periphal_devices=inv.get('peripheralDevices', {}),
                    shared=inv.get('shared', False),
                )
                
            res = 'success'
            msg = 'Update cluster inventory description successfully.'
            
            # trigger update in Kubernetes cluster
            update_cluster_node_labels.delay(
                cluster_config=self.cluster.cluster_config_dict)
            
        return Response({'res': res,
                         # 'data': response,
                         'msg': msg}, 
                         status=status.HTTP_201_CREATED)
        