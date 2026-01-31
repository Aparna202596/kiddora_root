from django.contrib.auth.backends import ModelBackend
from django.db.models import Q
from accounts.models import CustomUser
from django.contrib.auth import get_user_model

User = get_user_model()
class EmailBackend(ModelBackend):
    """
    Authenticate using email + password
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None

        try:
            user = User.objects.get(Q(email__iexact=username))
        except User.DoesNotExist:
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user

        return None
