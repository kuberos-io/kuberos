# Django
from django.urls import path

#KubeROS
from main.api.fleets import (
    ManageFleetViewSet,
    FleetNameListView,
    FleetViewSet, 
    FleetNodeView
)

urls = [
    
    # fleet create 
    path('manage_fleet/', ManageFleetViewSet.as_view(
        {
            'get': 'list',
            'post': 'create',
        }
    )),
    
    # fleet update
    path('manage_fleet/<str:fleet_name>/', ManageFleetViewSet.as_view(
        {
            'get': 'retrieve',
            'post': 'patch',
            'delete': 'delete',
        }
    )),
    
    # Fleet name list for auto completion
    path('fleets_name_list/', 
         FleetNameListView.as_view()
    ),
    
    # fleets
    path('fleets/', FleetViewSet.as_view(
        {
            'get': 'list',
            'post': 'create',    
        }
    )),

    path('fleets/<str:fleet_name>/', FleetViewSet.as_view(
        {
            'get': 'retrieve',
            'patch': 'patch',
            'delete': 'delete',
        }
    )),

    # fleet nodes FOR TESTING PURPOSES
    path('fleet_nodes/', FleetNodeView.as_view())
    
]

