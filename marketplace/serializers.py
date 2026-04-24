from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.db import transaction
from rest_framework import serializers

from .models import (
    DepositRequest,
    Notification,
    Order,
    PaymentAsset,
    PaymentSubmission,
    Product,
    PurchasedCredentialAccess,
    SupportMessage,
    SupportContactSettings,
    SupportTicket,
    Wallet,
    WalletCryptoAsset,
    WalletTransactionLog,
    WithdrawalRequest,
)

User = get_user_model()


def build_guest_access_url(request, order):
    if not order.is_guest or not order.guest_access_token:
        return None
    relative_path = f"/guest/orders/{order.guest_access_token}"
    frontend_base_url = ""
    if request:
        frontend_base_url = request.headers.get("origin", "")
    frontend_base_url = frontend_base_url or getattr(settings, "FRONTEND_BASE_URL", "")
    if frontend_base_url:
        return f"{frontend_base_url.rstrip('/')}{relative_path}"
    return relative_path


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_staff",
            "is_active",
            "last_login",
        )


class AdminUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_staff",
            "is_active",
            "date_joined",
            "last_login",
        )


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "is_staff", "is_active")

    def validate_email(self, value):
        if not value:
            return value
        existing = User.objects.filter(email__iexact=value).exclude(pk=self.instance.pk if self.instance else None)
        if existing.exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("username", "email", "password", "first_name", "last_name")

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        user.is_active = False
        user.save(update_fields=["is_active"])
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        request = self.context.get("request")
        identifier = attrs["email"].strip()
        user = authenticate(request=request, username=identifier, password=attrs["password"])
        if not user and "@" in identifier:
            try:
                user_obj = User.objects.get(email__iexact=identifier)
            except User.DoesNotExist as exc:
                raise serializers.ValidationError("Invalid credentials.") from exc
            user = authenticate(request=request, username=user_obj.username, password=attrs["password"])
        if not user and "@" not in identifier:
            try:
                user_obj = User.objects.get(username__iexact=identifier)
            except User.DoesNotExist as exc:
                raise serializers.ValidationError("Invalid credentials.") from exc
            user = authenticate(request=request, username=user_obj.username, password=attrs["password"])
        if not user:
            raise serializers.ValidationError("Invalid credentials.")
        if not user.is_active:
            raise serializers.ValidationError("Account pending admin approval.")
        attrs["user"] = user
        return attrs


class ProductListSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()
    category_icon = serializers.SerializerMethodField()
    subcategory_icon = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "title",
            "slug",
            "category",
            "subcategory",
            "category_icon",
            "subcategory_icon",
            "description",
            "image",
            "price_usd",
            "rating",
            "status",
            "stock_count",
            "single_item",
            "created_at",
            "updated_at",
        )

    def get_image(self, obj):
        request = self.context.get("request")
        if not obj.image:
            return None
        if request:
            return request.build_absolute_uri(obj.image.url)
        return obj.image.url

    def get_category_icon(self, obj):
        request = self.context.get("request")
        if not obj.category_icon:
            return None
        if request:
            return request.build_absolute_uri(obj.category_icon.url)
        return obj.category_icon.url

    def get_subcategory_icon(self, obj):
        request = self.context.get("request")
        if not obj.subcategory_icon:
            return None
        if request:
            return request.build_absolute_uri(obj.subcategory_icon.url)
        return obj.subcategory_icon.url


class ProductDetailSerializer(ProductListSerializer):
    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields


class AdminProductSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(required=False, allow_null=True)
    category_icon = serializers.ImageField(required=False, allow_null=True)
    subcategory_icon = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "title",
            "slug",
            "category",
            "subcategory",
            "category_icon",
            "subcategory_icon",
            "description",
            "image",
            "price_usd",
            "rating",
            "status",
            "stock_count",
            "single_item",
            "credentials_data",
            "created_at",
            "updated_at",
        )

    def validate_rating(self, value):
        if value < 0 or value > 5:
            raise serializers.ValidationError("Rating must be between 0 and 5.")
        return value

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if data.get("image"):
            if request:
                data["image"] = request.build_absolute_uri(instance.image.url)
            else:
                data["image"] = instance.image.url
        if data.get("category_icon"):
            if request:
                data["category_icon"] = request.build_absolute_uri(instance.category_icon.url)
            else:
                data["category_icon"] = instance.category_icon.url
        if data.get("subcategory_icon"):
            if request:
                data["subcategory_icon"] = request.build_absolute_uri(instance.subcategory_icon.url)
            else:
                data["subcategory_icon"] = instance.subcategory_icon.url
        return data


