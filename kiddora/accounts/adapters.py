from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.core.exceptions import MultipleObjectsReturned
from django.contrib.auth import get_user_model
from django.contrib import messages

from accounts.models import CustomUser

User = get_user_model()
# This adapter ensures that users logging in via social accounts are properly linked to existing accounts based on email, and that their status is updated accordingly.
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
            messages.error(request,"Multiple accounts found with this email. Please contact support.")
            return
        
        # Google has already verified the email, so it's safe to activate
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

# This method is called when a new social account is being created. 
# It ensures that the new user is active, has a verified email, and is assigned a default role if not already set.
    def save_user(self, request, sociallogin, form=None):

        user = super().save_user(request, sociallogin, form)
        if not user.role:
            user.role = CustomUser.ROLE_CUSTOMER
        user.is_active = True
        user.email_verified = True
        user.save()
        return user