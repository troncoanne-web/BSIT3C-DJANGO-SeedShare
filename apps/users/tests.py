from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import UserProfile


class UserListProfilePictureTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin = user_model.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='test-password-123',
        )
        self.user = user_model.objects.create_user(
            username='seed-user',
            first_name='Seed',
            last_name='Farmer',
            password='test-password-123',
        )
        self.client.force_login(self.admin)

    def test_user_list_shows_profile_picture_and_uses_initials_without_one(self):
        response = self.client.get(reverse('users:user_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'SF')
        self.assertNotContains(response, 'seed-user profile picture')

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            profile = UserProfile.objects.create(
                user=self.user,
                profile_picture=SimpleUploadedFile(
                    'profile.png',
                    b'profile image',
                    content_type='image/png',
                ),
            )

            response = self.client.get(reverse('users:user_list'))

            self.assertContains(response, profile.profile_picture.url)
            self.assertContains(response, 'seed-user profile picture')
