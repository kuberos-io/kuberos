# Python
import uuid

# Django
from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.utils import timezone
# Authentification
from django.contrib.auth.models import User
from django.contrib.auth import get_user_model


__all__ = [
    'BaseModel',
    'UserRelatedBaseModel',
]


class BaseModel(models.Model):
    """
    Base model class with common fields and methods
    """

    class Meta:
        abstract = True

    uuid = models.UUIDField(
        primary_key=True,
        editable=False,
        unique=True,
        default=uuid.uuid4
        )

    # TODO: Change "created_time" to "created_at" and "modified_time" to "modified_at"
    created_time = models.DateTimeField(
        null=False,
        blank=False,
        verbose_name="created time",
        default=timezone.now
        )
    modified_time = models.DateTimeField(
        null=False,
        blank=False,
        verbose_name="modified time",
        default=timezone.now
        )

    def __str__(self) -> str:
        return str(self.name)
    
    def get_uuid(self) -> str:
        return str(self.uuid)
    

def get_sentinel_user():
    return get_user_model().objects.get_or_create(username='deleted')[0]


class UserRelatedBaseModel(BaseModel):
    """
    Base model class for creating user related models with common methods:
    """

    class Meta:
        abstract = True

    created_by = models.ForeignKey(
        User,
        related_name='%s(class)s_created+',
        editable=False,
        on_delete=models.SET(get_sentinel_user),
        )


class BaseTagModel(UserRelatedBaseModel):
    """
    Base tag class for all objects that have the tags for versioning
    """

    class Meta:
        abstract = True

    modified_by = models.ForeignKey(
        User,
        related_name='%s(class)s_modified+',
        editable=True,
        on_delete=models.SET(get_sentinel_user),
        )

    description = models.TextField(
        blank=True,
        default=''
    )
