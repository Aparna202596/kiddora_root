import uuid
from decimal import Decimal

from accounts.models import CustomUser, UserAddress
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from products.models import Product, ProductVariant
from django.db import models
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver


#   ────────────────────────────────────────────────── COUPON ──────────────────────────────────────────────────
class Coupon(models.Model):
    DISCOUNT_TYPE_CHOICES = (
        ("PERCENT", "Percentage"),
        ("FLAT", "Flat Amount"),
    )

    COUPON_TYPE_CHOICES = (
        ("PUBLIC", "Public"),
        ("REFERRAL", "Referral"),
    )

    code = models.CharField(max_length=20, unique=True)

    coupon_type = models.CharField(
        max_length=20, choices=COUPON_TYPE_CHOICES, default="PUBLIC"
    )

    discount_type = models.CharField(max_length=10, choices=DISCOUNT_TYPE_CHOICES)

    discount_value = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(1)]
    )

    max_discount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

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
        return (
            self.is_active
            and not self.is_deleted
            and self.start_date <= now <= self.expiry_date
        )

    def clean(self):
        if self.discount_type == "PERCENT":
            if self.discount_value > 100:
                raise ValidationError("Percentage discount cannot exceed 100.")
        if self.expiry_date and self.start_date and self.expiry_date <= self.start_date:
            raise ValidationError("Expiry date must be after start date.")

    def __str__(self):
        return f"{self.code} ({self.discount_type}: {self.discount_value})"


class CouponUsage(models.Model):
    coupon = models.ForeignKey(
        "Coupon", on_delete=models.CASCADE, related_name="usages"
    )

    user = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="coupon_usages"
    )

    times_used = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("coupon", "user")
        verbose_name = "Coupon Usage"
        verbose_name_plural = "Coupon Usages"


# ────────────────────────────────────────────────── OFFER ──────────────────────────────────────────────────
class Offer(models.Model):
    OFFER_TYPE_CHOICES = (
        ("PRODUCT", "Product Offer"),
        ("CATEGORY", "Category Offer"),
        ("REFERRAL", "Referral Offer"),
    )
    offer_type = models.CharField(max_length=20, choices=OFFER_TYPE_CHOICES)
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="offers",
    )
    category = models.ForeignKey(
        "products.Category",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="offers",
    )
    discount_percent = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)]
    )
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(null=True, blank=True)
    referral_coupon = models.ForeignKey(
        "Coupon",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="referral_offers",
    )
    referrer_coupon = models.ForeignKey(
        "Coupon",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="referrer_offers",
    )
    new_user_coupon = models.ForeignKey(
        "Coupon",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="new_user_offers",
    )
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

@receiver(post_save, sender=Offer)
def refresh_products_on_offer_change(sender, instance, **kwargs):
    for product in instance.applied_to_products.select_related("product_offer").iterator():
        product.save()

#   ────────────────────────────────────────────────── REFERRAL ──────────────────────────────────────────────────
class ReferralCode(models.Model):
    user = models.OneToOneField(
        CustomUser, on_delete=models.CASCADE, related_name="referral_record"
    )

    code = models.CharField(max_length=20, unique=True)

    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @classmethod
    def fresh_code(cls) -> str:
        """Generate a new referral code (used by signal and views)."""
        return f"KIDDREF-{uuid.uuid4().hex[:8].upper()}"

    @property
    def use_count(self):
        return self.uses.count()

    def __str__(self):
        return f"{self.user.email} — {self.code}"


class ReferralUse(models.Model):

    referral_code = models.ForeignKey(
        ReferralCode, on_delete=models.CASCADE, related_name="uses"
    )

    referred_user = models.OneToOneField(
        CustomUser, on_delete=models.CASCADE, related_name="referred_via"
    )

    coupon_awarded = models.ForeignKey(
        Coupon,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="referral_uses",
    )

    new_user_coupon = models.ForeignKey(
        Coupon,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="new_user_referral_uses",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.referral_code.user.email} → {self.referred_user.email}"


#   ────────────────────────────────────────────────── WISHLIST ──────────────────────────────────────────────────
class Wishlist(models.Model):
    user = models.OneToOneField(
        CustomUser, on_delete=models.CASCADE, related_name="wishlist"
    )

    def __str__(self):
        return f"Wishlist – {self.user.email}"


