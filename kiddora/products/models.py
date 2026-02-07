from django.db import models
from django.utils import timezone
import uuid

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
    GENDER_CHOICES = [
        ('boy', 'Boy'),
        ('girl', 'Girl'),
        ('newborn', 'Newborn'),
        ('unisex', 'Unisex'),
    ]

    FABRIC_CHOICES = [
        ("Cotton", "Cotton"),
        ("Polyester", "Polyester"),
        ("Wool", "Wool"),
        ("Silk", "Silk"),
        ("Denim", "Denim"),
        ("Linen", "Linen"),
        ("Fleece", "Fleece"),
        ("Velvet", "Velvet"),
        ("Organic_cotton", "Organic Cotton"),
        ("Wool_blends", "Wool Blends"),
        ("Other", "Other"),
    ]

    subcategory = models.ForeignKey(SubCategory, on_delete=models.CASCADE, related_name="products")
    product_name = models.CharField(max_length=200)
    brand = models.CharField(max_length=100)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, default='unisex')
    fabric = models.CharField(max_length=20, choices=FABRIC_CHOICES, default="Other")
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_percent = models.PositiveIntegerField(default=0)
    final_price = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    sku = models.CharField(max_length=100, unique=True, blank=True)
    about_product = models.TextField(blank=True, help_text="Detailed description of the product")
    is_active = models.BooleanField(default=True)
    stock = models.PositiveIntegerField(default=0)

    def save(self, *args, **kwargs):
        # Generate SKU if not exists
        if not self.sku:
            while True:
                new_sku = f"KID-{uuid.uuid4().hex[:6].upper()}"
                if not Product.objects.filter(sku=new_sku).exists():
                    self.sku = new_sku
                    break
        # Calculate final price
        self.final_price = self.base_price * (1 - self.discount_percent / 100)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.product_name

class AgeGroup(models.Model):
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
    age = models.CharField(max_length=20, choices=AGE_CHOICES, unique=True, default="0-6 months")

    def __str__(self):
        return self.age

class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="product_images/")
    is_default = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if self.is_default:
            ProductImage.objects.filter(product=self.product, is_default=True).update(is_default=False)
        elif not self.product.images.filter(is_default=True).exists():
            self.is_default = True
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.product_name} Image"

class ProductVariant(models.Model):
    SIZE_CHOICES = [
        ("NB", "NB"),
        ("XS", "XS"),
        ("S", "S"),
        ("M", "M"),
        ("L", "L"),
        ("XL", "XL"),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    age_group = models.ManyToManyField(AgeGroup, related_name="variants")
    color = models.CharField(max_length=50)
    size = models.CharField(max_length=10, choices=SIZE_CHOICES, default="M")
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

    def __str__(self):
        return f"{self.variant} Inventory"
