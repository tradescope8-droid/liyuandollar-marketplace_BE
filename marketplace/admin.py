from django.contrib import admin
from django.utils.html import format_html

from .models import (
    DepositRequest,
    Notification,
    Order,
    PaymentAsset,
    PaymentSubmission,
    Product,
    PurchasedCredentialAccess,
    SupportMessage,
    SupportTicket,
    Wallet,
    WalletCryptoAsset,
    WalletTransactionLog,
    WithdrawalRequest,
)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "subcategory", "price_usd", "status", "stock_count", "single_item", "image_preview")
    list_filter = ("status", "category", "subcategory", "single_item")
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ("title", "category", "subcategory")
    search_help_text = (
        "Add admin-managed categories such as Facebook Accounts, Instagram Accounts, "
        "Emails, Gift Cards - UK, Gift Cards - Australia, Gift Cards - Hongkong, and Gift Cards - US."
    )
    fieldsets = (
        (
            "Catalog",
            {
                "fields": (
                    "title",
                    "slug",
                    "category",
                    "subcategory",
                    "category_icon",
                "subcategory_icon",
                "description",
                "image",
            ),
            "description": (
                "Category is free-form so admins can add new inventory groups and regional gift-card variants "
                "without a code change."
            ),
        },
    ),
    (
        "Availability",
        {
            "fields": ("price_usd", "rating", "status", "stock_count", "single_item"),
        },
    ),
        (
            "Protected Fulfillment",
            {
                "fields": ("credentials_data",),
                "description": "Credentials stay hidden from public APIs and are only revealed for paid orders.",
            },
        ),
    )

    @admin.display(description="Image", ordering="image")
    def image_preview(self, obj):
        if not obj.image:
            return "—"
        return format_html(
            '<img src="{}" style="height:42px;width:42px;object-fit:cover;border-radius:10px;border:1px solid #e5e7eb;" />',
            obj.image.url,
        )


@admin.register(PaymentAsset)
class PaymentAssetAdmin(admin.ModelAdmin):
    list_display = ("name", "symbol", "network", "wallet_address", "qr_preview", "is_active", "display_order")
    list_filter = ("is_active", "method_type", "network")
    ordering = ("display_order",)
    search_fields = ("name", "symbol", "network", "wallet_address")
    fieldsets = (
        (
            "Asset details",
            {
                "fields": ("method_type", "name", "symbol", "network"),
            },
        ),
        (
            "Settlement instructions",
            {
                "fields": ("wallet_address", "qr_code_image", "instructions"),
            },
        ),
        (
            "Visibility",
            {
                "fields": ("is_active", "display_order"),
            },
        ),
    )

    @admin.display(description="QR", ordering="qr_code_image")
    def qr_preview(self, obj):
        if not obj.qr_code_image:
            return "—"
        return format_html(
            '<img src="{}" style="height:42px;width:42px;object-fit:cover;border-radius:10px;border:1px solid #e5e7eb;" />',
            obj.qr_code_image.url,
        )


class PaymentSubmissionInline(admin.TabularInline):
    model = PaymentSubmission
    extra = 0
    readonly_fields = ("submitted_at",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "reference", "user", "product", "status", "amount_expected", "selected_payment_asset")
    list_filter = ("status", "selected_payment_asset__network")
    search_fields = ("reference", "user__username", "product__title")
    inlines = [PaymentSubmissionInline]


@admin.register(PaymentSubmission)
class PaymentSubmissionAdmin(admin.ModelAdmin):
    list_display = ("order", "tx_hash", "review_status", "submitted_at", "reviewed_by_admin")
    list_filter = ("review_status",)
    search_fields = ("order__reference", "tx_hash", "sender_wallet_address")


@admin.register(PurchasedCredentialAccess)
class PurchasedCredentialAccessAdmin(admin.ModelAdmin):
    list_display = ("order", "unlocked_at")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "title", "level", "is_read", "created_at", "order")
    list_filter = ("level", "is_read")
    search_fields = ("title", "message", "user__email", "order__reference")


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("user", "balance", "updated_at")
    search_fields = ("user__email", "user__username")


@admin.register(WalletCryptoAsset)
class WalletCryptoAssetAdmin(admin.ModelAdmin):
    list_display = ("name", "symbol", "network", "wallet_address", "is_active")
    list_filter = ("is_active", "network")
    search_fields = ("name", "symbol", "network", "wallet_address")


@admin.register(DepositRequest)
class DepositRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "amount", "status", "crypto_asset", "created_at", "confirmed_at")
    list_filter = ("status", "crypto_asset__network")
    search_fields = ("user__email", "tx_hash")


@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "amount", "status", "network", "created_at", "processed_at")
    list_filter = ("status", "network")
    search_fields = ("user__email", "destination_address")


@admin.register(WalletTransactionLog)
class WalletTransactionLogAdmin(admin.ModelAdmin):
    list_display = ("user", "transaction_type", "amount", "status", "created_at")
    list_filter = ("transaction_type", "status")
    search_fields = ("user__email", "reference_id")


class SupportMessageInline(admin.TabularInline):
    model = SupportMessage
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ("id", "subject", "status", "user", "email", "created_at")
    list_filter = ("status",)
    search_fields = ("subject", "user__email", "email")
    inlines = [SupportMessageInline]


@admin.register(SupportMessage)
class SupportMessageAdmin(admin.ModelAdmin):
    list_display = ("ticket", "sender_role", "sender_email", "created_at")
    list_filter = ("sender_role",)
    search_fields = ("message", "sender_email", "ticket__subject")
