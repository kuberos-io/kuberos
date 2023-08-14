# Python
import logging
import yaml

# Django
from rest_framework.response import Response
from rest_framework import viewsets, status
from rest_framework import permissions

# Celery
from celery.exceptions import TimeoutError

# Kuberos
from main.api.base import KuberosResponse

from main.models import (
    Fleet,
    Deployment,
    DeploymentEvent,
    DeploymentJob,
)

from main.tasks.cluster_operating import (
    sync_kubernetes_cluster,
)
from main.tasks.deployment_controller import (
    processing_deployment_job,
    prepare_deployment_env,
    delete_deployed_configmaps
)

# Pykuberos
from pykuberos.scheduler import KuberosScheduler


logger = logging.getLogger('kuberos.main.api')


# This flag is for testing the scheduler
EXECUTE_DEPLOYMENT = True


def random_string(length=10):
    import random
    import string
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(length))


class DeployRosModuleViewSet(viewsets.ViewSet):
    """
    API set for 
        - deploy a new application 
        - delete an application
        - patch deploy rosmodules
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """
        deploy the ROS module to the target fleet. 

        before deployment, following checks are performed:
            - check the deployment name -> return error: 'DeploymentAlreadyExists'
            - check the target fleet -> return error: 'FleetDoesNotExist'
            - check the main cluster reachability -> return error: 'ClusterNotReachable'
            - check the target robot availability -> return error: 'RobotNotAvailable'
        
        after all checks are passed, following steps are performed:
            - prepare the envrionment -> create configmaps, namespace, etc. 
                - return error: 'FailedToCreateConfigMap'
            - create deployment instance
            - create deployment event instance
            - create deployment job instances (one job is responsible for one robot)
            - dispatch the deployment job via Celery
            
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

        # check the deployment name
        dep_name = meta_data.get('name', None)
        existed_dep = Deployment.objects.filter(name=dep_name, active=True)
        if len(existed_dep) > 0:
            response.set_failed(
                reason='DeploymentAlreadyExists',
                err_msg=f'Deployment <{dep_name}> already exists.'
            )
            return Response(response.to_dict(),
                            status=status.HTTP_202_ACCEPTED)

        # check the fleet status
        target_fleet = meta_data.get('targetFleet', None)
        try:
            fleet = Fleet.objects.get(fleet_name=target_fleet)
        except Fleet.DoesNotExist:
            # Fleet does not exist
            msg = f'Fleet <{target_fleet}> does not exist.'
            logger.error(msg)
            response.set_failed(
                reason='FleetDoesNotExist',
                err_msg=msg
            )
            return Response(response.to_dict(), 
                            status=status.HTTP_202_ACCEPTED)

        # synchronize kubernetes cluster status
        result = sync_kubernetes_cluster.delay(
            cluster_config=fleet.k8s_main_cluster.cluster_config_dict,
        )
        try:
            result.get(timeout=2, propagate=False)
        except TimeoutError:
            # cluster synchroneous error 
            logger.error("Sync response timeout.")
            msg = f'The main cluster <{fleet.k8s_main_cluster}> is not reachable.'
            response.set_failed(
                reason='ClusterNotReachable',
                err_msg=msg)
            return Response(response.to_dict(), 
                            status=status.HTTP_202_ACCEPTED)

        # check the fleet node status -> deployable or not
        fleet_state = fleet.get_fleet_state_for_scheduling()
        # logger.debug("[Deploying] Fleet state: %s", fleet_state)

        # get the edge/cloud resources
        ava_edge_state = fleet.k8s_main_cluster.get_available_edge_node_state()
        # logger.debug("[Deploying] Edge state: %s", ava_edge_state)

        # Initialize Scheduler
        scheduler = KuberosScheduler(
            deployment_manifest=manifest_dict,
            fleet_state=fleet_state,
            edge_state=ava_edge_state
        )

        # bind_success, check_msgs = scheduler.bind_rosmodules_to_robots()
        # TODO: Error handling, if the target robot is not available
        check_success, check_msgs = scheduler.check_target_robots()
        if not check_success:
            logger.warning("[Deploying] Fleet resource check failed.")
            response.set_failed(
                reason='FleetResourceCheckFailed',
                err_msg=check_msgs
            )
            return Response(response.to_dict(),
                            status=status.HTTP_202_ACCEPTED)
        
        logger.info("[Deploying] Fleet resource check: Passed")

        # bind the rosmodules to the robots
        bind_success, check_msgs = scheduler.bind_rosmodules_to_robots()

        logger.info("[Deploying] Binding ROSModules to robots: Success")

        # schedule the deployment
        res, res_preset = scheduler.schedule()

        # scheduler.print_sc_result()
        logger.info('Scheduled Configmaps')
        logger.info(res_preset['sc_configmaps'])

        # add the configmaps of customized rosParamMaps
        # received from the request
        custom_rosparam_configmaps = request.data.get('rosparam_yamls', None)
        if custom_rosparam_configmaps:
            res_preset['sc_configmaps'] = self.merge_two_list_of_dict(
                res_preset['sc_configmaps'],
                custom_rosparam_configmaps, 
                key='name')
            
        if not EXECUTE_DEPLOYMENT:
            # Skip the execution for testing
            response.set_success(
                msg='Skip the deployment execution for testing the scheduler.'
            )
            return Response(response.to_dict(),
                            status=status.HTTP_202_ACCEPTED)
        
        # create deployment instance
        deployment = Deployment.objects.create(
            name=meta_data['name'],
            created_by=request.user,
            fleet=fleet,
            status='deploying',
            deployment_description=manifest_dict,
            config_maps = res_preset['sc_configmaps'],
        )
        deployment.save()
        
        # Prepare the deployment environment
        # check the cluster status
        # create configmaps, namespace, etc.
        prepare_task = prepare_deployment_env.delay(
            kube_config=fleet.k8s_main_cluster.cluster_config_dict,
            configmap_list=res_preset['sc_configmaps'],
            dep_uuid=deployment.get_uuid()
        )
        
        try:
            prepare_res = prepare_task.get(timeout=2, propagate=False)
            logger.debug("Result of creating configmaps: %s", prepare_res)
            
            if not prepare_res['status'] == 'success': 
                logger.error("<FailedToCreateConfigMap> %s", prepare_res['errors'])
                logger.error("To deployed configmaps: %s", res_preset['sc_configmaps'])
                logger.error("Response of KubeROS executer: %s", prepare_res)
                response.add_msg(f"To deployed configmaps: {res_preset['sc_configmaps']}")
                response.set_failed(
                    reason='FailedToCreateConfigMap',
                    err_msg=f'Failed to create configmaps: {prepare_res}.'
                )
                
                # remove the successfuly deployed configmaps 
                logger.info("Delete the deployed ConfigMaps.")
                delete_deployed_configmaps.delay(
                    kube_config=deployment.fleet.k8s_main_cluster.cluster_config_dict, 
                    configmap_list=deployment.get_config_maps(), 
                    dep_uuid=deployment.get_uuid()
                )
                
                return Response(response.to_dict(),
                                status=status.HTTP_202_ACCEPTED)
                
        except TimeoutError:
            # Create configmap failed
            logger.error("<TimeoutError> in creating configmap.")
            msg = f"<TimeoutError> in creating config map: {res_preset['sc_configmaps']}."
            response.set_failed(
                reason='FailedToCreateConfigMap',
                err_msg=msg)
            return Response(response.to_dict(), 
                            status=status.HTTP_202_ACCEPTED)


        # create deployment event instance
        dep_event = DeploymentEvent.objects.create(
            deployment=deployment,
            created_by=request.user,
            event_type=DeploymentEvent.EventTypeChoices.DEPLOY,
            deployment_description=manifest_dict,
        )
        dep_event.save()

        # create deployment job instance
        for item in res:
            dep_job = DeploymentJob.objects.create(
                robot_name=item['robot_name'],
                job_phase='pending',
                deployment=deployment,
                # deployment_event=dep_event,
                disc_server=item['sc_disc_server'],
                onboard_modules=item['sc_onboard'],
                edge_modules=item['sc_edge'],
            )
            dep_job.save()
            dep_job.intialize()

        # dispatch the deployment job
        processing_deployment_job.apply_async()
        
        response.set_accepted(
            msg='Deployment request is accepted and scheduled.'
        )
        return Response(response.to_dict(),
                        status=status.HTTP_200_OK)

    @staticmethod
    def merge_two_list_of_dict(list1, list2, key='name'):
        list1_dict = {item[key]: item for item in list1}
        list2_dict = {item[key]: item for item in list2}
        list1_dict.update(list2_dict)
        result = list(list1_dict.values())
        return result

    def delete(self, request, deployment_name):
        """
        Delete deployment
        type: 
            - complete deployment, throught deployment ID
        """
        
        response = KuberosResponse()
        
        # check deployment instance
        try:
            deployment = Deployment.objects.get(
                name=deployment_name, active=True)
            
        except Deployment.DoesNotExist:
            # Return failed 
            response.set_failed(
                reason='DeploymentDoesNotExist',
                err_msg=f'Deployment <{deployment_name}> does not exist.'
            )
            return Response(response.to_dict(),
                            status=status.HTTP_202_ACCEPTED)

        # check deployment event DELETE
        try:
            dep_event = DeploymentEvent.objects.get(
                deployment=deployment,
                event_type=DeploymentEvent.EventTypeChoices.DELETE
            )
            response.set_accepted(
                msg=f'Deployment <{deployment_name}> is already in deleting.'
            )
            # return Response(response.to_dict(),
            #                 status=status.HTTP_202_ACCEPTED)

        except DeploymentEvent.DoesNotExist:
            # create delete deployment event
            dep_event = DeploymentEvent.objects.create(
                deployment=deployment,
                created_by=request.user,
                event_type=DeploymentEvent.EventTypeChoices.DELETE,
            )

        # change deployment status
        deployment.status = 'deleting'
        deployment.save()

        # delete ConfigMaps 
        # After successful deletion, the celery worker will update the configmaps status 
        # in the deployment instance.
        # if deployment.configmaps_created:
        # problem with cocurrent database access with celery
        # TODO: try to fix this issue later
        config_maps = deployment.get_config_maps()
        delete_configmap_res = delete_deployed_configmaps(
                kube_config=deployment.fleet.k8s_main_cluster.cluster_config_dict, 
                configmap_list=config_maps, 
                dep_uuid=deployment.get_uuid()
            )
        if not delete_configmap_res['status'] == 'success':
            response.set_failed(
                reason='FailedToDeleteConfigMap',
                err_msg=f'Failed to delete configmaps: {config_maps}.'
            )
            return Response(response.to_dict(),
                            status=status.HTTP_202_ACCEPTED)
                    

        # check wether the deployment jobs is delete or not 
        # In the case that multiple delete requests are received,
        # the deployment job deletion cloud be done by previous request.
        if deployment.is_cluster_cleaned():
            deployment.update_status_as_deleted()
            response.set_success(
                msg=f'Deployment <{deployment_name}> successfully deleted.'
            )
            return Response(response.to_dict(),
                            status=status.HTTP_200_OK)

        # delete deployment jobs
        dep_job_uuid_list = []
        for dep_job in deployment.deployment_job_set.all():
            dep_job_uuid_list.append(dep_job.get_uuid())
            dep_job.update_phase_request_for_delete()

        # trigger processing deloyment job
        logger.debug("Creating dep job uuid list for deletion: %s", dep_job_uuid_list)
        processing_deployment_job.delay(dep_job_uuid_list)

        response.set_accepted(
            msg=f'Deleting deployment <{deployment_name}>.'
        )
        
        return Response(response.to_dict(),
                        status=status.HTTP_200_OK)

    def update(self, request, deployment_name):
        """
        This function is designed for using via GUI
        """
        pass


# # API Server:

# # Check Cluster Connection

# # Deployment Request

# # Get KubeROS status
