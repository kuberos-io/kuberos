import os
from .base import *

MODE = os.environ.get('MODE', 'development')


print("Django settings: ", os.environ.get('DJANGO_SETTINGS_MODULE', None))

if MODE == 'production':
    print("Using production envrionment settings")
    
    DEBUG = False
    
    ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', None)
    if ALLOWED_HOSTS is None: 
        ALLOWED_HOSTS = ["0.0.0.0", "127.0.0.1", "10.181.120.88"]
    else:
        ALLOWED_HOSTS = ALLOWED_HOSTS.split(";")
    print("ALLOWED_HOSTS: ", ALLOWED_HOSTS)
    
    POSTGRESQL_HOST = os.environ.get('POSTGRESQL_HOST', 'localhost')
    
    DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'kuberos_db',
        'USER': 'kuberos',
        'PASSWORD': 'deploy_ros2_humble',
        'HOST': POSTGRESQL_HOST,
        'PORT': 5432,
        }
    }


# Default: using development environment 
print("Using development environment settings in DevContainer! ")

DEBUG = True

DATABASES = {
'default': {
    'ENGINE': 'django.db.backends.postgresql',
    'NAME': 'kuberos_db',
    'USER': 'kuberos',
    'PASSWORD': 'deploy_ros2_humble',
    'HOST': 'localhost',
    'PORT': 5432,
    }
}
