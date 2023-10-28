# Python
import logging

# Django
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

# KubeROS
from main.models import (
    Fleet, 
    FleetNode,
)

logger = logging.getLogger('kuberos.main.serializer')


class FleetNodeSerializer(serializers.ModelSerializer):
    
    cluster_node_name = serializers.CharField(source='cluster_node.hostname')
    
    class Meta: 
        model = FleetNode
        fields = ['name', 'uuid', 'cluster_node_name', 
                  'shared_resource', 'status', 
                  'is_fleet_node_alive',
                  'robot_name', 'robot_id', 'onboard_comp_group']


class FleetSerializer(serializers.ModelSerializer):

    fleet_node_set = FleetNodeSerializer(many=True)

    fleet_status = serializers.CharField(source='get_fleet_status_display')

    k8s_main_cluster_name = serializers.CharField(source='k8s_main_cluster.cluster_name')
    
    class Meta: 
        model = Fleet
        fields = ['fleet_name', 'uuid', 'created_by', 
                  'created_since', 'alive_age',
                  'modified_time', 'is_entire_fleet_healthy', 'current_status',
                  'fleet_status', 'description', 
                  'k8s_main_cluster_name', 'fleet_node_set']
        extra_kwargs = {
            'created_by': {'read_only': True},
            'modified_by': {'read_only': True},
            'fleet_node_set': {'required': False,
                               'allow_null': True,
                               'allow_empty': True},
        }
    
    def create(self, validated_data):        
        validated_data['created_by'] = self.context['created_by']
        fleet_nodes = validated_data.pop('fleet_node_set')
        fleet = Fleet.objects.create(**validated_data)
        for fleet_node in fleet_nodes:
            fleet_node_instance = FleetNode.objects.create(fleet=fleet, 
                                                           **fleet_node)
        return fleet
        
    def update(self, instance, validated_data):
        # instance.modified_by = self.context['modified_by']
        fleet_nodes = validated_data.pop('fleet_node_set')
        instance = super().update(instance, validated_data)
        
        
        return instance

    # validate() is called after __init__() and before create() or update()
    # we have to validate the data before creating the serializer 
    # -> outside of the serializer    
    # def validate(self, data):
    #     logger.debug('Validating fleet nodes')
    #     logger.debug('Got request data: \n {}'.format(data))
    #     return data


class FleetNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fleet
        fields = ['fleet_name']
