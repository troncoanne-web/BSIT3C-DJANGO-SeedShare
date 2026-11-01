from django import forms
from django.contrib.auth import get_user_model
from django.core.validators import FileExtensionValidator
from django.db import transaction

from .models import PROFILE_PICTURE_EXTENSIONS, UserProfile

User = get_user_model()


class ProfileSettingsForm(forms.Form):
    username = forms.CharField(max_length=150)
    profile_picture = forms.ImageField(
        required=False,
        validators=[FileExtensionValidator(PROFILE_PICTURE_EXTENSIONS)],
    )
    remove_profile_picture = forms.BooleanField(required=False)
    MAX_PROFILE_PICTURE_SIZE = 5 * 1024 * 1024

    def __init__(self, *args, user, profile, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.profile = profile
        self.fields['username'].initial = user.username
        self.fields['username'].widget.attrs['class'] = 'form-control'
        self.fields['profile_picture'].widget.attrs.update({
            'class': 'form-control',
            'accept': 'image/*',
        })
        self.fields['remove_profile_picture'].widget.attrs['class'] = 'form-check-input'

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if User.objects.filter(username__iexact=username).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError('That username is already taken.')
        return username

    def clean_profile_picture(self):
        picture = self.cleaned_data.get('profile_picture')
        if picture and picture.size > self.MAX_PROFILE_PICTURE_SIZE:
            raise forms.ValidationError('Profile pictures must be 5 MB or smaller.')
        return picture

    def save(self):
        old_picture_name = self.profile.profile_picture.name
        picture = self.cleaned_data.get('profile_picture')
        remove_picture = self.cleaned_data.get('remove_profile_picture')

        with transaction.atomic():
            self.user.username = self.cleaned_data['username']
            self.user.save(update_fields=['username'])

            if picture:
                self.profile.profile_picture = picture
            elif remove_picture:
                self.profile.profile_picture = ''
            self.profile.save()

            new_picture_name = self.profile.profile_picture.name
            if old_picture_name and old_picture_name != new_picture_name:
                storage = self.profile.profile_picture.storage
                transaction.on_commit(lambda: storage.delete(old_picture_name))

        return self.user


class UserForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput,
        required=False
    )

    class Meta:
        model = User
        fields = [
            'username',
            'first_name',
            'last_name',
            'email',
            'password',
            'is_staff',
            'is_active'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Force all fields required except password
        for field in self.fields:
            if field != 'password':
                self.fields[field].required = True

        # Password required only when creating
        if not self.instance.pk:
            self.fields['password'].required = True

    def save(self, commit=True):
        user = super().save(commit=False)

        password = self.cleaned_data.get('password')

        # Only change password if user entered one
        if password:
            user.set_password(password)

        if commit:
            user.save()

        return user