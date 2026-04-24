from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AdminOrderViewSet,
    AdminPaymentAssetViewSet,
    AdminProductViewSet,
    AdminSupportContactSettingsView,
    AdminUserViewSet,
    AdminDepositRequestViewSet,
    AdminWalletCryptoAssetViewSet,
    AdminWithdrawalRequestViewSet,
    GuestOrderViewSet,
    LoginView,
    LogoutView,
    MeView,
    NotificationStreamView,
    NotificationViewSet,
    OrderViewSet,
    DepositRequestViewSet,
    PaymentAssetViewSet,
    ProductViewSet,
    RegisterView,
    SupportMessageCreateView,
    SupportContactSettingsView,
    SupportTicketViewSet,
    WalletCryptoAssetViewSet,
    WalletSummaryView,
    WalletTransactionLogViewSet,
    WithdrawalRequestViewSet,
)

router = DefaultRouter()
router.register("products", ProductViewSet, basename="product")
router.register("payment-assets", PaymentAssetViewSet, basename="payment-asset")
router.register("orders", OrderViewSet, basename="order")
router.register("guest/orders", GuestOrderViewSet, basename="guest-order")
router.register("admin/products", AdminProductViewSet, basename="admin-product")
router.register("admin/payment-assets", AdminPaymentAssetViewSet, basename="admin-payment-asset")
router.register("admin/orders", AdminOrderViewSet, basename="admin-order")
router.register("admin/users", AdminUserViewSet, basename="admin-user")
router.register("notifications", NotificationViewSet, basename="notification")
router.register("support/tickets", SupportTicketViewSet, basename="support-ticket")
router.register("wallet/deposit-assets", WalletCryptoAssetViewSet, basename="wallet-deposit-assets")
router.register("wallet/deposits", DepositRequestViewSet, basename="wallet-deposits")
router.register("wallet/withdrawals", WithdrawalRequestViewSet, basename="wallet-withdrawals")
router.register("wallet/transactions", WalletTransactionLogViewSet, basename="wallet-transactions")
router.register("admin/wallet-assets", AdminWalletCryptoAssetViewSet, basename="admin-wallet-assets")
router.register("admin/wallet-deposits", AdminDepositRequestViewSet, basename="admin-wallet-deposits")
router.register("admin/wallet-withdrawals", AdminWithdrawalRequestViewSet, basename="admin-wallet-withdrawals")

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/me/", MeView.as_view(), name="me"),
    path("wallet/", WalletSummaryView.as_view(), name="wallet-summary"),
    path("notifications/stream/", NotificationStreamView.as_view(), name="notifications-stream"),
    path("support/config/", SupportContactSettingsView.as_view(), name="support-config"),
    path("support/messages/", SupportMessageCreateView.as_view(), name="support-message-create"),
    path("admin/support/config/", AdminSupportContactSettingsView.as_view(), name="admin-support-config"),
    path("", include(router.urls)),
]
