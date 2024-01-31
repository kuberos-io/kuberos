# Django
from rest_framework import generics, permissions, viewsets, status
from rest_framework.response import Response
# KubeROS
from main.models import(
    RosNodeMeta,
    RosNodeVersion,
    RosModuleCategory, 
    RosModuleMeta,
    RosModuleVersion
)
from main.serializers.rospackages import(
    RosModuleCategorySerializer,
    RosModuleMetaSerializer,
    RosNodeMetaSerializer,
)

# Module category
class RosModuleCategoryViewSet(viewsets.ViewSet):
    
    permission_classes = [permissions.IsAuthenticated]
    
    # GET list 
    def list(self, request):
        category = RosModuleCategory.objects.filter(created_by=request.user)
        serializer = RosModuleCategorySerializer(category, many=True)
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)
    
    # POST 
    def create(self, request):
        serializer = RosModuleCategorySerializer(
            data=request.data,
            context={
                'created_by': request.user
            },
            partial=True
        )
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            response = {
                'status': 'success',
                'data': serializer.data
            }
            return Response(response, 
                            status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, 
                            status=status.HTTP_400_BAD_REQUEST)

    # GET by uuid 
    def retrieve(self, request, uuid):
        category = RosModuleCategory.objects.get(uuid=uuid)
        serializer = RosModuleCategorySerializer(category)
        return Response(serializer.data, 
                        status=status.HTTP_202_ACCEPTED)
        

# Module meta 
class RosModuleMetaViewSet(viewsets.ViewSet):
    
    permission_classes = [permissions.IsAuthenticated]
    
    # GET list 
    def list(self, request):
        module_meta = RosModuleMeta.objects.filter(created_by=request.user)
        serializer = RosModuleMetaSerializer(module_meta, many=True)
        return Response(serializer.data, 
                        status=status.HTTP_202_ACCEPTED)
  
    # POST 
    def create(self, request):
        serializer = RosModuleMetaSerializer(
            data=request.data,
            context={
                'created_by': request.user
            },
            partial=True
        )
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            response = {
                'status': 'success',
                'data': serializer.data
            }
            return Response(response, 
                            status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, 
                            status=status.HTTP_400_BAD_REQUEST)

    # GET by uuid 
    def retrieve(self, request, uuid):
        module_meta = RosModuleMeta.objects.get(uuid=uuid)
        serializer = RosModuleMetaSerializer(module_meta)
        return Response(serializer.data, 
                        status=status.HTTP_202_ACCEPTED)



# Ros Node 
class RosNodeMetaViewSet(viewsets.ViewSet):
    
    permission_classes = [permissions.IsAuthenticated]
    
    # GET list 
    def list(self, request):
        node_meta = RosNodeMeta.objects.filter(created_by=request.user)
        serializer = RosNodeMetaSerializer(node_meta, many=True)
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)
    
    # POST 
    def create(self, request):
        serializer = RosNodeMetaSerializer(
            data=request.data,
            context={
                'created_by': request.user
            },
            partial=True
        )
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            response = {
                'status': 'success',
                'data': serializer.data
            }
            return Response(response, 
                            status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, 
                            status=status.HTTP_400_BAD_REQUEST)

    # GET by uuid 
    def retrieve(self, request, uuid):
        node_meta = RosNodeMeta.objects.get(uuid=uuid)
        serializer = RosNodeMetaSerializer(node_meta)
        return Response(serializer.data, 
                        status=status.HTTP_202_ACCEPTED)
