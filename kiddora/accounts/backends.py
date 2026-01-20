from django.contrib.auth.backends import ModelBackend
from accounts.models import CustomUser

class CustomBackend(ModelBackend):
    """
    Allows login using email instead of username.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            # Treat username as email
            user = CustomUser.objects.get(email=username)
        except CustomUser.DoesNotExist:
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
