# Django
from django.contrib.auth import authenticate
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

# KubeROS
from .base import BaseModelSerializer
from main.models import (
    RosNodeMeta,
    RosNodeVersion,
    RosModuleCategory,
    RosModuleMeta,
    RosModuleVersion
)

# Base class
class RosBaseModelSerializer(serializers.ModelSerializer):
        
    def create(self, validated_data):
        validated_data['created_by'] = self.context['created_by']
        validated_data['modified_by'] = self.context['created_by']
        return super().create(validated_data=validated_data)

    @property
    def version(self):
        return 1

# Module category
class RosModuleCategorySerializer(RosBaseModelSerializer):
    class Meta: 
        model = RosModuleCategory
        fields = '__all__'
    
    def create(self, validated_data):
        validated_data['maintainers'] = [self.context['created_by']]
        return super().create(validated_data=validated_data)

# Module meta
class RosModuleMetaSerializer(RosBaseModelSerializer):
    class Meta: 
        model = RosModuleMeta
        fields = '__all__'


# Node meta
class RosNodeMetaSerializer(RosBaseModelSerializer):
    class Meta: 
        model = RosNodeMeta
        fields = '__all__'
    def create(self, validated_data):
        validated_data['maintainers'] = [self.context['created_by']]
        print("Validated Data", validated_data)
        return super().create(validated_data=validated_data)
    
