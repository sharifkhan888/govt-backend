from typing import Any, Dict
from django.contrib.auth import authenticate
from rest_framework import serializers
from . import models


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        user = authenticate(username=attrs.get("username"), password=attrs.get("password"))
        if not user:
            raise serializers.ValidationError("Invalid credentials")
        attrs["user"] = user
        return attrs


class UserSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, required=False)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    contact = serializers.CharField(required=False, allow_blank=True)
    role = serializers.IntegerField(required=False)
    status = serializers.CharField(required=False)

    def validate_username(self, value: str) -> str:
        qs = models.User.objects.filter(username=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A user with that username already exists.")
        return value

    def create(self, validated_data: Dict[str, Any]) -> models.User:
        password = validated_data.pop("password", None) or "changeme123"
        user = models.User(**validated_data)
        user.set_password(password)
        user.save()
        try:
            role_id = getattr(user, "role", None)
            ROLE_NAME_BY_ID = {
                1: "Chief Officer",
                2: "Accountant Officer",
                3: "Auditor",
                4: "Clerk",
            }
            role_name = ROLE_NAME_BY_ID.get(role_id)
            if role_name:
                role_obj = models.Role.objects.filter(name=role_name, is_active=True).first()
                if role_obj:
                    models.UserRole.objects.get_or_create(user=user, role=role_obj, defaults={"is_active": True})
        except Exception:
            pass
        return user

    def update(self, instance: models.User, validated_data: Dict[str, Any]) -> models.User:
        password = validated_data.pop("password", None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        if password:
            instance.set_password(password)
        instance.save()
        try:
            if "role" in validated_data:
                role_id = getattr(instance, "role", None)
                ROLE_NAME_BY_ID = {
                    1: "Chief Officer",
                    2: "Accountant Officer",
                    3: "Auditor",
                    4: "Clerk",
                }
                role_name = ROLE_NAME_BY_ID.get(role_id)
                if role_name:
                    role_obj = models.Role.objects.filter(name=role_name, is_active=True).first()
                    if role_obj:
                        ur, created = models.UserRole.objects.get_or_create(
                            user=instance, role=role_obj, defaults={"is_active": True}
                        )
                        if not created and not ur.is_active:
                            ur.is_active = True
                            ur.save(update_fields=["is_active"])
        except Exception:
            pass
        return instance


class RoleSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField()

    def validate_username(self, value: str) -> str:
        qs = models.User.objects.filter(username=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A user with that username already exists.")
        return value

    def create(self, validated_data: Dict[str, Any]) -> models.User:
        password = validated_data.pop("password", None) or "changeme123"
        user = models.User(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance: models.User, validated_data: Dict[str, Any]) -> models.User:
        password = validated_data.pop("password", None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class SettingSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    council_name = serializers.CharField(required=False, allow_blank=True)
    district_name = serializers.CharField(required=False, allow_blank=True)
    session = serializers.CharField(required=False, allow_blank=True)
    image_path = serializers.CharField(required=False, allow_blank=True)
    notice_date_111 = serializers.CharField(required=False, allow_blank=True)
    issue_date = serializers.CharField(required=False, allow_blank=True)
    renewal_date = serializers.CharField(required=False, allow_blank=True)
    assessment_year = serializers.CharField(required=False, allow_blank=True)
    notice_date_120 = serializers.CharField(required=False, allow_blank=True)
    age = serializers.IntegerField(required=False)

    def create(self, validated_data: Dict[str, Any]) -> models.Setting:
        obj = models.Setting.objects.create(**validated_data)
        return obj

    def update(self, instance: models.Setting, validated_data: Dict[str, Any]) -> models.Setting:
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        return instance


class BankAccountSerializer(serializers.Serializer):
    account_id = serializers.IntegerField(read_only=True)
    account_name = serializers.CharField(required=False, allow_blank=True)
    account_no = serializers.CharField(required=False, allow_blank=True)
    ifsc = serializers.CharField(required=False, allow_blank=True)
    bank_name = serializers.CharField(required=False, allow_blank=True)
    scheme_name = serializers.CharField(required=False, allow_blank=True)
    bank_manager_name = serializers.CharField(required=False, allow_blank=True)
    bank_contact = serializers.CharField(required=False, allow_blank=True)
    bank_address = serializers.CharField(required=False, allow_blank=True)
    remark = serializers.CharField(required=False, allow_blank=True)
    status = serializers.CharField(required=False, allow_blank=True)

    def create(self, validated_data: Dict[str, Any]) -> models.BankAccount:
        # Normalize account_no to Decimal or None
        from decimal import Decimal

        account_no = validated_data.get("account_no")
        if account_no in (None, ""):
            validated_data["account_no"] = None
        else:
            try:
                validated_data["account_no"] = Decimal(str(account_no))
            except Exception:
                validated_data["account_no"] = None

        if not validated_data.get("status"):
            validated_data["status"] = "active"

        obj = models.BankAccount.objects.create(**validated_data)
        return obj

    def update(self, instance: models.BankAccount, validated_data: Dict[str, Any]) -> models.BankAccount:
        from decimal import Decimal

        for key, value in validated_data.items():
            if key == "account_no":
                if value in (None, ""):
                    value = None
                else:
                    try:
                        value = Decimal(str(value))
                    except Exception:
                        value = None
            setattr(instance, key, value)
        instance.save()
        return instance


class ContractorSerializer(serializers.Serializer):
    contractor_id = serializers.IntegerField(read_only=True)
    contractor_name = serializers.CharField()
    contractor_address = serializers.CharField(required=False, allow_blank=True)
    contractor_contact_no = serializers.CharField(required=False, allow_blank=True)
    contractor_pan = serializers.CharField(required=False, allow_blank=True)
    contractor_tan = serializers.CharField(required=False, allow_blank=True)
    contractor_gst = serializers.CharField(required=False, allow_blank=True)
    contractor_bank_ac = serializers.CharField(required=False, allow_blank=True)
    contractor_ifsc = serializers.CharField(required=False, allow_blank=True)
    contractor_bank = serializers.CharField(required=False, allow_blank=True)
    remark = serializers.CharField(required=False, allow_blank=True)
    status = serializers.CharField(required=False, allow_blank=True)

    def create(self, validated_data: Dict[str, Any]) -> models.Contractor:
        # Default status
        if not validated_data.get("status"):
            validated_data["status"] = "active"
        obj = models.Contractor.objects.create(**validated_data)
        return obj

    def update(self, instance: models.Contractor, validated_data: Dict[str, Any]) -> models.Contractor:
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        return instance


class TransactionSerializer(serializers.Serializer):
    transaction_id = serializers.IntegerField(read_only=True)
    tx_type = serializers.ChoiceField(choices=("credit", "debit"))
    bank_account = serializers.IntegerField(required=False, allow_null=True)
    contractor = serializers.IntegerField(required=False, allow_null=True)
    transaction_date = serializers.DateField(required=False, allow_null=True)
    amount = serializers.DecimalField(required=False, allow_null=True, max_digits=18, decimal_places=2)
    account = serializers.CharField(required=False, allow_blank=True)
    particular = serializers.CharField(required=False, allow_blank=True)
    remark = serializers.CharField(required=False, allow_blank=True)
    bank_display_name = serializers.CharField(read_only=True)
    contractor_display_name = serializers.CharField(read_only=True)

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        # Validate foreign keys early to prevent DB-level 500 errors
        bank_id = attrs.get("bank_account")
        contractor_id = attrs.get("contractor")
        if bank_id is not None:
            if not models.BankAccount.objects.filter(pk=bank_id).exists():
                raise serializers.ValidationError({"bank_account": "Invalid bank_account id"})
        if contractor_id is not None:
            if not models.Contractor.objects.filter(pk=contractor_id).exists():
                raise serializers.ValidationError({"contractor": "Invalid contractor id"})
        # Keep account label in sync with tx_type when missing
        if not attrs.get("account") and attrs.get("tx_type"):
            attrs["account"] = str(attrs["tx_type"]).capitalize()
        return attrs

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        # Validate foreign keys early to prevent DB 500 errors
        bank_id = attrs.get("bank_account")
        contractor_id = attrs.get("contractor")
        if bank_id is not None:
            if not models.BankAccount.objects.filter(pk=bank_id).exists():
                raise serializers.ValidationError({"bank_account": "Invalid bank_account id"})
        if contractor_id is not None:
            if not models.Contractor.objects.filter(pk=contractor_id).exists():
                raise serializers.ValidationError({"contractor": "Invalid contractor id"})
        # Normalize account label if needed
        if not attrs.get("account") and attrs.get("tx_type"):
            attrs["account"] = str(attrs["tx_type"]).capitalize()
        return attrs

    def create(self, validated_data: Dict[str, Any]) -> models.Transaction:
        from datetime import date

        # Map foreign keys
        bank_id = validated_data.pop("bank_account", None)
        contractor_id = validated_data.pop("contractor", None)

        # Defaults
        if not validated_data.get("transaction_date"):
            validated_data["transaction_date"] = date.today()
        # Keep account label in sync with tx_type when missing
        if not validated_data.get("account") and validated_data.get("tx_type"):
            validated_data["account"] = validated_data["tx_type"].capitalize()

        obj = models.Transaction.objects.create(
            bank_account_id=bank_id,
            contractor_id=contractor_id,
            **validated_data,
        )
        # Persist snapshot of bank label for historical display
        try:
            obj.set_bank_display_name()
            obj.set_contractor_display_name()
            obj.save(update_fields=["bank_display_name", "contractor_display_name"])
        except Exception:
            pass
        return obj

    def update(self, instance: models.Transaction, validated_data: Dict[str, Any]) -> models.Transaction:
        # Map foreign keys
        if "bank_account" in validated_data:
            instance.bank_account_id = validated_data.pop("bank_account")
        if "contractor" in validated_data:
            instance.contractor_id = validated_data.pop("contractor")
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        # Refresh snapshot when bank changes or label empty
        try:
            if instance.bank_account_id and not instance.bank_display_name:
                instance.set_bank_display_name()
            if instance.contractor_id and not instance.contractor_display_name:
                instance.set_contractor_display_name()
            instance.save(update_fields=["bank_display_name", "contractor_display_name"])
        except Exception:
            pass
        return instance

    def to_representation(self, instance: models.Transaction) -> Dict[str, Any]:
        return {
            "transaction_id": instance.transaction_id,
            "tx_type": instance.tx_type,
            "bank_account": instance.bank_account_id,
            "contractor": instance.contractor_id,
            "transaction_date": instance.transaction_date.isoformat() if instance.transaction_date else None,
            "amount": str(instance.amount) if instance.amount is not None else None,
            "account": instance.account,
            "particular": instance.particular,
            "remark": instance.remark,
            "bank_display_name": instance.bank_display_name,
            "contractor_display_name": instance.contractor_display_name,
        }


class BalanceSnapshotSerializer(serializers.Serializer):
    snapshot_id = serializers.IntegerField(read_only=True)
    as_of_date = serializers.DateField()
    scope = serializers.CharField(required=False, allow_blank=True)
    bank_account = serializers.IntegerField(required=False, allow_null=True)
    contractor = serializers.IntegerField(required=False, allow_null=True)
    opening_balance = serializers.DecimalField(max_digits=18, decimal_places=2)
    total_credit = serializers.DecimalField(max_digits=18, decimal_places=2)
    total_debit = serializers.DecimalField(max_digits=18, decimal_places=2)
    net = serializers.DecimalField(max_digits=18, decimal_places=2)
    closing_balance = serializers.DecimalField(max_digits=18, decimal_places=2)
    created_at = serializers.DateTimeField(read_only=True)

    def create(self, validated_data):
        return models.BalanceSnapshot.objects.create(
            bank_account_id=validated_data.get("bank_account"),
            contractor_id=validated_data.get("contractor"),
            **{k: v for k, v in validated_data.items() if k not in ("bank_account", "contractor")}
        )

    def update(self, instance, validated_data):
        if "bank_account" in validated_data:
            instance.bank_account_id = validated_data.pop("bank_account")
        if "contractor" in validated_data:
            instance.contractor_id = validated_data.pop("contractor")
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        return instance


