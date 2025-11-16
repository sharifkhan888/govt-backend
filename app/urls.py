from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views, rbac_examples


router = DefaultRouter()
router.register(r"users", views.UserViewSet, basename="user")
router.register(r"settings", views.SettingViewSet, basename="setting")
router.register(r"bank-accounts", views.BankAccountViewSet, basename="bankaccount")
router.register(r"contractors", views.ContractorViewSet, basename="contractor")
router.register(r"transactions", views.TransactionViewSet, basename="transaction")
router.register(r"roles", views.RoleViewSet, basename="role")

# Define non-router paths first, then extend with router URLs.
urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("me/permissions/", views.MePermissionsView.as_view(), name="me_permissions"),
    path("reports/", views.ReportsView.as_view(), name="reports"),
    path("reports", views.ReportsView.as_view(), name="reports_no_slash"),
    path("r/", views.ReportsView.as_view(), name="reports_short"),
    path("backup/", views.BackupView.as_view(), name="backup"),
    path("settings/image-path/", views.SettingsImagePathView.as_view(), name="settings_image_path"),
    path("access-denied/", views.AccessDeniedView.as_view(), name="access_denied"),
    path("download/<str:filename>", views.DownloadExportView.as_view(), name="download_export"),
    path("rbac-test/", rbac_examples.rbac_test_page, name="rbac_test"),
    path("api/rbac-example/", rbac_examples.RBACExampleView.as_view(), name="rbac_example"),
    path("api/rbac-multi/", rbac_examples.MultiPermissionExampleView.as_view(), name="rbac_multi"),
    path("api/rbac-role/", rbac_examples.RoleBasedExampleView.as_view(), name="rbac_role"),
] + router.urls


