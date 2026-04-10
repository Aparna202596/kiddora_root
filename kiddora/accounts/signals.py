from accounts.models import CustomUser
from allauth.socialaccount.signals import social_account_added
from django.db.models.signals import post_save
from django.dispatch import receiver
from payments.models import Wallet
from shopcore.models import Cart, Wishlist

@receiver(post_save, sender=CustomUser)
def create_user_dependencies(sender, instance, created, **kwargs):

    if created and instance.role == "customer":
        Cart.objects.create(user=instance)
        Wishlist.objects.create(user=instance)
        Wallet.objects.create(user=instance)


# This signal handler ensures that when a user logs in via a social account for the first time,
# they are assigned the "customer" role, marked as active, and their email is verified.
@receiver(social_account_added)
def set_role_on_social_login(request, sociallogin, **kwargs):

    user = sociallogin.user
    if not user.role:
        user.role = CustomUser.ROLE_CUSTOMER
        user.is_active = True
        user.email_verified = True
        user.save()