class PaymentAssetSerializer(serializers.ModelSerializer):
    qr_code_image = serializers.SerializerMethodField()

    class Meta:
        model = PaymentAsset
        fields = (
            "id",
            "method_type",
            "name",
            "symbol",
            "network",
            "wallet_address",
            "qr_code_image",
            "instructions",
            "display_order",
            "usd_rate",
        )

    def get_qr_code_image(self, obj):
        request = self.context.get("request")
        if not obj.qr_code_image:
            return None
        if request:
            return request.build_absolute_uri(obj.qr_code_image.url)
        return obj.qr_code_image.url


class AdminPaymentAssetSerializer(PaymentAssetSerializer):
    qr_code_image = serializers.ImageField(required=False, allow_null=True)

    class Meta(PaymentAssetSerializer.Meta):
        fields = (
            "id",
            "method_type",
            "name",
            "symbol",
            "network",
            "wallet_address",
            "qr_code_image",
            "instructions",
            "is_active",
            "display_order",
            "usd_rate",
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if instance.qr_code_image:
            data["qr_code_image"] = (
                request.build_absolute_uri(instance.qr_code_image.url)
                if request
                else instance.qr_code_image.url
            )
        else:
            data["qr_code_image"] = None
        return data


class PaymentSubmissionSerializer(serializers.ModelSerializer):
    screenshot = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = PaymentSubmission
        fields = (
            "id",
            "tx_hash",
            "sender_wallet_address",
            "note",
            "screenshot",
            "submitted_at",
            "review_status",
        )
        read_only_fields = ("submitted_at", "review_status")

    def get_screenshot(self, obj):
        request = self.context.get("request")
        if not obj.screenshot:
            return None
        if request:
            return request.build_absolute_uri(obj.screenshot.url)
        return obj.screenshot.url


class OrderSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)
    selected_payment_asset = PaymentAssetSerializer(read_only=True)
    payment_submissions = PaymentSubmissionSerializer(read_only=True, many=True)
    order_number = serializers.CharField(read_only=True)
    credentials_available = serializers.SerializerMethodField()
    pdf_available = serializers.SerializerMethodField()
    payment_details = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id",
            "order_number",
            "reference",
            "user",
            "is_guest",
            "guest_name",
            "guest_email",
            "product",
            "amount_expected",
            "quantity",
            "selected_payment_asset",
            "status",
            "payment_details",
            "credentials_available",
            "pdf_available",
            "payment_submissions",
            "created_at",
            "updated_at",
        )

    def get_credentials_available(self, obj):
        return bool(obj.is_paid)

    def get_pdf_available(self, obj):
        return bool(obj.is_paid)

    def get_payment_details(self, obj):
        if not obj.selected_payment_asset:
            return None
        asset_data = PaymentAssetSerializer(
            obj.selected_payment_asset,
            context=self.context,
        ).data
        return {
            "reference": str(obj.order_number),
            "status": obj.status,
            "asset": asset_data,
        }


class AdminOrderSerializer(OrderSerializer):
    user = UserSerializer(read_only=True)


class AdminOrderStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order.Status.choices)


class OrderCreateSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(default=1, min_value=1)
    guest_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    guest_email = serializers.EmailField(required=False, allow_blank=True)
    payment_asset_id = serializers.IntegerField(required=False)

    def validate(self, attrs):
        quantity = attrs.get("quantity", 1)
        if quantity < 1:
            raise serializers.ValidationError("Quantity must be at least 1.")
        try:
            product = Product.objects.get(pk=attrs["product_id"])
        except Product.DoesNotExist as exc:
            raise serializers.ValidationError("Product not found.") from exc
        if not product.is_available_for_purchase:
            raise serializers.ValidationError("Product is no longer available.")
        if product.single_item and quantity > 1:
            raise serializers.ValidationError("This product can only be purchased once.")
        if quantity > product.stock_count:
            raise serializers.ValidationError("Requested quantity exceeds available stock.")
        request = self.context["request"]
        if not getattr(request.user, "is_authenticated", False):
            if not attrs.get("guest_email"):
                raise serializers.ValidationError("Guest email is required for guest checkout.")
        return attrs

    def validate_payment_asset_id(self, value):
        try:
            PaymentAsset.objects.get(pk=value, is_active=True)
        except PaymentAsset.DoesNotExist as exc:
            raise serializers.ValidationError("Selected payment asset is unavailable.") from exc
        return value

    def create(self, validated_data):
        request = self.context["request"]
        product = Product.objects.get(pk=validated_data["product_id"])
        quantity = validated_data.get("quantity", 1)
        payment_asset = None
        if validated_data.get("payment_asset_id"):
            payment_asset = PaymentAsset.objects.get(
                pk=validated_data["payment_asset_id"],
                is_active=True,
            )
        if request.user and request.user.is_authenticated:
            return Order.objects.create(
                user=request.user,
                product=product,
                amount_expected=product.price_usd * quantity,
                quantity=quantity,
                selected_payment_asset=payment_asset,
            )
        return Order.objects.create(
            user=None,
            is_guest=True,
            guest_name=validated_data.get("guest_name", ""),
            guest_email=validated_data["guest_email"],
            product=product,
            amount_expected=product.price_usd * quantity,
            quantity=quantity,
            selected_payment_asset=payment_asset,
        )


class GuestOrderSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)
    selected_payment_asset = PaymentAssetSerializer(read_only=True)
    payment_submissions = PaymentSubmissionSerializer(read_only=True, many=True)
    guest_access_token = serializers.CharField(read_only=True)
    order_number = serializers.CharField(read_only=True)
    credentials_available = serializers.SerializerMethodField()
    pdf_available = serializers.SerializerMethodField()
    guest_access_url = serializers.SerializerMethodField()
    payment_details = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id",
            "order_number",
            "reference",
            "is_guest",
            "guest_name",
            "guest_email",
            "guest_access_token",
            "product",
            "amount_expected",
            "quantity",
            "selected_payment_asset",
            "status",
            "payment_details",
            "credentials_available",
            "pdf_available",
            "guest_access_url",
            "payment_submissions",
            "created_at",
            "updated_at",
        )

    def get_credentials_available(self, obj):
        return bool(obj.is_paid)

    def get_pdf_available(self, obj):
        return bool(obj.is_paid)

    def get_guest_access_url(self, obj):
        return build_guest_access_url(self.context.get("request"), obj)

    def get_payment_details(self, obj):
        if not obj.selected_payment_asset:
            return None
        asset_data = PaymentAssetSerializer(
            obj.selected_payment_asset,
            context=self.context,
        ).data
        return {
            "reference": str(obj.order_number),
            "status": obj.status,
            "asset": asset_data,
        }


class GuestOrderCreateSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    guest_name = serializers.CharField(max_length=120)
    guest_email = serializers.EmailField()
    quantity = serializers.IntegerField(default=1, min_value=1)
    payment_asset_id = serializers.IntegerField(required=False)

    def validate(self, attrs):
        quantity = attrs.get("quantity", 1)
        if quantity < 1:
            raise serializers.ValidationError("Quantity must be at least 1.")
        try:
            product = Product.objects.get(pk=attrs["product_id"])
        except Product.DoesNotExist as exc:
            raise serializers.ValidationError("Product not found.") from exc
        if not product.is_available_for_purchase:
            raise serializers.ValidationError("Product is no longer available.")
        if product.single_item and quantity > 1:
            raise serializers.ValidationError("This product can only be purchased once.")
        if quantity > product.stock_count:
            raise serializers.ValidationError("Requested quantity exceeds available stock.")
        return attrs

    def validate_payment_asset_id(self, value):
        try:
            PaymentAsset.objects.get(pk=value, is_active=True)
        except PaymentAsset.DoesNotExist as exc:
            raise serializers.ValidationError("Selected payment asset is unavailable.") from exc
        return value

    def create(self, validated_data):
        product = Product.objects.get(pk=validated_data["product_id"])
        payment_asset = None
        if validated_data.get("payment_asset_id"):
            payment_asset = PaymentAsset.objects.get(
                pk=validated_data["payment_asset_id"],
                is_active=True,
            )
        quantity = validated_data.get("quantity", 1)
        order = Order.objects.create(
            user=None,
            is_guest=True,
            guest_name=validated_data["guest_name"],
            guest_email=validated_data["guest_email"],
            product=product,
            amount_expected=product.price_usd * quantity,
            quantity=quantity,
            selected_payment_asset=payment_asset,
            status=Order.Status.PENDING,
        )
        return order


class SelectPaymentAssetSerializer(serializers.Serializer):
    payment_asset_id = serializers.IntegerField()

    def validate_payment_asset_id(self, value):
        try:
            asset = PaymentAsset.objects.get(pk=value, is_active=True)
        except PaymentAsset.DoesNotExist as exc:
            raise serializers.ValidationError("Selected payment asset is unavailable.") from exc
        return value


class CredentialsSerializer(serializers.Serializer):
    credentials = serializers.JSONField()
    unlocked_at = serializers.DateTimeField()


class PurchasedCredentialAccessSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchasedCredentialAccess
        fields = ("unlocked_at", "pdf_generated_file")


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ("id", "title", "message", "level", "is_read", "created_at", "order")


