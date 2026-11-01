from io import BytesIO
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image


class HomeViewTests(TestCase):
    def test_home_renders_for_authenticated_user(self):
        user = get_user_model().objects.create_user(username='admin', password='secret1234')

        self.client.force_login(user)
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'home.html')

    def test_home_requires_login(self):
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 302)


class LoginRedirectTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='login-user',
            password='test-password-123',
        )

    def test_login_returns_user_to_requested_page(self):
        next_url = reverse('seeds:list')
        response = self.client.post(
            f'{reverse("login")}?next={next_url}',
            {'username': self.user.username, 'password': 'test-password-123'},
        )

        self.assertRedirects(response, next_url)

    def test_login_rejects_external_next_url(self):
        response = self.client.post(
            f'{reverse("login")}?next=https://example.com/',
            {'username': self.user.username, 'password': 'test-password-123'},
        )

        self.assertRedirects(response, reverse('dashboard'))


class ProfileSettingsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='farmer',
            password='test-password-123',
        )
        self.url = reverse('profile_settings')
        self.client.force_login(self.user)

    def test_profile_settings_requires_login(self):
        self.client.logout()

        response = self.client.get(self.url)

        self.assertRedirects(response, f'{reverse("login")}?next={self.url}')

    def test_user_can_change_own_username(self):
        response = self.client.post(self.url, {'username': 'new-farmer'})

        self.assertRedirects(response, self.url)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'new-farmer')

    def test_user_cannot_change_to_an_existing_username(self):
        get_user_model().objects.create_user(username='taken-name', password='password123')

        response = self.client.post(self.url, {'username': 'taken-name'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'That username is already taken.')
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'farmer')

    def test_user_can_upload_a_profile_picture(self):
        image_buffer = BytesIO()
        Image.new('RGB', (1, 1), color='red').save(image_buffer, format='PNG')
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(self.url, {
                'username': 'farmer',
                'profile_picture': SimpleUploadedFile(
                    'avatar.png',
                    image_buffer.getvalue(),
                    content_type='image/png',
                ),
            })

            self.assertRedirects(response, self.url)
            profile = self.user.profile
            self.assertTrue(profile.profile_picture.name.startswith('profile_pictures/'))
            self.assertTrue(profile.profile_picture.storage.exists(profile.profile_picture.name))
            board_response = self.client.get(reverse('seeds:list'))
            self.assertContains(board_response, 'dh-avatar-image')
            self.assertContains(board_response, profile.profile_picture.url)
