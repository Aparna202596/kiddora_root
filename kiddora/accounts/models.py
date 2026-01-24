from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
import uuid

class CustomUser(AbstractUser):
    ROLE_ADMIN = "admin"
    ROLE_CUSTOMER = "customer"

    ROLE_CHOICES = ((ROLE_ADMIN, "Admin"),(ROLE_CUSTOMER, "Customer"),)

    # Override fields
    username = models.CharField(max_length=150,unique=True,null=True,blank=True)
    email = models.EmailField(unique=True,null=False,blank=False)
    phone = models.CharField(max_length=20,unique=True,null=True,blank=True)
    full_name = models.CharField(max_length=100,null=True,blank=True)
    role = models.CharField(max_length=20,choices=ROLE_CHOICES,db_index=True)
    email_verified = models.BooleanField(default=False)
    profile_image = models.ImageField(upload_to="profile_images/",null=True,blank=True)
    otp = models.CharField(max_length=6,null=True,blank=True)
    otp_created_at = models.DateTimeField(null=True,blank=True)
    is_active = models.BooleanField(default=True)
    is_superuser = models.BooleanField(default=False)
    last_login = models.DateTimeField(null=True,blank=True,)
    date_joined = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    pending_email = models.EmailField(null=True, blank=True)
    blocked_at = models.DateTimeField(null=True, blank=True)
    
    # Authentication settings
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def __str__(self):
        return self.email

class UserAddress(models.Model):
    ADDRESS_HOME = "home"
    ADDRESS_WORK = "work"
    ADDRESS_OTHER = "other"

    ADDRESS_TYPE_CHOICES = ((ADDRESS_HOME, "Home"),(ADDRESS_WORK, "Work"),(ADDRESS_OTHER, "Other"),)

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="addresses"
    )
    id = models.BigAutoField(primary_key=True)
    address_line1 = models.CharField(max_length=200)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)
    address_type = models.CharField(max_length=10,choices=ADDRESS_TYPE_CHOICES)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        verbose_name_plural = "User Addresses"

    def __str__(self):
        return f"{self.user.email} - {self.city}"
