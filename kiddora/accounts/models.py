from django.contrib.auth.models import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
import uuid

class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(email, password, **extra_fields)
class CustomUser(AbstractUser):
    username=None
    #username=models.CharField(max_length=50,null=True, blank=True)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True)
    full_name = models.CharField(max_length=100, null=True, blank=True)
    email_verified = models.BooleanField(default=True)
    profile_image = models.ImageField(upload_to="profiles/", null=True, blank=True)
    gender = models.CharField(max_length=10, choices=[('male','Male'),('female','Female')],blank=True)
    
    ROLE_ADMIN = "admin"
    ROLE_CUSTOMER = "customer"
    role = models.CharField(
        max_length=20,
        choices=[(ROLE_ADMIN, "Admin"), (ROLE_CUSTOMER, "Customer")],
        default=ROLE_CUSTOMER)
    
    otp = models.CharField(max_length=6, null=True, blank=True)
    otp_created_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    pending_email = models.EmailField(null=True, blank=True)
    
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    
    objects = CustomUserManager() 
    
    def __str__(self):
        return self.email or self.username


class UserAddress(models.Model):
    ADDRESS_HOME = "home"
    ADDRESS_OFFICE = "office"

    ADDRESS_TYPE_CHOICES = (
        (ADDRESS_HOME, "Home"),
        (ADDRESS_OFFICE, "Office"),
    )

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="addresses")
    address_line1 = models.CharField(max_length=200)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)
    address_type = models.CharField(max_length=20, choices=ADDRESS_TYPE_CHOICES)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.full_name} - {self.city}"

class PasswordResetToken(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        return timezone.now() > self.created_at + timezone.timedelta(minutes=10)
    
    def __str__(self):
        return f"{self.user.email} - reset token"    