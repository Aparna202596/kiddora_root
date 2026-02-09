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

class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="product_images/")
    is_default = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if self.is_default:
            ProductImage.objects.filter(product=self.product, is_default=True).update(is_default=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.product_name} Image"

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

class ProductVariant(models.Model):
    
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    ages = models.ManyToManyField(AgeGroup, related_name="variants")
    colors = models.ManyToManyField(Color, related_name="variants")
    barcode = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.product.product_name} Variant"

class Inventory(models.Model):
    variant = models.OneToOneField(ProductVariant, on_delete=models.CASCADE, related_name="inventory")
    quantity_available = models.PositiveIntegerField()
    quantity_reserved = models.PositiveIntegerField(default=0)
    quantity_sold = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.variant} Inventory"


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

    # def can_use(self, user):
    #     if not self.is_valid():
    #         return False
    #     if self.used_count >= self.usage_limit:
    #         return False
    #     if self.used_by.filter(id=user.id).exists():
    #         return False
    #     return True
    
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

    # def applies_to(self, product):
    #     if not self.is_active or self.is_deleted:
    #         return False
    #     if self.offer_type == "PRODUCT":
    #         return self.product == product
    #     if self.offer_type == "CATEGORY":
    #         return product.subcategory.category == self.category
    #     return False

    def __str__(self):
        return f"{self.offer_type} - {self.discount_percent}%"