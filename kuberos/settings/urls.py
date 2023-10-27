"""kuberos URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path

from django.conf import settings
from django.conf.urls.static import static

from main.api.swagger import openapi_schema_view


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('main.urls')),
    
] + static(settings.MEDIA_URL, document_root = settings.MEDIA_ROOT)

if settings.MODE == 'development':
    urlpatterns += [
        # OpenAPI Swagger UI
        re_path(r'^swagger(?P<format>\.json|\.yaml)$', openapi_schema_view.without_ui(cache_timeout=0), name='schema-json'),
        re_path(r'^swagger/$', openapi_schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
        re_path(r'^redoc/$', openapi_schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),

    ]