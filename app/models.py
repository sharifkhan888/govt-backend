from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_CHOICES = (
        (1, "Chief Officer (Master Admin)"),
        (2, "Accountant Officer"),
        (3, "Auditor"),
        (4, "Clerk"),
    )
    # Default new users to Clerk unless explicitly set
    role = models.PositiveSmallIntegerField(choices=ROLE_CHOICES, default=4)
    status = models.CharField(max_length=50, default="active")
    contact = models.CharField(max_length=50, blank=True)

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.username}"


class Setting(models.Model):
    council_name = models.CharField(max_length=50, blank=True)
    district_name = models.CharField(max_length=50, blank=True)
    session = models.CharField(max_length=50, blank=True)
    image_path = models.CharField(max_length=500, blank=True)
    notice_date_111 = models.CharField(max_length=50, blank=True)
    issue_date = models.CharField(max_length=50, blank=True)
    renewal_date = models.CharField(max_length=50, blank=True)
    assessment_year = models.CharField(max_length=50, blank=True)
    notice_date_120 = models.CharField(max_length=50, blank=True)
    age = models.PositiveSmallIntegerField(default=0)


class BankAccount(models.Model):
    account_id = models.BigAutoField(primary_key=True)
    account_name = models.CharField(max_length=250, blank=True)
    account_no = models.DecimalField(max_digits=25, decimal_places=0, null=True, blank=True)
    ifsc = models.CharField(max_length=11, blank=True)
    bank_name = models.CharField(max_length=50, blank=True)
    scheme_name = models.CharField(max_length=250, blank=True)
    bank_manager_name = models.CharField(max_length=50, blank=True)
    bank_contact = models.CharField(max_length=50, blank=True)
    bank_address = models.CharField(max_length=250, blank=True)
    remark = models.CharField(max_length=300, blank=True)
    update_by = models.IntegerField(null=True, blank=True)
    last_update_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=50, blank=True)


class Contractor(models.Model):
    contractor_id = models.BigAutoField(primary_key=True)
    contractor_name = models.CharField(max_length=250)
    contractor_address = models.CharField(max_length=300, blank=True)
    contractor_contact_no = models.CharField(max_length=50, blank=True)
    contractor_pan = models.CharField(max_length=50, blank=True)
    contractor_tan = models.CharField(max_length=50, blank=True)
    contractor_gst = models.CharField(max_length=50, blank=True)
    contractor_bank_ac = models.CharField(max_length=50, blank=True)
    contractor_ifsc = models.CharField(max_length=50, blank=True)
    contractor_bank = models.CharField(max_length=50, blank=True)
    remark = models.CharField(max_length=250, blank=True)
    update_by = models.IntegerField(null=True, blank=True)
    last_update_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=50, blank=True)


class Transaction(models.Model):
    CREDIT = "credit"
    DEBIT = "debit"
    TX_TYPES = ((CREDIT, "Credit"), (DEBIT, "Debit"))

    transaction_id = models.AutoField(primary_key=True)
    tx_type = models.CharField(max_length=6, choices=TX_TYPES)
    bank_account = models.ForeignKey(BankAccount, on_delete=models.SET_NULL, null=True, blank=True)
    # Persist original bank label for historical display even if bank is deleted
    bank_display_name = models.CharField(max_length=250, blank=True)
    contractor = models.ForeignKey(Contractor, on_delete=models.SET_NULL, null=True, blank=True)
    # Persist original contractor name for historical display even if contractor is deleted
    contractor_display_name = models.CharField(max_length=250, blank=True)
    transaction_date = models.DateField(null=True, blank=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    account = models.CharField(max_length=50, blank=True)
    particular = models.CharField(max_length=250, blank=True)
    remark = models.CharField(max_length=250, blank=True)
    update_by = models.IntegerField(null=True, blank=True)
    last_update_date = models.DateField(null=True, blank=True)

    def set_bank_display_name(self) -> None:
        """Set a human-readable bank label from the related BankAccount.

        Prefers account_name, then account_no, then bank_name. This keeps
        transaction history readable even after the related bank account is deleted.
        """
        try:
            b = self.bank_account
            if not b:
                return
            label = (b.account_name or "").strip() or (str(b.account_no or "").strip()) or (b.bank_name or "").strip()
            self.bank_display_name = label
        except Exception:
            # Leave existing label unchanged on error
            pass

    def set_contractor_display_name(self) -> None:
        """Set a human-readable contractor label from the related Contractor.

        Keeps transaction history readable even after the related contractor is deleted.
        """
        try:
            c = self.contractor
            if not c:
                return
            label = (c.contractor_name or "").strip()
            self.contractor_display_name = label
        except Exception:
            # Leave existing label unchanged on error
            pass


class Payment(models.Model):
    credit_payment_id = models.AutoField(primary_key=True)
    received_from = models.CharField(max_length=250, blank=True)
    deposit_to_account = models.CharField(max_length=250, blank=True)
    payment_deposit_account = models.ForeignKey(BankAccount, on_delete=models.SET_NULL, null=True, blank=True)
    received_date = models.DateField(null=True, blank=True)
    received_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    account = models.CharField(max_length=50, blank=True)
    particular = models.CharField(max_length=250, blank=True)
    remark = models.CharField(max_length=250, blank=True)
    update_by = models.IntegerField(null=True, blank=True)
    last_update_date = models.DateField(null=True, blank=True)


class BackupLog(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    file_path = models.CharField(max_length=500)
    action = models.CharField(max_length=20, default="backup")

class BalanceSnapshot(models.Model):
    snapshot_id = models.AutoField(primary_key=True)
    as_of_date = models.DateField()
    scope = models.CharField(max_length=20, default="all", blank=True)

    # Optional scoping (overall or per bank/contractor)
    bank_account = models.ForeignKey(BankAccount, on_delete=models.SET_NULL, null=True, blank=True)
    contractor = models.ForeignKey(Contractor, on_delete=models.SET_NULL, null=True, blank=True)

    opening_balance = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_credit = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_debit = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    net = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    closing_balance = models.DecimalField(max_digits=18, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        label = self.scope or "all"
        return f"Snapshot {self.as_of_date} ({label})"


# RBAC Models for Role-Based Access Control
class Role(models.Model):
    """Role-based access control role definitions."""
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Permission(models.Model):
    """Permission definitions for role-based access control."""
    PERMISSION_CATEGORIES = [
        ('user', 'User Management'),
        ('bank_account', 'Bank Account Management'),
        ('contractor', 'Contractor Management'),
        ('transaction', 'Transaction Management'),
        ('settings', 'System Settings'),
        ('reports', 'Reports'),
        ('backup', 'Backup & Restore'),
    ]

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=PERMISSION_CATEGORIES)
    codename = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['category', 'name']

    def __str__(self):
        return f"{self.category}: {self.name}"


class RolePermission(models.Model):
    """Many-to-many relationship between roles and permissions."""
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='permissions')
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name='roles')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['role', 'permission']

    def __str__(self):
        return f"{self.role} - {self.permission}"


class UserRole(models.Model):
    """Many-to-many relationship between users and roles."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user_roles')
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='user_roles')
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ['user', 'role']

    def __str__(self):
        return f"{self.user} - {self.role}"