class WalletSerializer(serializers.ModelSerializer):
    total_deposits = serializers.DecimalField(max_digits=14, decimal_places=2)
    total_withdrawals = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency_label = serializers.CharField()

    class Meta:
        model = Wallet
        fields = ("id", "balance", "currency_label", "total_deposits", "total_withdrawals")


class WalletCryptoAssetSerializer(serializers.ModelSerializer):
    qr_code = serializers.SerializerMethodField()

    class Meta:
        model = WalletCryptoAsset
        fields = (
            "id",
            "name",
            "symbol",
            "network",
            "wallet_address",
            "qr_code",
            "instructions",
        )

    def get_qr_code(self, obj):
        request = self.context.get("request")
        if not obj.qr_code:
            return None
        if request:
            return request.build_absolute_uri(obj.qr_code.url)
        return obj.qr_code.url


class AdminWalletCryptoAssetSerializer(WalletCryptoAssetSerializer):
    class Meta(WalletCryptoAssetSerializer.Meta):
        fields = WalletCryptoAssetSerializer.Meta.fields + ("is_active", "created_at", "updated_at")


class DepositRequestSerializer(serializers.ModelSerializer):
    crypto_asset = WalletCryptoAssetSerializer(read_only=True)
    payment_asset = PaymentAssetSerializer(read_only=True)

    class Meta:
        model = DepositRequest
        fields = (
            "id",
            "amount",
            "asset_amount",
            "credited_amount_usd",
            "status",
            "tx_hash",
            "note",
            "crypto_asset",
            "payment_asset",
            "created_at",
            "admin_note",
        )


