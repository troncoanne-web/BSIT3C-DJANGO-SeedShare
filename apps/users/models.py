from django.db import models

# Create your models here.
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models

PROFILE_PICTURE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'gif', 'webp']


def profile_picture_upload_path(instance, filename):
    extension = Path(filename).suffix.lower()
    return f'profile_pictures/{uuid4().hex}{extension}'


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
    )
    profile_picture = models.ImageField(
        upload_to=profile_picture_upload_path,
        blank=True,
        validators=[FileExtensionValidator(PROFILE_PICTURE_EXTENSIONS)],
    )

    def __str__(self):
        return f'{self.user.username} profile'
