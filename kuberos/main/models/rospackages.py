# Python 

# Django 
from django.db import models
from django.contrib.auth.models import User

# KubeROS 
from .base import BaseTagModel


# ROS Node
class RosNodeMeta(BaseTagModel):
    name = models.CharField(
        max_length=256, 
        blank=False,
        null=False
    )
    maintainers = models.ManyToManyField(
        User, 
        related_name='ros_node_maintainers'
    )
    

def rosnode_package_info_file_path(instance, filename):
    return 'rosnode_package/{}/{}/package.xml'.format(
            instance.rosnode.name, 
            instance.tag
        )

class RosNodeVersion(BaseTagModel):
    name = models.CharField(
        max_length=255, 
        null=False, 
        blank=False, 
        verbose_name="name"
    )
    
    tag = models.CharField(
        max_length=256, 
    )
    meta = models.ForeignKey(
        RosNodeMeta,
        related_name='ros_node_versions',
        null=True,
        on_delete=models.SET_NULL
    )
    package_info_file = models.FileField(
        null=True,
        blank=True,
        upload_to=rosnode_package_info_file_path,
    )
    
    
# ROS Module
class RosModuleCategory(BaseTagModel):
    name = models.CharField(
        max_length=256,
        blank=False,
        null=False
    )


class RosModuleMeta(BaseTagModel):
    name = models.CharField(
        max_length=255, 
        null=False, 
        blank=False, 
        verbose_name="name"
        )
    category = models.ForeignKey(
        RosModuleCategory,
        related_name='ros_module_versions',
        null=True,
        on_delete=models.SET_NULL
    )
    
    maintainers = models.ManyToManyField(
        User, 
        related_name='ros_module_maintainers'
    )
    
    # maintainer 
    # keywords
    # readme 
    # install 
    # recommandation 
    # parameter
    # description 
    # logopath
    # logourl
    # license
    # homeurl
    # screenshot 
    # displayName
    # Provider
    # Annotation
    # Recommendations
    
    def get_newst_version(self):
        # return container image
        # return deployment yaml
        pass

def rosmodule_yaml_path(instance, filename):
    return 'rosmodule/{}/{}/{}.kuberos.yaml'.format(
            instance.meta.name, 
            instance.tag,
            instance.meta.name,
        )
    
class RosModuleVersion(BaseTagModel):
    ROS_DISTRIBUTION_CHOICES = (
        ('foxy', 'Foxy Fitzroy'),
        ('galactic', 'Galactic Geochelone'),
        ('humble', 'Humble Hawksbill'),
    )

    name = models.CharField(
        max_length=255, 
        null=False, 
        blank=False, 
        verbose_name="name"
        )
    
    meta = models.ForeignKey(
        RosModuleMeta, 
        related_name='ros_module_versions',
        null=True,
        on_delete=models.SET_NULL
    )
    
    mainnodes = models.ManyToManyField(
        RosNodeVersion, 
        related_name='ros_modules_as_main',
    )
    dependency_nodes = models.ManyToManyField(
        RosNodeVersion, 
        related_name='ros_modules_as_dependency',
    )
    
    container_image_url = models.CharField(
        max_length=1024
    )
    deployment_yaml = models.FileField(
        blank=True,
        null=True,
        upload_to=rosmodule_yaml_path,
    )


"""
Application Domain: 
 - mobile robot 
 - mobile manipulator 
 - industrial robot arm 
 - drohne 
 - underwater robot 
 
Type of ROS Module: 
 - sensor driver
 - actuator driver
 - simulation instance
 - robot software stack 
 - AL / ML 
 - datasets
 - diagnostic tools

Task Domain:
 - grasping 
 - pick and place 
 - navigation 
 - motion planning 
 - trajectory generation 
 - object detection 

Example Application: 



"""
# Application Domain: 