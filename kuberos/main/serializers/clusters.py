# Django
from django.contrib.auth import authenticate
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

# KubeROS
from main.serializers.utils import get_choice_value
from main.models import (
    Cluster,
    ClusterNode,
    ClusterServiceAccount, 
    ContainerRegistryAccessToken,
)


class ClusterServiceAccounSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClusterServiceAccount
        fields = '__all__'


class ClusterNodeSerializer(serializers.ModelSerializer):
    
    kuberos_role = serializers.CharField(source='get_kuberos_role_display')
    # is_available = serializers.BooleanField(source='is_available')
    class Meta: 
        model = ClusterNode
        fields = ('hostname', 'uuid', 'kuberos_role', 
                  'device_group', 'is_available', 'is_alive', 'kuberos_registered', 
                  'peripheral_device_name_list', 'robot_name', 'robot_id', 'assigned_fleet_name',
                  'resource_group', 'is_shared',
                  'get_capacity', 'get_usage',
                  )
        extra_kwargs = {
            'created_by': {'read_only': True}
            }
    
    def create(self, validated_data):
        validated_data['created_by'] = self.context['created_by']
        return super().create(validated_data)
    

class ClusterSerializer(serializers.ModelSerializer):

    cluster_node_set = ClusterNodeSerializer(many=True, required=False)

    cluster_status = serializers.CharField(source='get_cluster_status_display', read_only=True)
    # TODO: remove the ready_only
    env_type = serializers.CharField(source='get_env_type_display', read_only=True)
    distribution = serializers.CharField(source='get_distribution_display')
  
    class Meta: 
        model = Cluster
        # fields = '__all__'
        fields = ['cluster_name', 'uuid', 'host_url', 
                  'cluster_status', 'env_type', 'distribution', 'distribution_version',
                  'created_by', 'created_time', 'last_sync_since', 'alive_age',
                  'service_token_admin', 'ca_crt_file',
                  'description', 'cluster_node_set']
        extra_kwargs = {
            'service_token_admin': {'write_only': True},
            'modified_by': {'read_only': True}, 
            'ca_crt_file': {'write_only': True},
            'ca_pem': {'write_only': True},
        }

    
    def create(self, validated_data):
        validated_data['created_by'] = self.context['created_by']
        validated_data['modified_by'] = self.context['created_by']
        
        # get the value of the distribution chioces by give the label
        distribution = validated_data.pop('get_distribution_display')
        value = get_choice_value(Cluster.ClusterDistributionChoices, distribution)
        validated_data['distribution'] = value
        
        return super().create(validated_data)

    def validate(self, attrs):
        
        distribution = attrs.get('get_distribution_display')
        # validate the provided distribution
        if not distribution in Cluster.ClusterDistributionChoices.labels:
            raise serializers.ValidationError(f'Invalid distribution: {distribution} \
                    - K8s support one of following distribution: \
                    {Cluster.ClusterDistributionChoices.labels}')

        return super().validate(attrs)


# SCM 
class ContainerRegistryAccessTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContainerRegistryAccessToken
        fields = ['uuid', 'name', 'user_name', 'registry_url', 'description', 'token']
        extra_kwargs = {
            'encoded_secret': {'read_only': True},
            'token': {'write_only': True},
        }
    
    def create(self, validated_data):
        validated_data['created_by'] = self.context['created_by']
        return super().create(validated_data)
