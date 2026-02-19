from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.core.exceptions import MultipleObjectsReturned
from django.contrib.auth import get_user_model
from accounts.models import *
from django.contrib import messages

User = get_user_model()
class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        """
        Auto-link social account if a single user with same email exists.
        Prevent linking if multiple users exist with same email.
        """
        email = sociallogin.user.email
        if not email:
            return
        try:
            user = CustomUser.objects.get(email=email)
        except User.DoesNotExist:
            return
        except MultipleObjectsReturned:
            messages.error(request,"Multiple accounts found with this email. Please contact support.")
            return
        if not sociallogin.is_existing:
            sociallogin.connect(request, user)


    def save_user(self, request, sociallogin, form=None):
        """
        Ensure social users are active and verified and have a role.
        """
        user = super().save_user(request, sociallogin, form)
        if not user.role:
            user.role = CustomUser.ROLE_CUSTOMER
        user.is_active = True
        user.email_verified = True
        user.save()
        return user