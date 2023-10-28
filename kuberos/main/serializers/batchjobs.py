# Django
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

# KubeROS
from main.models import (
    BatchJobGroup,
    BatchJobDeployment
)


class BatchJobGroupSerializer(serializers.ModelSerializer):
    
    class Meta: 
        model = BatchJobGroup
        fields = ['group_postfix', 'exec_cluster', 'repeat_num',
                  'job_statistics',
                  ]
        

class BatchJobDeploymentSerializer(serializers.ModelSerializer):

    batch_job_group_set = BatchJobGroupSerializer(many=True, read_only=True)   

    class Meta: 
        model = BatchJobDeployment
        
        fields = ['name', 'is_active', 'status', 
                  'job_spec', 'exec_clusters', 'get_job_statistics', 'get_resource_usages',
                  'started_since', 'execution_time',
                  'batch_job_group_set',
                  ]
        
        extra_kwargs = {
            'created_by': {'read_only': True}, 
            'batch_job_group_set': {'required': False,
                               'allow_null': True,
                               'allow_empty': True},
        }

    def create(self, validated_data):
        validated_data['created_by'] = self.context['created_by']
        validated_data['modified_by'] = self.context['created_by']
        return super().create(validated_data)


class BatchJobNameListSerializer(serializers.ModelSerializer):
    """
    Serializer for autocompletion in CLI
    """    
    class Meta:
        model = BatchJobDeployment
        fields = ['name']
