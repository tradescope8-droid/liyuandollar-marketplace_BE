import uuid
from decimal import Decimal
import secrets

from django.conf import settings
from django.db import models
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify


class Product(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        SOLD = "sold", "Sold"
        INACTIVE = "inactive", "Inactive"

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    category = models.CharField(max_length=120)
    subcategory = models.CharField(max_length=120, blank=True, default="")
    category_icon = models.ImageField(upload_to="product-categories/", blank=True, null=True)
    subcategory_icon = models.ImageField(upload_to="product-subcategories/", blank=True, null=True)
    description = models.TextField()
    image = models.ImageField(upload_to="products/", blank=True, null=True)
    price_usd = models.DecimalField(max_digits=12, decimal_places=2)
    rating = models.DecimalField(max_digits=3, decimal_places=1, default=Decimal("4.8"))
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.AVAILABLE,
    )
    stock_count = models.PositiveIntegerField(default=1)
    single_item = models.BooleanField(default=False)
    credentials_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    @property
    def is_available_for_purchase(self):
        if self.status != self.Status.AVAILABLE:
            return False
        if self.single_item:
            return self.stock_count > 0
        return self.stock_count > 0


class PaymentAsset(models.Model):
    class MethodType(models.TextChoices):
        CRYPTO = "crypto", "Crypto"

    method_type = models.CharField(
        max_length=20,
        choices=MethodType.choices,
        default=MethodType.CRYPTO,
    )
    name = models.CharField(max_length=120)
    symbol = models.CharField(max_length=20)
    network = models.CharField(max_length=60)
    wallet_address = models.CharField(max_length=255)
    qr_code_image = models.ImageField(
        upload_to="payment-assets/qr-codes/",
        blank=True,
        null=True,
    )
    instructions = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)
    usd_rate = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal("1.000000"))

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self):
        return f"{self.name} ({self.network})"


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        AWAITING_CONFIRMATION = "awaiting_confirmation", "Awaiting confirmation"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"
        FAILED = "failed", "Failed"

    reference = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    order_number = models.CharField(max_length=32, unique=True, editable=False, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="orders",
        null=True,
        blank=True,
    )
    is_guest = models.BooleanField(default=False)
    guest_name = models.CharField(max_length=120, blank=True, default="")
    guest_email = models.EmailField(blank=True, default="")
    guest_token = models.UUIDField(default=uuid.uuid4, editable=False)
    guest_access_token = models.CharField(max_length=128, unique=True, blank=True, null=True)
    guest_token_created_at = models.DateTimeField(blank=True, null=True)
    guest_token_expires_at = models.DateTimeField(blank=True, null=True)
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="orders",
    )
    amount_expected = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    selected_payment_asset = models.ForeignKey(
        PaymentAsset,
        on_delete=models.SET_NULL,
        related_name="orders",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.order_number or f'Order #{self.pk}'} - {self.product.title}"

    @property
    def is_paid(self):
        return self.status == self.Status.PAID

    @staticmethod
    def generate_order_number():
        date_part = timezone.now().strftime("%Y%m%d")
        random_part = secrets.token_hex(3).upper()
        return f"LD-{date_part}-{random_part}"

    @staticmethod
    def generate_guest_access_token():
        return secrets.token_urlsafe(32)

    def ensure_order_number(self):
        if self.order_number:
            return
        for _ in range(10):
            candidate = self.generate_order_number()
            if not Order.objects.filter(order_number=candidate).exists():
                self.order_number = candidate
                return
        self.order_number = f"LD-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:12].upper()}"

    def ensure_guest_access_token(self):
        if not self.is_guest:
            self.guest_access_token = None
            self.guest_token_created_at = None
            self.guest_token_expires_at = None
            return
        if self.guest_access_token:
            return
        for _ in range(10):
            candidate = self.generate_guest_access_token()
            if not Order.objects.filter(guest_access_token=candidate).exists():
                self.guest_access_token = candidate
                self.guest_token_created_at = timezone.now()
                return
        self.guest_access_token = self.generate_guest_access_token()
        self.guest_token_created_at = timezone.now()

    def guest_token_is_valid(self):
        if not self.guest_access_token or not self.is_guest:
            return False
        if self.guest_token_expires_at and self.guest_token_expires_at <= timezone.now():
            return False
        return True

    def save(self, *args, **kwargs):
        previous_status = None
        if self.pk:
            previous_status = (
                Order.objects.filter(pk=self.pk).values_list("status", flat=True).first()
            )

        self.is_guest = self.user_id is None
        self.ensure_order_number()
        self.ensure_guest_access_token()

        with transaction.atomic():
            super().save(*args, **kwargs)
            if self.user and previous_status and previous_status != self.status:
                Notification.objects.create(
                    user=self.user,
                    order=self,
                    level=Notification.Level.INFO,
                    title="Order status updated",
                    message=f"Order {self.order_number} status changed to {self.get_status_display()}.",
                )
            if self.status == self.Status.PAID and previous_status != self.Status.PAID:
                product = Product.objects.select_for_update().get(pk=self.product_id)
                if product.stock_count < self.quantity:
                    raise ValueError("This product can no longer be confirmed as paid because it is out of stock.")
                product.stock_count -= self.quantity
                if product.stock_count == 0:
                    product.status = Product.Status.SOLD if product.single_item else product.status
                product.save(update_fields=["stock_count", "status", "updated_at"])
                PurchasedCredentialAccess.objects.get_or_create(order=self)
                if self.user:
                    Notification.objects.create(
                        user=self.user,
                        order=self,
                        level=Notification.Level.SUCCESS,
                        title="Payment confirmed",
                        message=f"Your order {self.order_number} is marked as paid. Credentials are now available.",
                    )


