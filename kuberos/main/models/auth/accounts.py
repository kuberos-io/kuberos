"""
Model for user accounts.
"""

# Django
from django.utils.translation import ugettext_lazy as _
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


def user_photo_path(instance, filename):
    """
    Provide the image storage path for the ImageField.
    Args:
        - instance: the instance of the model where the ImageField is defined.
        - filename: The file name that was originally given to the uploaded file. 
                    This may not be taken into account in the destination path.
    """
    return f'user_{instance.user.id}/{filename}'


class UserProfile(models.Model):
    """
    Model to hold additional information for a User.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
    )

    biograph = models.TextField(
        max_length=200,
        blank=True,
    )

    location = models.CharField(
        max_length=200,
        blank=True,
    )

    birth_data = models.DateField(
        null=True,
        blank=True,
    )

    display_name = models.CharField(
        max_length=200,
        blank=True
    )

    photo = models.ImageField(
        upload_to=user_photo_path,
        blank=True,
        null=True,
    )

    # file = models.FileField(storage=)

    class Meta: 
        verbose_name = _('User Profile')
        verbose_name_plural = _('User Profiles')

    def __str__(self):
        return f'Profile of User: {self.user}'



@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Create or update UserProfile automatically when a User instance is created or updated. 
    """
    if created:
        UserProfile.objects.create(user=instance)
    else:
        instance.userprofile.save()

# @receiver(post_save, sender=User)
# def save_user_profile(sender, instance, **kwargs):
#     instance.userprofile.save()
