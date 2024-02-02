# Django
from django.urls import path, include, re_path
# KubeROS
from main.api.rospackages import(
    RosModuleCategoryViewSet,
    RosModuleMetaViewSet,
    RosNodeMetaViewSet
)

urls = [
    # module category
    path('rosmodule_category/', RosModuleCategoryViewSet.as_view(
        {
            'get': 'list',
            'post': 'create'
        }
    )),
    path('rosmodule_category/<str:uuid>/', RosModuleCategoryViewSet.as_view(
        {
            'get': 'retrieve',
        }
    )),
    
    # module meta
    path('rosmodule_meta/', RosModuleMetaViewSet.as_view(
        {
            'get': 'list',
            'post': 'create'
        }
    )),
    path('rosmodule_meta/<str:uuid>/', RosModuleMetaViewSet.as_view(
        {
            'get': 'retrieve',
        }
    )),
    
    # node meta
    path('rosnode_meta/', RosNodeMetaViewSet.as_view(
        {
            'get': 'list',
            'post': 'create'
        }
    )),
    path('rosnode_meta/<str:uuid>/', RosNodeMetaViewSet.as_view(
        {
            'get': 'retrieve',
        }
    ))
]