class PaymentSubmission(models.Model):
    class ReviewStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="payment_submissions",
    )
    tx_hash = models.CharField(max_length=255, blank=True)
    sender_wallet_address = models.CharField(max_length=255, blank=True)
    note = models.TextField(blank=True)
    screenshot = models.ImageField(
        upload_to="payment-submissions/",
        blank=True,
        null=True,
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_by_admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_payment_submissions",
    )
    review_status = models.CharField(
        max_length=20,
        choices=ReviewStatus.choices,
        default=ReviewStatus.PENDING,
    )

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"Payment submission for order #{self.order_id}"


class PurchasedCredentialAccess(models.Model):
    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name="credential_access",
    )
    unlocked_at = models.DateTimeField(auto_now_add=True)
    pdf_generated_file = models.FileField(
        upload_to="credential-pdfs/",
        blank=True,
        null=True,
    )

    def __str__(self):
        return f"Credential access for order #{self.order_id}"


class Notification(models.Model):
    class Level(models.TextChoices):
        INFO = "info", "Info"
        SUCCESS = "success", "Success"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    title = models.CharField(max_length=160)
    message = models.TextField()
    level = models.CharField(max_length=20, choices=Level.choices, default=Level.INFO)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user_id} - {self.title}"


class Wallet(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wallet",
    )
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Wallet ({self.user_id})"


class WalletCryptoAsset(models.Model):
    name = models.CharField(max_length=120)
    symbol = models.CharField(max_length=20)
    network = models.CharField(max_length=60)
    wallet_address = models.CharField(max_length=255)
    qr_code = models.ImageField(upload_to="wallet-assets/qr-codes/", blank=True, null=True)
    instructions = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.network})"


class DepositRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        REJECTED = "rejected", "Rejected"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="deposit_requests",
    )
    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name="deposits",
    )
    crypto_asset = models.ForeignKey(
        WalletCryptoAsset,
        on_delete=models.PROTECT,
        related_name="deposits",
    )
    payment_asset = models.ForeignKey(
        PaymentAsset,
        on_delete=models.PROTECT,
        related_name="deposit_requests",
        null=True,
        blank=True,
    )
    amount = models.DecimalField(max_digits=18, decimal_places=8)
    asset_amount = models.DecimalField(max_digits=18, decimal_places=8, blank=True, null=True)
    credited_amount_usd = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    tx_hash = models.CharField(max_length=255, blank=True)
    note = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    admin_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    confirmed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Deposit {self.id} ({self.user_id})"

    def confirm(self, admin_note=""):
        if self.status != self.Status.PENDING:
            raise ValueError("Only pending deposits can be confirmed.")
        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(pk=self.wallet_id)
            balance_before = wallet.balance
            credited_amount = self.credited_amount_usd or self.amount
            wallet.balance = balance_before + credited_amount
            wallet.save(update_fields=["balance", "updated_at"])
            WalletTransactionLog.objects.create(
                user=self.user,
                wallet=wallet,
                transaction_type=WalletTransactionLog.TransactionType.DEPOSIT,
                reference_type=WalletTransactionLog.ReferenceType.DEPOSIT_REQUEST,
                reference_id=self.id,
                amount=credited_amount,
                balance_before=balance_before,
                balance_after=wallet.balance,
                status=self.Status.CONFIRMED,
                description="Deposit confirmed and converted to wallet USD balance.",
            )
            self.status = self.Status.CONFIRMED
            self.admin_note = admin_note
            self.confirmed_at = timezone.now()
            self.save(update_fields=["status", "admin_note", "confirmed_at", "updated_at"])

    def reject(self, admin_note=""):
        if self.status != self.Status.PENDING:
            raise ValueError("Only pending deposits can be rejected.")
        self.status = self.Status.REJECTED
        self.admin_note = admin_note
        self.save(update_fields=["status", "admin_note", "updated_at"])


class WithdrawalRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        COMPLETED = "completed", "Completed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="withdrawal_requests",
    )
    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name="withdrawals",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    destination_address = models.CharField(max_length=255)
    destination_qr_code = models.ImageField(upload_to="wallet-withdrawals/qr-codes/", blank=True, null=True)
    network = models.CharField(max_length=60)
    note = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    admin_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Withdrawal {self.id} ({self.user_id})"

    def approve(self, admin_note=""):
        if self.status != self.Status.PENDING:
            raise ValueError("Only pending withdrawals can be approved.")
        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(pk=self.wallet_id)
            if wallet.balance < self.amount:
                raise ValueError("Insufficient wallet balance.")
            balance_before = wallet.balance
            wallet.balance = balance_before - self.amount
            wallet.save(update_fields=["balance", "updated_at"])
            WalletTransactionLog.objects.create(
                user=self.user,
                wallet=wallet,
                transaction_type=WalletTransactionLog.TransactionType.WITHDRAWAL,
                reference_type=WalletTransactionLog.ReferenceType.WITHDRAWAL_REQUEST,
                reference_id=self.id,
                amount=self.amount,
                balance_before=balance_before,
                balance_after=wallet.balance,
                status=self.Status.APPROVED,
                description="Withdrawal approved by admin.",
            )
            self.status = self.Status.APPROVED
            self.admin_note = admin_note
            self.processed_at = timezone.now()
            self.save(update_fields=["status", "admin_note", "processed_at", "updated_at"])

    def complete(self, admin_note=""):
        if self.status not in [self.Status.APPROVED, self.Status.PENDING]:
            raise ValueError("Only pending or approved withdrawals can be completed.")
        if self.status == self.Status.PENDING:
            self.approve(admin_note=admin_note)
            return
        self.status = self.Status.COMPLETED
        self.admin_note = admin_note or self.admin_note
        self.save(update_fields=["status", "admin_note", "updated_at"])

    def reject(self, admin_note=""):
        if self.status != self.Status.PENDING:
            raise ValueError("Only pending withdrawals can be rejected.")
        self.status = self.Status.REJECTED
        self.admin_note = admin_note
        self.save(update_fields=["status", "admin_note", "updated_at"])


class WalletTransactionLog(models.Model):
    class TransactionType(models.TextChoices):
        DEPOSIT = "deposit", "Deposit"
        WITHDRAWAL = "withdrawal", "Withdrawal"
        PURCHASE = "purchase", "Purchase"

    class ReferenceType(models.TextChoices):
        DEPOSIT_REQUEST = "deposit_request", "Deposit request"
        WITHDRAWAL_REQUEST = "withdrawal_request", "Withdrawal request"
        ORDER = "order", "Order"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wallet_transactions",
    )
    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    reference_type = models.CharField(max_length=30, choices=ReferenceType.choices)
    reference_id = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    balance_before = models.DecimalField(max_digits=14, decimal_places=2)
    balance_after = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=30)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user_id} {self.transaction_type} {self.amount}"


class SupportContactSettings(models.Model):
    telegram_channel = models.CharField(max_length=120, default="@liliyuan111")
    whatsapp_number = models.CharField(max_length=32, default="+66 91 817 1423")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Support contact settings"

    def __str__(self):
        return "Support contact settings"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={
                "telegram_channel": "@liliyuan111",
                "whatsapp_number": "+66 91 817 1423",
            },
        )
        return obj


class SupportTicket(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PENDING = "pending", "Pending"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="support_tickets",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    subject = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Support ticket #{self.pk}"


class SupportMessage(models.Model):
    class SenderRole(models.TextChoices):
        USER = "user", "User"
        GUEST = "guest", "Guest"
        ADMIN = "admin", "Admin"

    ticket = models.ForeignKey(
        SupportTicket,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_messages",
    )
    sender_role = models.CharField(max_length=20, choices=SenderRole.choices, default=SenderRole.GUEST)
    sender_name = models.CharField(max_length=120, blank=True)
    sender_email = models.EmailField(blank=True)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Support message #{self.pk}"
