from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from accounts.models import CustomUser, UserAddress
from products.models import Product, Category, ProductVariant
import uuid

#  COUPON
#  User-applied discount codes at checkout.

class Coupon(models.Model):
    DISCOUNT_TYPE_CHOICES = (
        ("PERCENT", "Percentage"),
        ("FLAT",    "Flat Amount"),
    )

    code = models.CharField(max_length=20, unique=True)
    discount_type = models.CharField(max_length=10, choices=DISCOUNT_TYPE_CHOICES)
    #   PERCENT type → discount_value = 10  means 10%
    #   FLAT type    → discount_value = 100 means ₹100 off
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(1)],
                                help_text="Percentage (1–100) for PERCENT type, or flat amount for FLAT type.")
    max_discount = models.DecimalField(max_digits=10, decimal_places=2,null=True, blank=True,
        help_text="Maximum discount in ₹ for PERCENT coupons. Leave blank for no cap.",
    )
    min_order_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Minimum cart value required to apply this coupon.",
    )

    # Validity window
    # FIX: added start_date so coupons can be scheduled in advance
    start_date   = models.DateTimeField(default=timezone.now)
    expiry_date  = models.DateTimeField()

    # Usage tracking
    usage_limit  = models.PositiveIntegerField(
        default=1,
        help_text="0 = unlimited uses.",
    )
    used_count   = models.PositiveIntegerField(default=0)

    # FIX: removed offer_type / product FK / category FK from Coupon.
    # Those belong on the Offer model. Coupons are generic checkout codes.
    # FIX: used_by M2M remains to prevent a single user applying the same coupon twice.
    used_by = models.ManyToManyField(
        CustomUser,
        blank=True,
        related_name="used_coupons",
        help_text="Users who have already redeemed this coupon.",
    )

    is_active  = models.BooleanField(default=True)
    # FIX: added soft-delete flag + created_at timestamp
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

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


# ═════════════════════════════════════════════════════════════════════════════
#  OFFER
#  Automatic admin-set discounts on products or categories.
#  Applied at product display / cart calculation — NOT entered by user.
#  Per instructions: apply the LARGEST offer when both product & category
#  offers exist (logic handled in views/cart utils, not here).
# ═════════════════════════════════════════════════════════════════════════════
class Offer(models.Model):
    OFFER_TYPE_CHOICES = (
        ("PRODUCT",  "Product Offer"),
        ("CATEGORY", "Category Offer"),
        # FIX: REFERRAL type added per instructions
        ("REFERRAL", "Referral Offer"),
    )

    offer_type       = models.CharField(max_length=20, choices=OFFER_TYPE_CHOICES)
    # FIX: product / category are nullable because REFERRAL offers apply to neither
    product          = models.ForeignKey(
        Product, on_delete=models.CASCADE,
        null=True, blank=True, related_name="offers",
    )
    category         = models.ForeignKey(
        Category, on_delete=models.CASCADE,
        null=True, blank=True, related_name="offers",
    )
    discount_percent = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)],
    )
    # FIX: added validity window — offers must have start/end dates
    start_date       = models.DateTimeField(default=timezone.now)
    end_date         = models.DateTimeField(null=True, blank=True)

    # For REFERRAL offers: the coupon code awarded to the referrer
    referral_coupon  = models.ForeignKey(
        Coupon, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="referral_offers",
        help_text="Coupon awarded to referrer when referral offer triggers.",
    )

    is_active  = models.BooleanField(default=True)
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


# ═════════════════════════════════════════════════════════════════════════════
#  REFERRAL
#  Each user gets one ReferralCode on account creation.
#  ReferralUse records each successful referral.
# ═════════════════════════════════════════════════════════════════════════════
class ReferralCode(models.Model):
    """One per user; generated at signup and never changes."""
    user = models.OneToOneField(
        CustomUser, on_delete=models.CASCADE, related_name="referral_code",
    )
    code       = models.CharField(max_length=20, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.code:
            # Generate a short, readable referral code
            while True:
                code = f"KID{uuid.uuid4().hex[:7].upper()}"
                if not ReferralCode.objects.filter(code=code).exists():
                    self.code = code
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.email} → {self.code}"

class ReferralUse(models.Model):
    referral_code = models.ForeignKey(ReferralCode, on_delete=models.CASCADE, related_name="uses",)
    referred_user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name="referred_by")
    coupon_awarded = models.ForeignKey(Coupon, on_delete=models.SET_NULL,null=True, blank=True, related_name="referral_uses",
                                help_text="Coupon given to the referrer after this user registered.")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.referral_code.user.email} referred {self.referred_user.email}"

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
    )
    PAYMENT_METHOD_CHOICES = (
        ("COD", "Cash on Delivery"),
        ("RAZORPAY", "Razorpay"),
        ("STRIPE", "Stripe"),
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
    total_amount = models.DecimalField(max_digits=10, decimal_places=2,
                                            help_text="Sum of all item totals before discounts.")
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                            help_text="Offer/product discounts applied.")
    shipping_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    final_amount = models.DecimalField(max_digits=10, decimal_places=2,
                                            help_text="total_amount - discount_amount - coupon_discount + shipping_charge")
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
        ("CANCELLED", "Cancelled"),
        ("RETURN_REQUESTED", "Return Requested"),
        ("RETURN_APPROVED", "Return Approved"),
        ("RETURN_REJECTED", "Return Rejected"),
        ("REFUNDED", "Refunded"),
    )

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="order_items")
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, related_name="order_items")
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Price at time of purchase (snapshot).")
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Offer discount applied to this item.")
    total_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="(unit_price × quantity) - discount_amount")
    item_status = models.CharField(max_length=20, choices=ITEM_STATUS_CHOICES, default="ACTIVE")
    cancel_reason = models.TextField(blank=True, null=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        self.total_price = (self.unit_price * self.quantity) - self.discount_amount
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order.order_id} – {self.variant}"

#  RETURN
#  Per-item return requests. One Return per OrderItem.
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
    admin_remark = models.TextField(blank=True, null=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "product")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} → {self.product.product_name} ({self.rating}★)"

#  WALLET
class Wallet(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name="wallet")
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Wallet – {self.user.email} (₹{self.balance})"

class WalletTransaction(models.Model):
    TRANSACTION_TYPE_CHOICES = (
        ("CREDIT",  "Credit"),
        ("DEBIT",   "Debit"),
        ("REFUND",  "Refund"),
    )
    REFERENCE_TYPE_CHOICES = (
        ("ORDER", "Order"),
        ("RETURN", "Return"),
        ("REFERRAL", "Referral Reward"),
        ("COUPON", "Coupon Refund"),
        ("MANUAL", "Manual Adjustment"),
    )

    wallet         = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="transactions")
    txn_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True, 
                                        help_text="UUID transaction ID. Use in admin wallet management and ledger.")
    txn_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    balance_after = models.DecimalField(max_digits=10, decimal_places=2)
    reference_type = models.CharField(max_length=20, choices=REFERENCE_TYPE_CHOICES, null=True, blank=True)
    reference_id = models.CharField(max_length=50, null=True, blank=True,
                                        help_text="PK of related Order/Return/etc.")
    description = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.txn_id} | {self.txn_type} {self.amount}"

    @property
    def txn_id_display(self):
        """Short display version of the UUID txn_id (first 12 chars, no dashes)."""
        return str(self.txn_id).replace("-", "").upper()[:12]

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
        return f"{self.wishlist.user.email} ♡ {self.product.product_name}"