class DepositRequestCreateSerializer(serializers.Serializer):
    payment_asset_id = serializers.IntegerField(required=False)
    crypto_asset_id = serializers.IntegerField(required=False)
    amount = serializers.DecimalField(max_digits=18, decimal_places=8)
    tx_hash = serializers.CharField(required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        payment_asset_id = attrs.get("payment_asset_id") or attrs.get("crypto_asset_id")
        if not payment_asset_id:
            raise serializers.ValidationError("A payment asset is required.")
        try:
            payment_asset = PaymentAsset.objects.get(pk=payment_asset_id, is_active=True)
        except PaymentAsset.DoesNotExist as exc:
            raise serializers.ValidationError("Selected asset is not active.") from exc
        if payment_asset.usd_rate <= 0:
            raise serializers.ValidationError("Selected asset is missing a valid USD conversion rate.")
        attrs["payment_asset"] = payment_asset
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        payment_asset = validated_data["payment_asset"]
        with transaction.atomic():
            legacy_asset = (
                WalletCryptoAsset.objects.filter(
                    symbol=payment_asset.symbol,
                    network=payment_asset.network,
                    wallet_address=payment_asset.wallet_address,
                ).first()
            )
            if not legacy_asset:
                legacy_asset = WalletCryptoAsset.objects.create(
                    name=payment_asset.name,
                    symbol=payment_asset.symbol,
                    network=payment_asset.network,
                    wallet_address=payment_asset.wallet_address,
                    instructions=payment_asset.instructions,
                    is_active=payment_asset.is_active,
                )
            asset_amount = validated_data["amount"]
            credited_amount_usd = asset_amount * payment_asset.usd_rate
            return DepositRequest.objects.create(
                user=request.user,
                wallet=wallet,
                crypto_asset=legacy_asset,
                payment_asset=payment_asset,
                amount=asset_amount,
                asset_amount=asset_amount,
                credited_amount_usd=credited_amount_usd,
                tx_hash=validated_data.get("tx_hash", ""),
                note=validated_data.get("note", ""),
            )


class WithdrawalRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = WithdrawalRequest
        fields = (
            "id",
            "amount",
            "destination_address",
            "destination_qr_code",
            "network",
            "status",
            "note",
            "created_at",
            "admin_note",
        )


class WithdrawalRequestCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    destination_address = serializers.CharField()
    destination_qr_code = serializers.ImageField(required=False, allow_null=True)
    network = serializers.CharField()
    note = serializers.CharField(required=False, allow_blank=True)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0.")
        return value

    def validate(self, attrs):
        request = self.context["request"]
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        if attrs["amount"] > wallet.balance:
            raise serializers.ValidationError("Insufficient wallet balance.")
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        return WithdrawalRequest.objects.create(
            user=request.user,
            wallet=wallet,
            amount=validated_data["amount"],
            destination_address=validated_data["destination_address"],
            destination_qr_code=validated_data.get("destination_qr_code"),
            network=validated_data["network"],
            note=validated_data.get("note", ""),
        )


class WalletTransactionLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletTransactionLog
        fields = (
            "id",
            "transaction_type",
            "reference_type",
            "reference_id",
            "amount",
            "balance_before",
            "balance_after",
            "status",
            "description",
            "created_at",
        )


class AdminNoteSerializer(serializers.Serializer):
    admin_note = serializers.CharField(required=False, allow_blank=True)


class SupportMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportMessage
        fields = ("id", "sender_role", "sender_name", "sender_email", "message", "created_at")


class SupportContactSettingsSerializer(serializers.ModelSerializer):
    whatsapp_link = serializers.SerializerMethodField()
    telegram_link = serializers.SerializerMethodField()

    class Meta:
        model = SupportContactSettings
        fields = (
            "telegram_channel",
            "telegram_link",
            "whatsapp_number",
            "whatsapp_link",
            "updated_at",
        )

    def get_whatsapp_link(self, obj):
        digits = "".join(char for char in obj.whatsapp_number if char.isdigit())
        if not digits:
            return ""
        return f"https://wa.me/{digits}?text=Hello%20I%20need%20help"

    def get_telegram_link(self, obj):
        handle = obj.telegram_channel.strip()
        if not handle:
            return ""
        if handle.startswith("@"):
            handle = handle[1:]
        return f"https://t.me/{handle}"


class SupportTicketSerializer(serializers.ModelSerializer):
    last_message = serializers.SerializerMethodField()
    last_message_at = serializers.SerializerMethodField()

    class Meta:
        model = SupportTicket
        fields = ("id", "subject", "status", "created_at", "last_message", "last_message_at")

    def get_last_message(self, obj):
        message = obj.messages.order_by("-created_at").first()
        return message.message if message else None

    def get_last_message_at(self, obj):
        message = obj.messages.order_by("-created_at").first()
        return message.created_at if message else None


class SupportTicketDetailSerializer(SupportTicketSerializer):
    messages = SupportMessageSerializer(many=True, read_only=True)

    class Meta(SupportTicketSerializer.Meta):
        fields = SupportTicketSerializer.Meta.fields + ("messages",)


class SupportTicketCreateSerializer(serializers.Serializer):
    subject = serializers.CharField(max_length=255)
    message = serializers.CharField(required=False, allow_blank=True)
    name = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            return attrs
        if not attrs.get("name") or not attrs.get("email"):
            raise serializers.ValidationError("Name and email are required for guest support.")
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        is_authed = user and user.is_authenticated
        ticket = SupportTicket.objects.create(
            user=user if is_authed else None,
            name=validated_data.get("name", "") if not is_authed else (user.get_full_name() or user.username),
            email=validated_data.get("email", "") if not is_authed else user.email,
            subject=validated_data["subject"],
            status=SupportTicket.Status.OPEN,
        )
        initial_message = validated_data.get("message", "").strip()
        if initial_message:
            SupportMessage.objects.create(
                ticket=ticket,
                sender=user if is_authed else None,
                sender_role=SupportMessage.SenderRole.USER if is_authed else SupportMessage.SenderRole.GUEST,
                sender_name=ticket.name,
                sender_email=ticket.email,
                message=initial_message,
            )
        return ticket


class SupportMessageCreateSerializer(serializers.Serializer):
    ticket_id = serializers.IntegerField()
    message = serializers.CharField()
    name = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        try:
            ticket = SupportTicket.objects.get(pk=attrs["ticket_id"])
        except SupportTicket.DoesNotExist as exc:
            raise serializers.ValidationError("Ticket not found.") from exc

        if user and user.is_authenticated:
            if ticket.user_id != user.id:
                raise serializers.ValidationError("You do not have access to this ticket.")
        else:
            if ticket.user_id:
                raise serializers.ValidationError("You must be logged in to reply to this ticket.")
            if not attrs.get("name") or not attrs.get("email"):
                raise serializers.ValidationError("Name and email are required for guest replies.")
            if ticket.email and attrs.get("email") != ticket.email:
                raise serializers.ValidationError("Email does not match the ticket owner.")

        attrs["ticket"] = ticket
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        ticket = validated_data["ticket"]
        is_authed = user and user.is_authenticated
        sender_name = ticket.name if is_authed else validated_data.get("name", ticket.name)
        sender_email = ticket.email if is_authed else validated_data.get("email", ticket.email)
        return SupportMessage.objects.create(
            ticket=ticket,
            sender=user if is_authed else None,
            sender_role=SupportMessage.SenderRole.USER if is_authed else SupportMessage.SenderRole.GUEST,
            sender_name=sender_name,
            sender_email=sender_email,
            message=validated_data["message"],
        )
