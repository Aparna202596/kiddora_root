from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from accounts.models import CustomUser, UserAddress
from products.models import Product, Category, ProductVariant
import uuid
from django.conf import settings

#  COUPON
#  User-applied discount codes at checkout.
class CouponUsage(models.Model):
    """Tracks how many times each user has used a specific coupon."""
    coupon = models.ForeignKey('Coupon', on_delete=models.CASCADE, related_name='usages')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )
    times_used = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('coupon', 'user')
        verbose_name = 'Coupon Usage'
        verbose_name_plural = 'Coupon Usages'

class Coupon(models.Model):
    DISCOUNT_TYPE_CHOICES = (
        ("PERCENT", "Percentage"),
        ("FLAT",    "Flat Amount"),
    )

    code = models.CharField(max_length=20, unique=True)
    discount_type = models.CharField(max_length=10, choices=DISCOUNT_TYPE_CHOICES)
    #   PERCENT type → discount_value = 10  means 10%
    #   FLAT type    → discount_value = 100 means ₹100 off
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(1)])
    max_discount = models.DecimalField(max_digits=10, decimal_places=2,null=True, blank=True)
    min_order_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    start_date = models.DateTimeField(default=timezone.now)
    expiry_date = models.DateTimeField()
    usage_limit = models.PositiveIntegerField(default=1)
    used_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-created_at"]
    def get_user_usage(self, user):
        """Return how many times THIS user has used the coupon."""
        try:
            return self.usages.get(user=user).times_used
        except CouponUsage.DoesNotExist:
            return 0
        
    def is_valid(self):
        """Check coupon is active, not deleted, and within its date window."""
        now = timezone.now()
        return (self.is_active and not self.is_deleted and self.start_date <= now <= self.expiry_date)

    def clean(self):
        if self.discount_type == "PERCENT":
            if self.discount_value > 100:
                raise ValidationError("Percentage discount cannot exceed 100.")
        if self.expiry_date and self.start_date and self.expiry_date <= self.start_date:
            raise ValidationError("Expiry date must be after start date.")

    def __str__(self):
        return f"{self.code} ({self.discount_type}: {self.discount_value})"

class Offer(models.Model):
    OFFER_TYPE_CHOICES = (
        ("PRODUCT", "Product Offer"),
        ("CATEGORY", "Category Offer"),
        ("REFERRAL", "Referral Offer"),
    )

    offer_type = models.CharField(max_length=20, choices=OFFER_TYPE_CHOICES)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True, related_name="offers")
    category = models.ForeignKey(Category, on_delete=models.CASCADE, null=True, blank=True, related_name="offers")
    discount_percent = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(100)])
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(null=True, blank=True)
    referral_coupon  = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True, related_name="referral_offers")
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        if self.offer_type == "PRODUCT" and not self.product:
            raise ValidationError("Product offer requires a product.")
        if self.offer_type == "CATEGORY" and not self.category:
            raise ValidationError("Category offer requires a category.")

    def is_valid(self):
        now = timezone.now()
        active = self.is_active and not self.is_deleted and self.start_date <= now
        if self.end_date:
            active = active and now <= self.end_date
        return active

    def __str__(self):
        target = self.product or self.category or "Referral"
        return f"{self.get_offer_type_display()} – {self.discount_percent}% on {target}"


#  CART
class Cart(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name="cart")
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True, related_name="carts")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cart – {self.user.email}"

class CartItem(models.Model):
    MAX_QTY_PER_PRODUCT = 5   # handle maximum quantity per product
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name="cart_items")
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("cart", "variant")
        ordering = ["-added_at"]

    def clean(self):
    #max quantity validation
        if self.quantity > self.MAX_QTY_PER_PRODUCT:
            raise ValidationError(
                f"Cannot add more than {self.MAX_QTY_PER_PRODUCT} of the same item."
            )
        if self.quantity < 1:
            raise ValidationError("Quantity must be at least 1.")

    def __str__(self):
        return f"{self.variant} × {self.quantity}"

