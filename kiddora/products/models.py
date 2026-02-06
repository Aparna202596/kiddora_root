from django.db import models
from django.utils import timezone
class Category(models.Model):
    
    category_name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.category_name

class SubCategory(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="subcategories")
    subcategory_name = models.CharField(max_length=100)
    class Meta:
        unique_together = ("category", "subcategory_name")
    def __str__(self):
        return self.subcategory_name

class Product(models.Model):

    AGE_CHOICES = [
    ("0-6 months", "0-6 months"),
    ("6-12 months", "6-12 months"),
    ("1-2 years", "1-2 years"),
    ("2-3 years", "2-3 years"),
    ("3-5 years", "3-5 years"),
    ("5-7 years", "5-7 years"),
    ("7-10 years", "7-10 years"),
    ("10-12 years", "10-12 years"),
    ("12-15 years", "12-15 years"),
    ]

    GENDER_CHOICES = [
        ('boy', 'Boy'),
        ('girl', 'Girl'),
        ('newborn', 'Newborn'),
        ('unisex', 'Unisex'),
    ]
    subcategory = models.ForeignKey(SubCategory, on_delete=models.CASCADE, related_name="products")
    product_name = models.CharField(max_length=200)
    brand = models.CharField(max_length=100)
    gender = models.CharField(max_length=10,choices=GENDER_CHOICES,default='unisex')
    age_group = models.CharField(max_length=15, choices=AGE_CHOICES, default="0-6 months")
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_percent = models.PositiveIntegerField(default=0)
    final_price = models.DecimalField(max_digits=10, decimal_places=2)
    sku = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    stock = models.PositiveIntegerField(default=0)
    
    def __str__(self):
        return self.product_name
class ProductVariant(models.Model):
    SIZE_CHOICES = [
    ("XS", "XS"),
    ("S", "S"),
    ("M", "M"),
    ("L", "L"),
    ("XL", "XL"),
    ]
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    color = models.CharField(max_length=50)
    size = models.CharField(max_length=5, choices=SIZE_CHOICES,default="M")
    barcode = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.product.product_name} ({self.color}, {self.size})"

class Inventory(models.Model):
    variant = models.OneToOneField(ProductVariant, on_delete=models.CASCADE, related_name="inventory")
    quantity_available = models.PositiveIntegerField()
    quantity_reserved = models.PositiveIntegerField(default=0)
    quantity_sold = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

class Coupon(models.Model):
    DISCOUNT_TYPE_CHOICES = (
        ("PERCENT", "Percentage"),
        ("FLAT", "Flat"),
    )
    code = models.CharField(max_length=20, unique=True)
    discount_type = models.CharField(max_length=10, choices=DISCOUNT_TYPE_CHOICES)
    discount_value = models.PositiveIntegerField()
    min_order_amount = models.DecimalField(max_digits=10, decimal_places=2)
    max_discount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    usage_limit = models.PositiveIntegerField()
    used_by = models.ManyToManyField("accounts.CustomUser", blank=True)
    is_active = models.BooleanField(default=True)
    expiry_date = models.DateTimeField()
    is_deleted = models.BooleanField(default=False)
    used_count = models.PositiveIntegerField(default=0)

    def is_valid(self):
        return self.is_active and not self.is_deleted and timezone.now() <= self.expiry_date

    def can_use(self, user):
        if not self.is_valid():
            return False
        if self.used_count >= self.usage_limit:
            return False
        if self.used_by.filter(id=user.id).exists():
            return False
        return True
    
    def __str__(self):
        return self.code
    
class Offer(models.Model):
    OFFER_TYPE_CHOICES = (
        ("PRODUCT", "Product"),
        ("CATEGORY", "Category"),
    )
    offer_type = models.CharField(max_length=20, choices=OFFER_TYPE_CHOICES)
    discount_percent = models.PositiveIntegerField()
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, null=True, blank=True)
    priority = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)

    def applies_to(self, product):
        if not self.is_active or self.is_deleted:
            return False
        if self.offer_type == "PRODUCT":
            return self.product == product
        if self.offer_type == "CATEGORY":
            return product.subcategory.category == self.category
        return False

    def __str__(self):
        return f"{self.offer_type} - {self.discount_percent}%"