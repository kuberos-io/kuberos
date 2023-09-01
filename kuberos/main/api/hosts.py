# Python
from functools import partial
# Django
from rest_framework import generics, permissions, viewsets, status
from rest_framework.response import Response
# KubeROS
from main.models import (
    HostCredential,
    Host
)
from main.serializers import (
    HostCredentialSerializer, 
    HostSerializer
)

class HostCredentialViewSet(viewsets.ViewSet):
    
    permission_classes = [permissions.IsAuthenticated]
    # authentication_classes = []  # Override the default authentification and authorization in settings.
    
    # GET list
    def list(self, request):
        host_credentials = HostCredential.objects.filter(created_by=request.user)
        serializer = HostCredentialSerializer(host_credentials, many=True)
        return Response(serializer.data)
    
    # POST
    def create(self, request):
        serializer = HostCredentialSerializer(
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
            'name': serializer.data['name']
        }
        return Response(response, status=status.HTTP_201_CREATED)

    # GET by uuid
    def retrieve(self, request, uuid):
        host_credential = HostCredential.objects.get(uuid=uuid)
        serializer = HostCredentialSerializer(host_credential)
        return Response(serializer.data, 
                        status=status.HTTP_202_ACCEPTED)


class HostViewSet(viewsets.ViewSet):
    
    permission_classes = [permissions.IsAuthenticated]
    
    # GET
    def list(self, request):
        hosts = Host.objects.filter(created_by=request.user)
        serializer = HostSerializer(hosts, many=True)
        return Response(serializer.data)
    
    # POST
    def create(self, request):
        serializer = HostSerializer(
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
            'host': serializer.data
        }
        return Response(response, status=status.HTTP_201_CREATED)