#  ORDER
class Order(models.Model):
    ORDER_STATUS_CHOICES = (
        ("PENDING", "Pending"),
        ("CONFIRMED", "Confirmed"),
        ("SHIPPED", "Shipped"),
        ("OUT_FOR_DELIVERY", "Out for Delivery"),
        ("DELIVERED", "Delivered"),
        ("CANCELLED", "Cancelled"),
        ("RETURNED", "Returned")
    )
    PAYMENT_METHOD_CHOICES = (
        ("COD", "Cash on Delivery"),
        ("RAZORPAY","Razorpay"),
        ("PAYPAL","Paypal"),
        ("WALLET", "Wallet"),
    )
    PAYMENT_STATUS_CHOICES = (
        ("PENDING", "Pending"),
        ("PAID", "Paid"),
        ("FAILED", "Failed"),
        ("REFUNDED", "Refunded"),
        ("PARTIALLY_REFUNDED", "Partially Refunded"),
    )
    order_id = models.CharField(max_length=20, unique=True, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="orders")
    address = models.ForeignKey(UserAddress, on_delete=models.PROTECT, related_name="orders")
    order_status = models.CharField(max_length=20, choices=ORDER_STATUS_CHOICES, default="PENDING")
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default="COD")
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default="PENDING")
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    coupon_discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    shipping_charge = models.DecimalField(max_digits=10, decimal_places=2, default=100)
    final_amount = models.DecimalField(max_digits=10, decimal_places=2) #"total_amount - discount_amount - coupon_discount + shipping_charge"
    
    order_date = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["-order_date"]

    def save(self, *args, **kwargs):
        if not self.order_id:
            while True:
                oid = f"KIDO-{uuid.uuid4().hex[:10].upper()}"
                if not Order.objects.filter(order_id=oid).exists():
                    self.order_id = oid
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        return self.order_id
    
#  ORDER ITEM
class OrderItem(models.Model):
    ITEM_STATUS_CHOICES = (
        ("ACTIVE", "Active"),
        ("PENDING", "Pending"),
        ("CANCELLED", "Cancelled"),
        ("RETURN_REQUESTED", "Return Requested"),
        ("RETURN_APPROVED", "Return Approved"),
        ("RETURN_REJECTED", "Return Rejected"),
        ("REFUNDED", "Refunded"),
    )
    
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="order_items")
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, related_name="order_items")
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_price = models.DecimalField(max_digits=10, decimal_places=2) #"unit_price × quantity) - discount_amount"
    item_status = models.CharField(max_length=20, choices=ITEM_STATUS_CHOICES, default="ACTIVE")
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.TextField(blank=True, null=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        self.total_price = (self.unit_price * self.quantity) - self.discount_amount
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order.order_id} – {self.variant}"

class Return(models.Model):
    STATUS_CHOICES = (
        ("REQUESTED", "Requested"),
        ("APPROVED",  "Approved"),
        ("REJECTED",  "Rejected"),
        ("REFUNDED",  "Refunded"),
    )

    order_item = models.OneToOneField(OrderItem, on_delete=models.CASCADE, related_name="return_request")
    reason = models.TextField(help_text="Reason for return (mandatory per instructions).")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="REQUESTED")
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    admin_note = models.TextField(blank=True, null=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    locked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Return: {self.order_item} [{self.status}]"

#  REVIEW
#  User reviews for products. One review per user per product.
class Review(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="reviews")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField()
    is_approved = models.BooleanField(default=False)
    admin_reply = models.TextField(blank=True, null=True)
    replied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        unique_together = ("user", "product")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} → {self.product.product_name} ({self.rating}★)"

#  WISHLIST
# Per-user wishlist of products. One Wishlist per user, multiple WishlistItems per wishlist.
class Wishlist(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name="wishlist")

    def __str__(self):
        return f"Wishlist – {self.user.email}"

class WishlistItem(models.Model):
    wishlist = models.ForeignKey(Wishlist, on_delete=models.CASCADE, related_name="items")
    product  = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlist_items")
    added_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        unique_together = ("wishlist", "product")
        ordering = ["-added_at"]

    def __str__(self):
        return f"{self.wishlist.user.email} - {self.product.product_name}"

class Banner(models.Model):

    SLOT_CHOICES = (
        ("HERO", "Hero Carousel"),
        ("SECONDARY", "Secondary Banner"),
    )

    title = models.CharField(max_length=120)
    subtitle = models.CharField(max_length=200, blank=True)
    image = models.ImageField(upload_to="banners/")
    cta_text = models.CharField(max_length=40, default="Shop Now")
    cta_url = models.CharField(max_length=300, default="/products/user/products/")
    badge_text = models.CharField(max_length=40, blank=True)
    slot = models.CharField(max_length=20, choices=SLOT_CHOICES, default="HERO")
    display_order = models.PositiveIntegerField(default=0,validators=[MinValueValidator(0)])
    is_active = models.BooleanField(default=True)
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["display_order", "-created_at"]
        verbose_name = "Banner"
        verbose_name_plural = "Banners"

    def is_live(self):
        
        now = timezone.now()
        if not self.is_active:
            return False
        if self.start_date and now < self.start_date:
            return False
        if self.end_date and now > self.end_date:
            return False
        return True

    def __str__(self):
        return f"[{self.slot}] {self.title} (order={self.display_order})"