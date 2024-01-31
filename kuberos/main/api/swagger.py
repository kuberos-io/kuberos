# from rest_framework.schemas import get_schema_view
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

# openapi schema view 
openapi_schema_view = get_schema_view(
    openapi.Info(
        title="KubeROS_API",
        description="HTTP APIs",
        default_version='v1',
    ),
    public=True, 
    permission_classes=[permissions.AllowAny]
)