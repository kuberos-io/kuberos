# Django
from django.contrib.auth import authenticate
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

# KubeROS
from main.models import (
    HostCredential, 
    Host
)


# Host Credential
class HostCredentialSerializer(serializers.ModelSerializer):
    class Meta: 
        model = HostCredential
        fields = '__all__'
        extra_kwargs = {
            'password': {'write_only': True},
            'ssh_private': {'write_only': True}
        }

    def create(self, validated_data):
        validated_data['created_by'] = self.context['created_by']
        if not 'name' in validated_data.keys():
            validated_data['name'] = validated_data['username']
        return super().create(validated_data)


# Host 
class HostSerializer(serializers.ModelSerializer):
 
    host_credentials = HostCredentialSerializer(many=True, read_only=True)
    
    class Meta: 
        model = Host
        fields = '__all__'
    
    def create(self, validated_data):
        validated_data['created_by'] = self.context['created_by']
        return super().create(validated_data)

