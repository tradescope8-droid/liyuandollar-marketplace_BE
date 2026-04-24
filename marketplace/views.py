from django.conf import settings
from django.contrib.auth import get_user_model
import json
import time

from django.http import HttpResponse, StreamingHttpResponse
from django.db import transaction
from django.db.models import ProtectedError
from django.db.models import Sum
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

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
from .permissions import (
    CanAccessGuestOrder,
    CanAccessGuestPaidOrder,
    CanAccessPaidOrderOnly,
    IsStaffUserPermission,
)
from .serializers import (
    AdminOrderSerializer,
    AdminOrderStatusSerializer,
    AdminNoteSerializer,
    AdminPaymentAssetSerializer,
    AdminProductSerializer,
    AdminUserSerializer,
    AdminUserUpdateSerializer,
    AdminWalletCryptoAssetSerializer,
    build_guest_access_url,
    CredentialsSerializer,
    LoginSerializer,
    NotificationSerializer,
    OrderCreateSerializer,
    OrderSerializer,
    GuestOrderCreateSerializer,
    GuestOrderSerializer,
    DepositRequestCreateSerializer,
    DepositRequestSerializer,
    PaymentAssetSerializer,
    PaymentSubmissionSerializer,
    ProductDetailSerializer,
    ProductListSerializer,
    RegisterSerializer,
    SelectPaymentAssetSerializer,
    SupportMessageCreateSerializer,
    SupportMessageSerializer,
    SupportContactSettingsSerializer,
    SupportTicketCreateSerializer,
    SupportTicketDetailSerializer,
    SupportTicketSerializer,
    UserSerializer,
    WalletCryptoAssetSerializer,
    WalletTransactionLogSerializer,
    WithdrawalRequestCreateSerializer,
    WithdrawalRequestSerializer,
)
from .utils import build_credential_pdf_lines, build_simple_pdf, send_guest_order_email

User = get_user_model()


def send_guest_order_created_email(request, order):
    if not order.is_guest or not order.guest_email:
        return
    access_url = build_guest_access_url(request, order)
    payment_asset = order.selected_payment_asset
    body_lines = [
        f"Your order {order.order_number} has been created.",
        "",
        f"Product: {order.product.title}",
        f"Amount expected: {order.amount_expected}",
        f"Status: {order.get_status_display()}",
    ]
    if payment_asset:
        body_lines.extend(
            [
                f"Payment asset: {payment_asset.name} ({payment_asset.symbol})",
                f"Network: {payment_asset.network}",
                f"Wallet address: {payment_asset.wallet_address}",
                f"Instructions: {payment_asset.instructions or 'Follow the payment instructions shown on your order page.'}",
            ]
        )
    if access_url:
        body_lines.extend(
            [
                "",
                "Save this secure link to access your order later:",
                access_url,
                "Do not share this link.",
            ]
        )
    body_lines.extend(["", f"Support: {settings.SUPPORT_EMAIL}"])
    send_guest_order_email(order, f"Order created: {order.order_number}", body_lines)


def send_guest_status_email(request, order):
    if not order.is_guest or not order.guest_email:
        return
    access_url = build_guest_access_url(request, order)
    body_lines = [
        f"Your order {order.order_number} status is now {order.get_status_display()}.",
        f"Product: {order.product.title}",
        f"Amount expected: {order.amount_expected}",
    ]
    if access_url:
        body_lines.extend(["", f"View your order: {access_url}"])
    if order.is_paid:
        body_lines.append("Credentials and PDF download are now available.")
    body_lines.extend(["", f"Support: {settings.SUPPORT_EMAIL}"])
    send_guest_order_email(order, f"Order update: {order.order_number}", body_lines)


def set_auth_cookies(response, user):
    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)
    refresh_token = str(refresh)
    response.set_cookie(
        settings.AUTH_COOKIE_ACCESS,
        access_token,
        httponly=settings.AUTH_COOKIE_HTTP_ONLY,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        max_age=int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()),
    )
    response.set_cookie(
        settings.AUTH_COOKIE_REFRESH,
        refresh_token,
        httponly=settings.AUTH_COOKIE_HTTP_ONLY,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
    )


