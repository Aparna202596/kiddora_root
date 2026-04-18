from accounts.models import CustomUser
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import MultipleObjectsReturned

User = get_user_model()

class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        email = sociallogin.user.email
        if not email:
            return
        try:
            user = CustomUser.objects.get(email=email)
        except User.DoesNotExist:
            return
        except MultipleObjectsReturned:
            messages.error(
                request,
                "Multiple accounts found with this email. Please contact support.",
            )
            return

        changed = False
        if not user.is_active:
            user.is_active = True
            changed = True
        if not user.email_verified:
            user.email_verified = True
            changed = True
        if not user.role:
            user.role = CustomUser.ROLE_CUSTOMER
            changed = True
        if changed:
            user.save()

        if not sociallogin.is_existing:
            sociallogin.connect(request, user)

    def save_user(self, request, sociallogin, form=None):

        user = super().save_user(request, sociallogin, form)
        if not user.role:
            user.role = CustomUser.ROLE_CUSTOMER
        user.is_active = True
        user.email_verified = True
        user.save()
        return user
