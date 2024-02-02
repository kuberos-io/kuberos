# Django 
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone



class DeviceCategory(models.Model):
    
    category_name = models.CharField(
        null=False,
        blank=False,
        unique=True,
        max_length=255
    )

    

class Device(models.Model):
    """
    A device that can be used to authenticate a user.
    """
    device_name = models.CharField(
        null=False,
        blank=False,
        max_length=255
    )

    # hardware specific parameters to be communicated and controlled by 
    # a ros2 software on a computer.
    device_parameters = models.JSONField(
        null=True,
    )
    
    
    
# class DeviceParameterTag(models.Model):
# Due to different firmware versions and the hardware differences? 
# To be implemented later.
