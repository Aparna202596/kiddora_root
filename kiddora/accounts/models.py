import re
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


# ── Reusable validators ───────────────────────────────────────────────────────

def validate_full_name(value):
    if not value or not value.strip():
        raise ValidationError("Full name is required.")
    value = value.strip()
    if value[0] == ' ':
        raise ValidationError("Full name must not start with a space.")
    if re.search(r'  +', value):
        raise ValidationError("Full name must not contain consecutive spaces.")
    if not re.fullmatch(r'[A-Za-z]+( [A-Za-z]+)*', value):
        raise ValidationError(
            "Full name may only contain letters (A–Z, a–z) and single spaces between words. "
            "Numbers and special characters are not allowed."
        )


def validate_phone(value):
    if not value or not value.strip():
        raise ValidationError("Phone number is required.")
    if not re.fullmatch(r'\d{10}', value.strip()):
        raise ValidationError(
            "Phone number must be exactly 10 digits (numbers only, no spaces or special characters)."
        )

# ── CustomUser ────────────────────────────────────────────────────────────────

class CustomUser(AbstractUser):
    ROLE_ADMIN    = "ADMIN"
    ROLE_CUSTOMER = "CUSTOMER"
    ROLE_CHOICES  = ((ROLE_ADMIN, "Admin"), (ROLE_CUSTOMER, "Customer"))

    GENDER_MALE   = "male"
    GENDER_FEMALE = "female"
    GENDER_CHOICES = ((GENDER_MALE, "Male"), (GENDER_FEMALE, "Female"))

    username = models.CharField(max_length=150, unique=True, null=True, blank=True)
    
    email = models.EmailField(unique=True)
    
    phone = models.CharField(
        max_length=10, unique=True, null=True, blank=True,
        validators=[validate_phone],
    )
    
    full_name = models.CharField(
        max_length=100, null=True, blank=True,
        validators=[validate_full_name],
    )
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, null=True, blank=True)
    
    role = models.CharField(
        max_length=20, choices=ROLE_CHOICES, default=ROLE_CUSTOMER, db_index=True)
    
    email_verified  = models.BooleanField(default=False)
    
    profile_image = models.ImageField(upload_to="profile_images/", null=True, blank=True)
    
    otp = models.CharField(max_length=6, null=True, blank=True)
    
    otp_created_at = models.DateTimeField(null=True, blank=True)
    
    is_active = models.BooleanField(default=True)
    
    is_staff = models.BooleanField(default=False)
    
    is_superuser = models.BooleanField(default=False)
    
    last_login = models.DateTimeField(null=True, blank=True)
    
    date_joined = models.DateTimeField(default=timezone.now)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    updated_at = models.DateTimeField(auto_now=True)
    
    pending_email = models.EmailField(null=True, blank=True)
    
    blocked_at = models.DateTimeField(null=True, blank=True)
    
    timezone = models.CharField(max_length=50, default="UTC")
    
    is_deleted = models.BooleanField(default=False)
    
    deleted_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD  = "email"
    REQUIRED_FIELDS = ["username"]

    def clean(self):
        super().clean()
        if self.full_name:
            validate_full_name(self.full_name)
        if self.phone:
            validate_phone(self.phone)

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = self.ROLE_ADMIN
        # Normalise before saving
        if self.full_name:
            self.full_name = ' '.join(self.full_name.strip().split())
        if self.phone:
            self.phone = self.phone.strip()
        if self.pk:
            try:
                old = CustomUser.objects.get(pk=self.pk)
                if old.profile_image and old.profile_image != self.profile_image:
                    try:
                        old.profile_image.delete(save=False)
                    except Exception:
                        pass
            except CustomUser.DoesNotExist:
                pass
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.is_active  = False
        self.save(update_fields=["is_deleted", "deleted_at", "is_active"])

    def hard_delete(self):
        super().delete()

    def __str__(self):
        return self.email


#  ────────────────────────────────────────────────── USER ADDRESS ──────────────────────────────────────────────────
class UserAddress(models.Model):
    ADDRESS_HOME = "home"
    ADDRESS_WORK = "work"
    ADDRESS_OTHER = "other"

    ADDRESS_TYPE_CHOICES = (
        (ADDRESS_HOME, "Home"),
        (ADDRESS_WORK, "Work"),
        (ADDRESS_OTHER, "Other"),
    )

    user = models.ForeignKey(
        CustomUser, on_delete=models.PROTECT, related_name="addresses"
    )

    id = models.BigAutoField(primary_key=True)

    address_line1 = models.CharField(max_length=200)

    address_line2 = models.CharField(max_length=200, blank=True, null=True, default="")

    city = models.CharField(max_length=100)

    state = models.CharField(max_length=100)

    country = models.CharField(max_length=100)

    pincode = models.CharField(max_length=10)

    address_type = models.CharField(max_length=10, choices=ADDRESS_TYPE_CHOICES)

    is_default = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    is_deleted = models.BooleanField(default=False)

    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "User Addresses"

    def delete(self, *args, **kwargs):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at"])

    def __str__(self):
        return f"{self.user.email} - {self.city}"
