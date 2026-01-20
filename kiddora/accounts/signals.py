from allauth.socialaccount.signals import social_account_added
from django.db.models.signals import post_save
from django.dispatch import receiver
from accounts.models import CustomUser
from cart.models import Cart
from wishlist.models import Wishlist
from wallet.models import Wallet

@receiver(post_save, sender=CustomUser)
def create_user_dependencies(sender, instance, created, **kwargs):
    if created and instance.role == "customer":
        Cart.objects.create(user=instance)
        Wishlist.objects.create(user=instance)
        Wallet.objects.create(user=instance)

@receiver(social_account_added)
def set_role_on_social_login(request, sociallogin, **kwargs):
    user = sociallogin.user

    if not user.role:
        user.role = CustomUser.ROLE_CUSTOMER
        user.is_active = True
        user.email_verified = True
        user.save()