from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import models
from decimal import Decimal
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

    subcategory = models.ForeignKey("SubCategory", on_delete=models.CASCADE, related_name="products")
    product_name = models.CharField(max_length=200)
    brand = models.CharField(max_length=100)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, default="unisex")
    fabric = models.CharField(max_length=20, choices=FABRIC_CHOICES, default="Other")
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_percent = models.PositiveIntegerField(default=0)
    final_price = models.DecimalField(max_digits=10,decimal_places=2,editable=False)
    about_product = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        base = Decimal(self.base_price or 0)
        discount = Decimal(self.discount_percent or 0)
        self.final_price = base - (base * discount / Decimal("100"))
        super().save(*args, **kwargs)

    def __str__(self):
        return self.product_name
    
class Color(models.Model):

    COLOR_CHOICES = [
        ("White", "White"),
        ("Black", "Black"),
        ("Gray", "Gray"),
        ("Light Gray", "Light Gray"),
        ("Charcoal", "Charcoal"),

        ("Red", "Red"),
        ("Maroon", "Maroon"),
        ("Crimson", "Crimson"),
        ("Burgundy", "Burgundy"),
        ("Coral", "Coral"),

        ("Pink", "Pink"),
        ("Baby Pink", "Baby Pink"),
        ("Hot Pink", "Hot Pink"),
        ("Rose", "Rose"),
        ("Blush", "Blush"),

        ("Orange", "Orange"),
        ("Peach", "Peach"),
        ("Rust", "Rust"),
        ("Burnt Orange", "Burnt Orange"),
        ("Amber", "Amber"),

        ("Yellow", "Yellow"),
        ("Mustard", "Mustard"),
        ("Gold", "Gold"),
        ("Lemon", "Lemon"),
        ("Ivory", "Ivory"),

        ("Green", "Green"),
        ("Olive", "Olive"),
        ("Mint", "Mint"),
        ("Lime", "Lime"),
        ("Forest Green", "Forest Green"),

        ("Blue", "Blue"),
        ("Sky Blue", "Sky Blue"),
        ("Navy Blue", "Navy Blue"),
        ("Royal Blue", "Royal Blue"),
        ("Teal", "Teal"),

        ("Purple", "Purple"),
        ("Lavender", "Lavender"),
        ("Violet", "Violet"),
        ("Plum", "Plum"),
        ("Lilac", "Lilac"),

        ("Brown", "Brown"),
        ("Beige", "Beige"),
        ("Tan", "Tan"),
        ("Khaki", "Khaki"),
        ("Chocolate", "Chocolate"),
    ]

    color = models.CharField(max_length=30, choices=COLOR_CHOICES, unique=True)

    def __str__(self):
        return self.color

class AgeGroup(models.Model):

    AGE_CHOICES = [
        ("Newborn", "Newborn"),
        ("0-3 months", "0-3 months"),
        ("3-6 months", "3-6 months"),
        ("6-9 months", "6-9 months"),
        ("9-12 months", "9-12 months"),
        ("12-18 months", "12-18 months"),
        ("18-24 months", "18-24 months"),
        ("2-3 years", "2-3 years"),
        ("3-4 years", "3-4 years"),
        ("4-5 years", "4-5 years"),
        ("5-6 years", "5-6 years"),
        ("6-7 years", "6-7 years"),
        ("7-8 years", "7-8 years"),
        ("8-9 years", "8-9 years"),
        ("9-10 years", "9-10 years"),
        ("10-11 years", "10-11 years"),
        ("11-12 years", "11-12 years"),
        ("12-13 years", "12-13 years"),
        ("13-14 years", "13-14 years"),
        ("14-15 years", "14-15 years"),
    ]

    age = models.CharField(max_length=20, choices=AGE_CHOICES, unique=True)

    def __str__(self):
        return self.age

class ProductVariant(models.Model):

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    color = models.ForeignKey(Color,on_delete=models.PROTECT, related_name="variants")
    age_group = models.ForeignKey(AgeGroup,on_delete=models.PROTECT,related_name="variants")
    sku = models.CharField(max_length=100, unique=True, blank=True)
    barcode = models.CharField(max_length=100, unique=True, blank=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("product", "color", "age_group")

    def generate_unique_sku(self):
        while True:
            sku = f"KID-{uuid.uuid4().hex[:8].upper()}"
            if not ProductVariant.objects.filter(sku=sku).exists():
                return sku

    def generate_unique_barcode(self):
        while True:
            barcode = uuid.uuid4().int % 10**12
            barcode = str(barcode).zfill(12)
            if not ProductVariant.objects.filter(barcode=barcode).exists():
                return barcode

    def save(self, *args, **kwargs):

        if not self.sku:
            self.sku = self.generate_unique_sku()

        if not self.barcode:
            self.barcode = self.generate_unique_barcode()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.product_name} | {self.color} | {self.age_group}"

class ProductImage(models.Model):

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")

    image1 = models.ImageField(upload_to="product_images/",blank=True, null=True)
    image2 = models.ImageField(upload_to="product_images/",blank=True, null=True)
    image3 = models.ImageField(upload_to="product_images/",blank=True, null=True)
    image4 = models.ImageField(upload_to="product_images/", blank=True, null=True)
    image5 = models.ImageField(upload_to="product_images/", blank=True, null=True)

    is_default = models.BooleanField(default=False)

    def clean(self):
        if not (self.image1 and self.image2 and self.image3):
            raise ValidationError("Minimum 3 images are required.")

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.is_default:
            ProductImage.objects.filter(product=self.product, is_default=True).update(is_default=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.product_name} Images"

class Inventory(models.Model):

    variant = models.OneToOneField(ProductVariant,on_delete=models.CASCADE,related_name="inventory")
    quantity_available = models.PositiveIntegerField()
    quantity_reserved = models.PositiveIntegerField(default=0)
    quantity_sold = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.variant} Inventory"
