from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model

User = get_user_model()

class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        """
        Auto-link Google account if email already exists
        """
        email = sociallogin.user.email
        if not email:
            return
        try:
            user = User.objects.get(email=email)
            sociallogin.connect(request, user)
        except User.DoesNotExist:
            pass
    def save_user(self, request, sociallogin, form=None):
        """
        Ensure social users are active and verified
        """
        user = super().save_user(request, sociallogin, form)
        user.is_active = True
        user.email_verified = True
        # default role
        if not user.role:
            user.role = User.ROLE_CUSTOMER
        user.save()
        return user