class WishlistItem(models.Model):
    wishlist = models.ForeignKey(
        Wishlist, on_delete=models.CASCADE, related_name="items"
    )

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="wishlist_items"
    )

    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("wishlist", "product")
        ordering = ["-added_at"]

    def __str__(self):
        return f"{self.wishlist.user.email} - {self.product.product_name}"


#   ────────────────────────────────────────────────── CART ──────────────────────────────────────────────────
class Cart(models.Model):
    user = models.OneToOneField(
        CustomUser, on_delete=models.CASCADE, related_name="cart"
    )

    coupon = models.ForeignKey(
        Coupon, on_delete=models.SET_NULL, null=True, blank=True, related_name="carts"
    )

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cart – {self.user.email}"


class CartItem(models.Model):
    MAX_QTY_PER_PRODUCT = 5  

    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")

    variant = models.ForeignKey(
        ProductVariant, on_delete=models.CASCADE, related_name="cart_items"
    )

    quantity = models.PositiveIntegerField(default=1)

    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("cart", "variant")
        ordering = ["-added_at"]

    def clean(self):
        if self.quantity > self.MAX_QTY_PER_PRODUCT:
            raise ValidationError(
                f"Cannot add more than {self.MAX_QTY_PER_PRODUCT} of the same item."
            )
        if self.quantity < 1:
            raise ValidationError("Quantity must be at least 1.")

    def __str__(self):
        return f"{self.variant} × {self.quantity}"


#   ────────────────────────────────────────────────── ORDER ──────────────────────────────────────────────────
class Order(models.Model):
    ORDER_STATUS_CHOICES = (
        ("PENDING", "Pending"),
        ("CONFIRMED", "Confirmed"),
        ("SHIPPED", "Shipped"),
        ("OUT_FOR_DELIVERY", "Out for Delivery"),
        ("DELIVERED", "Delivered"),
        ("CANCELLED", "Cancelled"),
        ("RETURNED", "Returned"),
        ("ORDER NOT PLACED", "Order Not Placed"),
    )
    PAYMENT_METHOD_CHOICES = (
        ("COD", "Cash on Delivery"),
        ("RAZORPAY", "Razorpay"),
        ("PAYPAL", "Paypal"),
        ("WALLET", "Wallet"),
    )
    PAYMENT_STATUS_CHOICES = (
        ("PENDING", "Pending"),
        ("INITIATED", "Initiated"),
        ("PAID", "Paid"),
        ("FAILED", "Failed"),
        ("REFUNDED", "Refunded"),
        ("PARTIALLY_REFUNDED", "Partially Refunded"),
        ("CANCELLED", "Cancelled"),
    )
    FREE_SHIPPING_THRESHOLD = Decimal("1000")
    DEFAULT_SHIPPING_CHARGE = Decimal("100")

    order_id = models.CharField(max_length=20, unique=True, editable=False)

    user = models.ForeignKey(
        CustomUser, on_delete=models.PROTECT, related_name="orders"
    )

    address = models.ForeignKey(
        UserAddress, on_delete=models.PROTECT, related_name="orders"
    )

    order_status = models.CharField(
        max_length=20, choices=ORDER_STATUS_CHOICES, default="PENDING"
    )

    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_METHOD_CHOICES, default="COD"
    )

    payment_status = models.CharField(
        max_length=20, choices=PAYMENT_STATUS_CHOICES, default="PENDING"
    )

    coupon = models.ForeignKey(
        Coupon, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )

    coupon_discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    total_amount = models.DecimalField(max_digits=10, decimal_places=2)

    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    shipping_charge = models.DecimalField(max_digits=10, decimal_places=2, default=100)

    final_amount = models.DecimalField(max_digits=10, decimal_places=2)

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

        if self.shipping_charge is None or self.shipping_charge == Decimal("100"):
            self.shipping_charge = self.calculate_shipping()

        if self.final_amount == 0 or self.final_amount is None:
            self.final_amount = (
                self.total_amount
                - self.discount_amount
                - self.coupon_discount
                + self.shipping_charge
            )

        super().save(*args, **kwargs)

    def calculate_shipping(self) -> Decimal:
        if self.total_amount >= self.FREE_SHIPPING_THRESHOLD:
            return Decimal("0")
        return self.DEFAULT_SHIPPING_CHARGE

    @property
    def is_free_shipping(self) -> bool:
        return self.shipping_charge == 0

    def __str__(self):
        return self.order_id


