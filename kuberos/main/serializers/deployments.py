# Django
from django.contrib.auth import authenticate
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

# KubeROS
from main.models import (
    Deployment, 
    DeploymentEvent,
    DeploymentJob
)

class DeploymentEventSerializer(serializers.ModelSerializer):
    
    class Meta: 
        model = DeploymentEvent
        fields = ['event_type', 'event_status', 'created_at']
        


class DeploymentJobSerializer(serializers.ModelSerializer):
    
    class Meta: 
        model = DeploymentJob
        fields = ['robot_name', 'job_phase', 
                  'all_pods_status', 'all_svcs_status']
        

class DeploymentSerializer(serializers.ModelSerializer):

    
    deployment_event_set = DeploymentEventSerializer(many=True, read_only=True)   
        
    deployment_job_set = DeploymentJobSerializer(many=True, read_only=True)

    class Meta: 
        model = Deployment
        fields = ['name', 'status', 'fleet_name', 'running_since', 
                  'deployment_event_set', 
                  'deployment_job_set'
                  ]
        extra_kwargs = {
            'created_by': {'read_only': True}, 
            'dep_event_set': {'required': False,
                               'allow_null': True,
                               'allow_empty': True},
        }

    def create(self, validated_data):
        validated_data['created_by'] = self.context['created_by']
        validated_data['modified_by'] = self.context['created_by']
        return super().create(validated_data)


