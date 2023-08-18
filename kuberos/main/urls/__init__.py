from django.urls import path, include

from .auth import urls as auth_urls
from .host import urls as host_urls
from .rospackages import urls as rospackage_urls
from .cluster import urls as cluster_urls
from .cluster_operating import urls as cluster_operating_urls
from .deployment import urls as deployment_urls
from .bachjobs import urls as batchjobs_urls
from .fleet import urls as fleet_urls
from .deploying import urls as deploying_urls


v1_urls = [    
    path('auth/', include(auth_urls)),
    path('host/', include(host_urls)),
    path('cluster/', include(cluster_urls)),
    path('rospackage/', include(rospackage_urls)),
    path('deploying/', include(deploying_urls)),
    path('deployment/', include(deployment_urls)),
    path('batch_jobs/', include(batchjobs_urls)),
    path('cluster_operating/', include(cluster_operating_urls)),
    path('fleet/', include(fleet_urls)),
]


urlpatterns = [
    path('v1/', include(v1_urls))
]



__all__ = ['urlpatterns']