#  ────────────────────────────────────────────────── ORDER ITEM ──────────────────────────────────────────────────
class OrderItem(models.Model):
    ITEM_STATUS_CHOICES = (
        ("ACTIVE", "Active"),
        ("PENDING", "Pending"),
        ("CANCELLED", "Cancelled"),
        ("ORDER NOT PLACED", "Order Not Placed"),
        ("RETURN_REQUESTED", "Return Requested"),
        ("RETURN_APPROVED", "Return Approved"),
        ("RETURN_REJECTED", "Return Rejected"),
        ("REFUNDED", "Refunded"),
    )

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="order_items"
    )

    variant = models.ForeignKey(
        ProductVariant, on_delete=models.PROTECT, related_name="order_items"
    )

    quantity = models.PositiveIntegerField()

    cancelled_quantity = models.PositiveIntegerField(default=0)

    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    item_status = models.CharField(
        max_length=20, choices=ITEM_STATUS_CHOICES, default="ACTIVE"
    )

    delivered_at = models.DateTimeField(null=True, blank=True)

    cancel_reason = models.TextField(blank=True, null=True)

    cancelled_at = models.DateTimeField(null=True, blank=True)

    @property
    def active_quantity(self) -> int:
        """Units still active (not cancelled)."""
        return max(0, self.quantity - self.cancelled_quantity)

    @property
    def active_total(self):
        """Price for active units only, proportional to discount."""
        if self.quantity == 0:
            return Decimal("0")
        unit_net = self.total_price / self.quantity  
        return (unit_net * self.active_quantity).quantize(Decimal("0.01"))

    def save(self, *args, **kwargs):
        self.total_price = (self.unit_price * self.quantity) - self.discount_amount
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order.order_id} – {self.variant}"


# ────────────────────────────────────────────────── RETURN ──────────────────────────────────────────────────
class Return(models.Model):
    STATUS_CHOICES = (
        ("REQUESTED", "Requested"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("REFUNDED", "Refunded"),
    )

    order_item = models.OneToOneField(
        OrderItem, on_delete=models.CASCADE, related_name="return_request"
    )

    reason = models.TextField(
        help_text="Reason for return (mandatory per instructions)."
    )

    return_quantity = models.PositiveIntegerField(default=0)

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="REQUESTED"
    )

    refund_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    admin_note = models.TextField(blank=True, null=True)

    updated_at = models.DateTimeField(null=True, blank=True)

    approved_at = models.DateTimeField(null=True, blank=True)

    refunded_at = models.DateTimeField(null=True, blank=True)

    locked = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def per_unit_refund(self) -> Decimal:
        """Net price per unit after discount, used for partial refunds."""
        qty = self.order_item.quantity
        if not qty:
            return Decimal("0")
        return (self.order_item.total_price / qty).quantize(Decimal("0.01"))

    @property
    def calculated_refund_amount(self) -> Decimal:
        qty = self.return_quantity or self.order_item.active_quantity
        return (self.per_unit_refund * qty).quantize(Decimal("0.01"))

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Return: {self.order_item} [{self.status}]"


#   ────────────────────────────────────────────────── REVIEW ──────────────────────────────────────────────────
class Review(models.Model):
    """User reviews for products. One review per user per product."""

    user = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="reviews"
    )

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="reviews"
    )

    rating = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )

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


#   ────────────────────────────────────────────────── BANNER ──────────────────────────────────────────────────
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

    display_order = models.PositiveIntegerField(
        default=0, validators=[MinValueValidator(0)]
    )

    is_active = models.BooleanField(default=True)

    start_date = models.DateTimeField(null=True, blank=True)

    end_date = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["display_order", "-created_at"]
        verbose_name = "Banner"
        verbose_name_plural = "Banners"

    def is_live(self):

        if not self.is_active:
            return False

        now = timezone.now()

        if self.start_date and now < self.start_date:
            return False

        if self.end_date and now > self.end_date:
            return False

        return True

    def __str__(self):
        return f"[{self.slot}] {self.title} (order={self.display_order})"