def clear_auth_cookies(response):
    response.delete_cookie(settings.AUTH_COOKIE_ACCESS, samesite=settings.AUTH_COOKIE_SAMESITE)
    response.delete_cookie(settings.AUTH_COOKIE_REFRESH, samesite=settings.AUTH_COOKIE_SAMESITE)


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        if not user.is_active:
            admin_users = User.objects.filter(is_staff=True)
            Notification.objects.bulk_create(
                [
                    Notification(
                        user=admin_user,
                        level=Notification.Level.WARNING,
                        title="New user awaiting approval",
                        message=f"{user.username or user.email} has registered and needs approval.",
                    )
                    for admin_user in admin_users
                ]
            )
        response = Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
        if user.is_active:
            set_auth_cookies(response, user)
        return response


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])
        response = Response(UserSerializer(user).data)
        set_auth_cookies(response, user)
        return response


class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_auth_cookies(response)
        return response


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    lookup_field = "pk"

    def get_queryset(self):
        return Product.objects.filter(status=Product.Status.AVAILABLE, stock_count__gt=0)

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ProductDetailSerializer
        return ProductListSerializer


class PaymentAssetViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PaymentAssetSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return PaymentAsset.objects.filter(is_active=True)


class OrderViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = OrderSerializer
    permission_classes = [AllowAny]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        queryset = (
            Order.objects.select_related("product", "selected_payment_asset", "user")
            .prefetch_related("payment_submissions")
        )
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.action == "create":
            return OrderCreateSerializer
        return OrderSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        if order.is_guest:
            send_guest_order_created_email(request, order)
            output = GuestOrderSerializer(order, context={"request": request})
        else:
            output = OrderSerializer(order, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)

    def get_object(self):
        obj = super().get_object()
        self.check_object_permissions(self.request, obj)
        return obj

    def get_permissions(self):
        if self.action in ["create"]:
            return [AllowAny()]
        if self.action in ["list", "retrieve", "select_payment_asset", "payment_details", "submit_payment", "pay_with_wallet"]:
            return [IsAuthenticated()]
        if self.action in ["credentials", "download_pdf"]:
            return [CanAccessPaidOrderOnly()]
        return super().get_permissions()

    @action(detail=True, methods=["post"], url_path="select-payment-asset")
    def select_payment_asset(self, request, pk=None):
        order = self.get_object()
        serializer = SelectPaymentAssetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        asset = PaymentAsset.objects.get(pk=serializer.validated_data["payment_asset_id"], is_active=True)
        order.selected_payment_asset = asset
        order.status = Order.Status.PENDING
        order.save(update_fields=["selected_payment_asset", "status", "updated_at"])
        return Response(OrderSerializer(order, context={"request": request}).data)

    @action(detail=True, methods=["get"], url_path="payment-details")
    def payment_details(self, request, pk=None):
        order = self.get_object()
        if not order.selected_payment_asset:
            return Response(
                {"detail": "Select a payment asset first."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        asset_data = PaymentAssetSerializer(order.selected_payment_asset, context={"request": request}).data
        return Response(
            {
                "order_id": order.id,
                "reference": str(order.order_number),
                "status": order.status,
                "asset": asset_data,
            }
        )

    @action(detail=True, methods=["post"], url_path="submit-payment")
    def submit_payment(self, request, pk=None):
        order = self.get_object()
        if not order.selected_payment_asset:
            return Response(
                {"detail": "Select a payment asset before submitting payment."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        tx_hash = (request.data.get("tx_hash", "") or "").strip()
        screenshot = request.data.get("screenshot")
        if not tx_hash:
            return Response(
                {"detail": "Transaction hash / ID is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not screenshot:
            return Response(
                {"detail": "Payment screenshot is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        submission = PaymentSubmission.objects.create(
            order=order,
            tx_hash=tx_hash,
            sender_wallet_address=request.data.get("sender_wallet_address", ""),
            note=request.data.get("note", ""),
            screenshot=screenshot,
        )
        order.status = Order.Status.AWAITING_CONFIRMATION
        order.save(update_fields=["status", "updated_at"])
        return Response(
            {
                "order": OrderSerializer(order, context={"request": request}).data,
                "submission": PaymentSubmissionSerializer(submission, context={"request": request}).data,
                "message": "Payment submitted. Admin confirmation is required before credentials unlock.",
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"], url_path="credentials")
    def credentials(self, request, pk=None):
        order = self.get_object()
        if not order.is_paid:
            return Response({"detail": "Credentials are only available for paid orders."}, status=status.HTTP_403_FORBIDDEN)
        access, _ = PurchasedCredentialAccess.objects.get_or_create(order=order)
        serializer = CredentialsSerializer(
            {
                "credentials": order.product.credentials_data,
                "unlocked_at": access.unlocked_at,
            }
        )
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="download-pdf")
    def download_pdf(self, request, pk=None):
        order = self.get_object()
        if not order.is_paid:
            return Response({"detail": "PDF downloads are only available for paid orders."}, status=status.HTTP_403_FORBIDDEN)
        access, _ = PurchasedCredentialAccess.objects.get_or_create(order=order)
        lines = build_credential_pdf_lines(order, access.unlocked_at)
        pdf_bytes = build_simple_pdf("LiyanDollar Marketplace Credentials", lines)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{order.order_number}-credentials.pdf"'
        return response

    @action(detail=True, methods=["post"], url_path="pay-with-wallet")
    def pay_with_wallet(self, request, pk=None):
        order = self.get_object()
        if not order.user_id:
            return Response({"detail": "Wallet payments are available for registered users only."}, status=status.HTTP_403_FORBIDDEN)
        if order.user_id != request.user.id:
            return Response({"detail": "You do not have permission to pay for this order."}, status=status.HTTP_403_FORBIDDEN)
        if order.is_paid:
            return Response({"detail": "Order is already marked as paid."}, status=status.HTTP_400_BAD_REQUEST)
        if not order.product.is_available_for_purchase:
            return Response({"detail": "This product is no longer available."}, status=status.HTTP_400_BAD_REQUEST)
        if order.product.single_item and order.quantity > 1:
            return Response({"detail": "This product can only be purchased once."}, status=status.HTTP_400_BAD_REQUEST)
        if order.quantity > order.product.stock_count:
            return Response({"detail": "Requested quantity exceeds available stock."}, status=status.HTTP_400_BAD_REQUEST)

        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
            if wallet.balance < order.amount_expected:
                return Response({"detail": "Insufficient wallet balance."}, status=status.HTTP_400_BAD_REQUEST)
            balance_before = wallet.balance
            wallet.balance = balance_before - order.amount_expected
            wallet.save(update_fields=["balance", "updated_at"])
            WalletTransactionLog.objects.create(
                user=request.user,
                wallet=wallet,
                transaction_type=WalletTransactionLog.TransactionType.PURCHASE,
                reference_type=WalletTransactionLog.ReferenceType.ORDER,
                reference_id=order.id,
                amount=order.amount_expected,
                balance_before=balance_before,
                balance_after=wallet.balance,
                status=Order.Status.PAID,
                description="Marketplace purchase paid with wallet balance.",
            )
            order.status = Order.Status.PAID
            order.save(update_fields=["status", "updated_at"])

        return Response(OrderSerializer(order, context={"request": request}).data)


class GuestOrderViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = GuestOrderSerializer
    permission_classes = [AllowAny]
    lookup_field = "guest_access_token"
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        return (
            Order.objects.filter(user__isnull=True, is_guest=True)
            .select_related("product", "selected_payment_asset")
            .prefetch_related("payment_submissions")
        )

    def get_serializer_class(self):
        if self.action == "create":
            return GuestOrderCreateSerializer
        return GuestOrderSerializer

    def get_object(self):
        obj = super().get_object()
        if not CanAccessGuestOrder().has_object_permission(self.request, self, obj):
            self.permission_denied(self.request, message="Guest access denied.")
        return obj

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        send_guest_order_created_email(request, order)
        output = GuestOrderSerializer(order, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="select-payment-asset")
    def select_payment_asset(self, request, guest_access_token=None):
        order = self.get_object()
        serializer = SelectPaymentAssetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        asset = PaymentAsset.objects.get(pk=serializer.validated_data["payment_asset_id"], is_active=True)
        order.selected_payment_asset = asset
        order.status = Order.Status.PENDING
        order.save(update_fields=["selected_payment_asset", "status", "updated_at"])
        return Response(GuestOrderSerializer(order, context={"request": request}).data)

    @action(detail=True, methods=["get"], url_path="payment-details")
    def payment_details(self, request, guest_access_token=None):
        order = self.get_object()
        if not order.selected_payment_asset:
            return Response(
                {"detail": "Select a payment asset first."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        asset_data = PaymentAssetSerializer(order.selected_payment_asset, context={"request": request}).data
        return Response(
            {
                "order_id": order.id,
                "reference": str(order.order_number),
                "status": order.status,
                "asset": asset_data,
            }
        )

    @action(detail=True, methods=["post"], url_path="submit-payment")
    def submit_payment(self, request, guest_access_token=None):
        order = self.get_object()
        if not order.selected_payment_asset:
            return Response(
                {"detail": "Select a payment asset before submitting payment."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        tx_hash = (request.data.get("tx_hash", "") or "").strip()
        screenshot = request.data.get("screenshot")
        if not tx_hash:
            return Response(
                {"detail": "Transaction hash / ID is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not screenshot:
            return Response(
                {"detail": "Payment screenshot is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        submission = PaymentSubmission.objects.create(
            order=order,
            tx_hash=tx_hash,
            sender_wallet_address=request.data.get("sender_wallet_address", ""),
            note=request.data.get("note", ""),
            screenshot=screenshot,
        )
        order.status = Order.Status.AWAITING_CONFIRMATION
        order.save(update_fields=["status", "updated_at"])
        send_guest_status_email(request, order)
        return Response(
            {
                "order": GuestOrderSerializer(order, context={"request": request}).data,
                "submission": PaymentSubmissionSerializer(submission, context={"request": request}).data,
                "message": "Payment submitted. Admin confirmation is required before credentials unlock.",
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"], url_path="credentials")
    def credentials(self, request, guest_access_token=None):
        order = self.get_object()
        if not CanAccessGuestPaidOrder().has_object_permission(request, self, order):
            return Response({"detail": "Credentials are only available for paid orders."}, status=status.HTTP_403_FORBIDDEN)
        access, _ = PurchasedCredentialAccess.objects.get_or_create(order=order)
        serializer = CredentialsSerializer(
            {
                "credentials": order.product.credentials_data,
                "unlocked_at": access.unlocked_at,
            }
        )
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="download-pdf")
    def download_pdf(self, request, guest_access_token=None):
        order = self.get_object()
        if not CanAccessGuestPaidOrder().has_object_permission(request, self, order):
            return Response({"detail": "PDF downloads are only available for paid orders."}, status=status.HTTP_403_FORBIDDEN)
        access, _ = PurchasedCredentialAccess.objects.get_or_create(order=order)
        lines = build_credential_pdf_lines(order, access.unlocked_at)
        pdf_bytes = build_simple_pdf("LiyanDollar Marketplace Credentials", lines)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{order.order_number}-credentials.pdf"'
        return response


class AdminProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all().order_by("-created_at")
    serializer_class = AdminProductSerializer
    permission_classes = [IsStaffUserPermission]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def destroy(self, request, *args, **kwargs):
        product = self.get_object()
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {
                    "detail": (
                        f"{product.title} cannot be deleted because it is already linked to one or more orders. "
                        "Mark it as inactive instead if you want to remove it from sale."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class AdminPaymentAssetViewSet(viewsets.ModelViewSet):
    queryset = PaymentAsset.objects.all().order_by("display_order", "name")
    serializer_class = AdminPaymentAssetSerializer
    permission_classes = [IsStaffUserPermission]
    parser_classes = [JSONParser, MultiPartParser, FormParser]


class AdminOrderViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = (
        Order.objects.select_related("product", "selected_payment_asset", "user")
        .prefetch_related("payment_submissions")
        .order_by("-created_at")
    )
    serializer_class = AdminOrderSerializer
    permission_classes = [IsStaffUserPermission]

    @action(detail=True, methods=["post"], url_path="set-status")
    def set_status(self, request, pk=None):
        order = self.get_object()
        serializer = AdminOrderStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order.status = serializer.validated_data["status"]
        order.save()
        if order.is_guest:
            send_guest_status_email(request, order)
        return Response(AdminOrderSerializer(order, context={"request": request}).data)


class AdminUserViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = User.objects.all().order_by("-date_joined")
    permission_classes = [IsStaffUserPermission]

    def get_serializer_class(self):
        if self.action in ["update", "partial_update"]:
            return AdminUserUpdateSerializer
        return AdminUserSerializer

    def update(self, request, *args, **kwargs):
        user_obj = self.get_object()
        if request.user and request.user.id == user_obj.id:
            is_staff = request.data.get("is_staff")
            is_active = request.data.get("is_active")
            if is_staff is not None and str(is_staff).lower() in ["false", "0", "off"]:
                return Response({"detail": "You cannot remove your own admin access."}, status=status.HTTP_400_BAD_REQUEST)
            if is_active is not None and str(is_active).lower() in ["false", "0", "off"]:
                return Response({"detail": "You cannot deactivate your own account."}, status=status.HTTP_400_BAD_REQUEST)
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=["patch"], url_path="set-role")
    def set_role(self, request, pk=None):
        user = self.get_object()
        if request.user and request.user.id == user.id:
            if "is_staff" in request.data and not bool(request.data.get("is_staff")):
                return Response({"detail": "You cannot remove your own admin access."}, status=status.HTTP_400_BAD_REQUEST)
            if "is_active" in request.data and not bool(request.data.get("is_active")):
                return Response({"detail": "You cannot deactivate your own account."}, status=status.HTTP_400_BAD_REQUEST)
        user.is_staff = bool(request.data.get("is_staff", user.is_staff))
        user.is_active = bool(request.data.get("is_active", user.is_active))
        user.save(update_fields=["is_staff", "is_active"])
        return Response(AdminUserSerializer(user).data)


class WalletSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        confirmed_statuses = ["confirmed", "approved", "completed"]
        totals = (
            WalletTransactionLog.objects.filter(user=request.user, status__in=confirmed_statuses)
            .values("transaction_type")
            .annotate(total=Sum("amount"))
        )
        totals_map = {row["transaction_type"]: row["total"] or 0 for row in totals}
        return Response(
            {
                "id": wallet.id,
                "balance": wallet.balance,
                "currency_label": "USD",
                "total_deposits": totals_map.get(WalletTransactionLog.TransactionType.DEPOSIT, 0),
                "total_withdrawals": totals_map.get(WalletTransactionLog.TransactionType.WITHDRAWAL, 0),
            }
        )


class WalletCryptoAssetViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PaymentAssetSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PaymentAsset.objects.filter(is_active=True)


class DepositRequestViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return DepositRequest.objects.filter(user=self.request.user).select_related("crypto_asset")

    def get_serializer_class(self):
        if self.action == "create":
            return DepositRequestCreateSerializer
        return DepositRequestSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        deposit = serializer.save()
        output = DepositRequestSerializer(deposit, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)


class WithdrawalRequestViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        return WithdrawalRequest.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.action == "create":
            return WithdrawalRequestCreateSerializer
        return WithdrawalRequestSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        withdrawal = serializer.save()
        output = WithdrawalRequestSerializer(withdrawal, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)


class WalletTransactionLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = WalletTransactionLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return WalletTransactionLog.objects.filter(user=self.request.user)


class AdminWalletCryptoAssetViewSet(viewsets.ModelViewSet):
    queryset = WalletCryptoAsset.objects.all().order_by("name")
    serializer_class = AdminWalletCryptoAssetSerializer
    permission_classes = [IsStaffUserPermission]
    parser_classes = [JSONParser, MultiPartParser, FormParser]


class AdminDepositRequestViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DepositRequest.objects.select_related("user", "wallet", "crypto_asset").order_by("-created_at")
    serializer_class = DepositRequestSerializer
    permission_classes = [IsStaffUserPermission]

    @action(detail=True, methods=["post"], url_path="confirm")
    def confirm(self, request, pk=None):
        deposit = self.get_object()
        note_serializer = AdminNoteSerializer(data=request.data)
        note_serializer.is_valid(raise_exception=True)
        try:
            deposit.confirm(admin_note=note_serializer.validated_data.get("admin_note", ""))
            if deposit.user:
                Notification.objects.create(
                    user=deposit.user,
                    order=None,
                    level=Notification.Level.SUCCESS,
                    title="Deposit confirmed",
                    message=f"Your deposit of ${deposit.amount} has been confirmed.",
                )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(DepositRequestSerializer(deposit, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        deposit = self.get_object()
        note_serializer = AdminNoteSerializer(data=request.data)
        note_serializer.is_valid(raise_exception=True)
        try:
            deposit.reject(admin_note=note_serializer.validated_data.get("admin_note", ""))
            if deposit.user:
                Notification.objects.create(
                    user=deposit.user,
                    order=None,
                    level=Notification.Level.ERROR,
                    title="Deposit rejected",
                    message=f"Your deposit of ${deposit.amount} was rejected.",
                )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(DepositRequestSerializer(deposit, context={"request": request}).data)


class AdminWithdrawalRequestViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = WithdrawalRequest.objects.select_related("user", "wallet").order_by("-created_at")
    serializer_class = WithdrawalRequestSerializer
    permission_classes = [IsStaffUserPermission]

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        withdrawal = self.get_object()
        note_serializer = AdminNoteSerializer(data=request.data)
        note_serializer.is_valid(raise_exception=True)
        try:
            withdrawal.approve(admin_note=note_serializer.validated_data.get("admin_note", ""))
            if withdrawal.user:
                Notification.objects.create(
                    user=withdrawal.user,
                    order=None,
                    level=Notification.Level.SUCCESS,
                    title="Withdrawal approved",
                    message=f"Your withdrawal of ${withdrawal.amount} has been approved.",
                )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(WithdrawalRequestSerializer(withdrawal, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        withdrawal = self.get_object()
        note_serializer = AdminNoteSerializer(data=request.data)
        note_serializer.is_valid(raise_exception=True)
        try:
            withdrawal.complete(admin_note=note_serializer.validated_data.get("admin_note", ""))
            if withdrawal.user:
                Notification.objects.create(
                    user=withdrawal.user,
                    order=None,
                    level=Notification.Level.SUCCESS,
                    title="Withdrawal completed",
                    message=f"Your withdrawal of ${withdrawal.amount} has been completed.",
                )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(WithdrawalRequestSerializer(withdrawal, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        withdrawal = self.get_object()
        note_serializer = AdminNoteSerializer(data=request.data)
        note_serializer.is_valid(raise_exception=True)
        try:
            withdrawal.reject(admin_note=note_serializer.validated_data.get("admin_note", ""))
            if withdrawal.user:
                Notification.objects.create(
                    user=withdrawal.user,
                    order=None,
                    level=Notification.Level.ERROR,
                    title="Withdrawal rejected",
                    message=f"Your withdrawal of ${withdrawal.amount} was rejected.",
                )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(WithdrawalRequestSerializer(withdrawal, context={"request": request}).data)


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Notification.objects.filter(user=self.request.user)
        since_id = self.request.query_params.get("since_id")
        if since_id and since_id.isdigit():
            queryset = queryset.filter(id__gt=int(since_id))
        return queryset

    @action(detail=False, methods=["post"], url_path="mark-read")
    def mark_read(self, request):
        ids = request.data.get("ids", [])
        if not isinstance(ids, list):
            return Response({"detail": "ids must be a list."}, status=status.HTTP_400_BAD_REQUEST)
        Notification.objects.filter(user=request.user, id__in=ids).update(is_read=True)
        return Response({"status": "ok"})


class NotificationStreamView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        last_id = request.GET.get("last_id")
        last_id_int = int(last_id) if last_id and last_id.isdigit() else 0

        def event_stream():
            nonlocal last_id_int
            while True:
                notifications = list(
                    Notification.objects.filter(user=request.user, id__gt=last_id_int).order_by("id")[:10]
                )
                if notifications:
                    last_id_int = notifications[-1].id
                    payload = NotificationSerializer(notifications, many=True).data
                    yield f"data: {json.dumps(payload)}\n\n"
                time.sleep(5)

        response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        return response


class SupportTicketViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = SupportTicketSerializer
    queryset = SupportTicket.objects.all().prefetch_related("messages")

    def get_permissions(self):
        if self.action == "create":
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_queryset(self):
        if self.request.user.is_authenticated:
            return SupportTicket.objects.filter(user=self.request.user).prefetch_related("messages")
        return SupportTicket.objects.none()

    def get_serializer_class(self):
        if self.action == "create":
            return SupportTicketCreateSerializer
        if self.action == "retrieve":
            return SupportTicketDetailSerializer
        return SupportTicketSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        ticket = serializer.save()
        output = SupportTicketDetailSerializer(ticket, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)


class SupportMessageCreateView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SupportMessageCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        message = serializer.save()
        return Response(SupportMessageSerializer(message).data, status=status.HTTP_201_CREATED)


class SupportContactSettingsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        config = SupportContactSettings.get_solo()
        return Response(SupportContactSettingsSerializer(config).data)


class AdminSupportContactSettingsView(APIView):
    permission_classes = [IsStaffUserPermission]

    def get(self, request):
        config = SupportContactSettings.get_solo()
        return Response(SupportContactSettingsSerializer(config).data)

    def put(self, request):
        config = SupportContactSettings.get_solo()
        serializer = SupportContactSettingsSerializer(config, data=request.data, partial=False)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
