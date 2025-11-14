from datetime import date
from typing import Any, Dict

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils.timezone import now
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from rest_framework import permissions, status, views, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.response import Response

from . import models, serializers
from .decorators import has_permission, has_any_permission, role_required, any_role_required
from .utils.export import (
    export_bank_accounts_excel,
    export_contractors_excel,
    export_report_pdf,
    export_bank_account_pdf,
    export_contractor_pdf,
    export_profit_loss_pdf,
    export_bank_wise_pdf,
    export_contractor_wise_pdf,
    export_transaction_register_pdf,
)
from .utils.backup import create_backup, restore_backup

User = get_user_model()


class LoginView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = serializers.LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "username": user.username, "role": user.role})


class MePermissionsView(views.APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return Response({"permissions": []})
        roles = models.UserRole.objects.filter(user=request.user, is_active=True).values_list("role_id", flat=True)
        if roles:
            perms = models.RolePermission.objects.filter(role_id__in=list(roles)).select_related("permission")
            codenames = sorted({rp.permission.codename for rp in perms})
            return Response({"permissions": codenames})

        # Fallback: map User.role (choices int) to Role name to derive permissions
        role_id = getattr(request.user, "role", None)
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
                perms = models.RolePermission.objects.filter(role_id=role_obj.id).select_related("permission")
                codenames = sorted({rp.permission.codename for rp in perms})
                return Response({"permissions": codenames})

        return Response({"permissions": []})


@method_decorator(has_permission('view_users'), name='list')
@method_decorator(has_permission('add_users'), name='create')
@method_decorator(has_permission('edit_users'), name='update')
@method_decorator(has_permission('edit_users'), name='partial_update')
@method_decorator(has_permission('delete_users'), name='destroy')
class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by("id")
    serializer_class = serializers.UserSerializer

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        ids = request.data.get("ids") or []
        if isinstance(ids, str):
            ids = [i for i in ids.replace(" ", "").split(",") if i]
        try:
            ids = [int(i) for i in ids]
        except Exception:
            return Response({"detail": "Invalid ids payload"}, status=status.HTTP_400_BAD_REQUEST)
        qs = User.objects.filter(id__in=ids)
        deleted, _ = qs.delete()
        return Response({"deleted": deleted, "ids": ids})

class RoleViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = models.Role.objects.filter(is_active=True).order_by("id")
    serializer_class = serializers.RoleSerializer


@method_decorator(has_permission('view_settings'), name='list')
@method_decorator(has_permission('edit_settings'), name='create')
@method_decorator(has_permission('edit_settings'), name='update')
@method_decorator(has_permission('edit_settings'), name='partial_update')
@method_decorator(has_permission('edit_settings'), name='destroy')
class SettingViewSet(viewsets.ModelViewSet):
    queryset = models.Setting.objects.all().order_by("id")
    serializer_class = serializers.SettingSerializer


@method_decorator(has_permission('view_banks'), name='list')
@method_decorator(has_permission('add_banks'), name='create')
@method_decorator(has_permission('edit_banks'), name='update')
@method_decorator(has_permission('edit_banks'), name='partial_update')
@method_decorator(has_permission('delete_banks'), name='destroy')
@method_decorator(has_permission('delete_banks'), name='bulk_delete')
class BankAccountViewSet(viewsets.ModelViewSet):
    queryset = models.BankAccount.objects.all().order_by("account_id")
    serializer_class = serializers.BankAccountSerializer

    @action(detail=False, methods=["get"])
    def export(self, request):
        file_path = export_bank_accounts_excel()
        return Response({"file": file_path})

    @action(detail=True, methods=["get"], url_path="export-pdf")
    def export_pdf(self, request, pk=None):
        file_path = export_bank_account_pdf(int(pk))
        return Response({"file": file_path})

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        ids = request.data.get("ids") or []
        if isinstance(ids, str):
            ids = [i for i in ids.replace(" ", "").split(",") if i]
        try:
            ids = [int(i) for i in ids]
        except Exception:
            return Response({"detail": "Invalid ids payload"}, status=status.HTTP_400_BAD_REQUEST)
        qs = models.BankAccount.objects.filter(account_id__in=ids)
        # Snapshot bank labels into related transactions before deletion
        try:
            for b in qs:
                label = (b.account_name or "").strip() or (str(b.account_no or "").strip()) or (b.bank_name or "").strip()
                models.Transaction.objects.filter(bank_account_id=b.account_id).update(bank_display_name=label)
        except Exception:
            pass
        deleted, _ = qs.delete()
        return Response({"deleted": deleted, "ids": ids})

    def destroy(self, request, *args, **kwargs):
        # Before deleting, snapshot bank label into transactions for historical display
        instance = self.get_object()
        try:
            label = (instance.account_name or "").strip() or (str(instance.account_no or "").strip()) or (instance.bank_name or "").strip()
            models.Transaction.objects.filter(bank_account_id=instance.account_id).update(bank_display_name=label)
        except Exception:
            pass
        return super().destroy(request, *args, **kwargs)


@method_decorator(has_permission('view_contractors'), name='list')
@method_decorator(has_permission('add_contractors'), name='create')
@method_decorator(has_permission('edit_contractors'), name='update')
@method_decorator(has_permission('edit_contractors'), name='partial_update')
@method_decorator(has_permission('delete_contractors'), name='destroy')
@method_decorator(has_permission('delete_contractors'), name='bulk_delete')
class ContractorViewSet(viewsets.ModelViewSet):
    queryset = models.Contractor.objects.all().order_by("contractor_id")
    serializer_class = serializers.ContractorSerializer

    def destroy(self, request, *args, **kwargs):
        # Before deleting, snapshot contractor names into transactions for historical display
        instance = self.get_object()
        try:
            models.Transaction.objects.filter(contractor_id=instance.contractor_id).update(
                contractor_display_name=instance.contractor_name
            )
        except Exception:
            pass
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=["get"])
    def export(self, request):
        file_path = export_contractors_excel()
        return Response({"file": file_path})

    @action(detail=True, methods=["get"], url_path="export-pdf")
    def export_pdf(self, request, pk=None):
        file_path = export_contractor_pdf(int(pk))
        return Response({"file": file_path})

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        ids = request.data.get("ids") or []
        if isinstance(ids, str):
            ids = [i for i in ids.replace(" ", "").split(",") if i]
        try:
            ids = [int(i) for i in ids]
        except Exception:
            return Response({"detail": "Invalid ids payload"}, status=status.HTTP_400_BAD_REQUEST)
        qs = models.Contractor.objects.filter(contractor_id__in=ids)
        # Snapshot contractor names into related transactions before deletion
        try:
            for c in qs:
                models.Transaction.objects.filter(contractor_id=c.contractor_id).update(
                    contractor_display_name=c.contractor_name
                )
        except Exception:
            pass
        deleted, _ = qs.delete()
        return Response({"deleted": deleted, "ids": ids})


@method_decorator(has_permission('view_transactions'), name='list')
@method_decorator(has_permission('add_transactions'), name='create')
@method_decorator(has_permission('edit_transactions'), name='update')
@method_decorator(has_permission('edit_transactions'), name='partial_update')
@method_decorator(has_permission('delete_transactions'), name='destroy')
@method_decorator(has_permission('delete_transactions'), name='bulk_delete')
class TransactionViewSet(viewsets.ModelViewSet):
    queryset = models.Transaction.objects.all().order_by("-transaction_date", "-transaction_id")
    serializer_class = serializers.TransactionSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            self.perform_create(serializer)
        except Exception as exc:
            # Fallback: if FK constraint fails, try creating with null FKs to keep entry saved
            msg = str(exc)
            try:
                data = dict(serializer.validated_data)
                data.pop("bank_account", None)
                data.pop("contractor", None)
                fallback = serializers.TransactionSerializer(data=data)
                fallback.is_valid(raise_exception=True)
                self.perform_create(fallback)
                headers = self.get_success_headers(fallback.data)
                return Response(fallback.data, status=status.HTTP_201_CREATED, headers=headers)
            except Exception:
                # Convert unexpected DB errors to a clear 400 response
                return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        ids = request.data.get("ids") or []
        if isinstance(ids, str):
            ids = [i for i in ids.replace(" ", "").split(",") if i]
        try:
            ids = [int(i) for i in ids]
        except Exception:
            return Response({"detail": "Invalid ids payload"}, status=status.HTTP_400_BAD_REQUEST)
        qs = models.Transaction.objects.filter(transaction_id__in=ids)
        deleted, _ = qs.delete()
        return Response({"deleted": deleted, "ids": ids})

    def get_queryset(self):
        qs = super().get_queryset()
        bank = self.request.query_params.get("bank")
        contractor = self.request.query_params.get("contractor")
        tx_type = self.request.query_params.get("type")
        start = self.request.query_params.get("start")
        end = self.request.query_params.get("end")
        if bank:
            qs = qs.filter(bank_account_id=bank)
        if contractor:
            qs = qs.filter(contractor_id=contractor)
        if tx_type in ("credit", "debit"):
            qs = qs.filter(tx_type=tx_type)
        if start:
            qs = qs.filter(transaction_date__gte=start)
        if end:
            qs = qs.filter(transaction_date__lte=end)
        return qs


@method_decorator(has_permission('view_reports'), name='get')
class ReportsView(views.APIView):
    # Method: ReportsView.get
    def get(self, request):
        report_type = request.query_params.get("type", "profit-loss")
        fmt = request.query_params.get("format", "pdf")
        start = request.query_params.get("start")
        end = request.query_params.get("end")
        bank_id = request.query_params.get("bank")
        contractor_id = request.query_params.get("contractor")
        scope = request.query_params.get("scope", "both")
        snapshot_mode = request.query_params.get("snapshot")  # NEW

        # Build queryset filters
        qs = models.Transaction.objects.all()
        if start:
            qs = qs.filter(transaction_date__gte=start)
        if end:
            qs = qs.filter(transaction_date__lte=end)
        if bank_id:
            qs_bank = qs.filter(bank_account_id=bank_id)
        else:
            qs_bank = qs
        if contractor_id:
            qs_contractor = qs.filter(contractor_id=contractor_id)
        else:
            qs_contractor = qs

        # Helper to sum amounts by type
        def _sum(qs_local, tx_type: str) -> float:
            from decimal import Decimal

            total = Decimal("0")
            for t in qs_local.filter(tx_type=tx_type):
                if t.amount is not None:
                    total += Decimal(str(t.amount))
            return float(total)

        # Decide exporter and summary
        if report_type in ("profit", "loss", "profit-loss"):
            file_path = export_profit_loss_pdf(start, end, scope) if fmt == "pdf" else export_contractors_excel()
            summary = {
                "credit": _sum(qs, models.Transaction.CREDIT),
                "debit": _sum(qs, models.Transaction.DEBIT),
                "net": _sum(qs, models.Transaction.CREDIT) - _sum(qs, models.Transaction.DEBIT),
            }
        elif report_type in ("bank", "bank-wise"):
            bid = int(bank_id) if bank_id else None
            file_path = export_bank_wise_pdf(start, end, bid, scope=scope) if fmt == "pdf" else export_contractors_excel()
            summary = {
                "credit": _sum(qs_bank, models.Transaction.CREDIT),
                "debit": _sum(qs_bank, models.Transaction.DEBIT),
                "net": _sum(qs_bank, models.Transaction.CREDIT) - _sum(qs_bank, models.Transaction.DEBIT),
            }
        elif report_type in ("contractor", "contractor-wise"):
            cid = int(contractor_id) if contractor_id else None
            file_path = export_contractor_wise_pdf(start, end, cid, scope=scope) if fmt == "pdf" else export_contractors_excel()
            summary = {
                "credit": _sum(qs_contractor, models.Transaction.CREDIT),
                "debit": _sum(qs_contractor, models.Transaction.DEBIT),
                "net": _sum(qs_contractor, models.Transaction.CREDIT) - _sum(qs_contractor, models.Transaction.DEBIT),
            }
        elif report_type in ("register", "transaction-register", "नगद", "नगद-वहिवाट"):  # NEW
            file_path = export_transaction_register_pdf(start, end, scope=scope) if fmt == "pdf" else export_contractors_excel()
            summary = {
                "credit": _sum(qs, models.Transaction.CREDIT),
                "debit": _sum(qs, models.Transaction.DEBIT),
                "net": _sum(qs, models.Transaction.CREDIT) - _sum(qs, models.Transaction.DEBIT),
            }
        else:
            file_path = export_report_pdf("unknown") if fmt == "pdf" else export_contractors_excel()
            summary = {}

        # Persist daily snapshot when requested
        if snapshot_mode in ("daily", "true", "1"):
            from decimal import Decimal
            from datetime import date as _date

            # Determine the day: prefer 'end', fallback to 'start', else today
            try:
                day_obj = _date.fromisoformat(end or start or _date.today().isoformat())
            except Exception:
                day_obj = _date.today()

            base_qs = models.Transaction.objects.all()
            if bank_id:
                base_qs = base_qs.filter(bank_account_id=bank_id)
            if contractor_id:
                base_qs = base_qs.filter(contractor_id=contractor_id)

            def _sum_dec(qs_local, tx_type: str) -> Decimal:
                total = Decimal("0")
                for t in qs_local.filter(tx_type=tx_type):
                    if t.amount is not None:
                        total += Decimal(str(t.amount))
                return total

            prev_qs = base_qs.filter(transaction_date__lt=day_obj)
            day_qs = base_qs.filter(transaction_date=day_obj)

            opening = _sum_dec(prev_qs, models.Transaction.CREDIT) - _sum_dec(prev_qs, models.Transaction.DEBIT)
            day_credit = _sum_dec(day_qs, models.Transaction.CREDIT)
            day_debit = _sum_dec(day_qs, models.Transaction.DEBIT)
            day_net = day_credit - day_debit
            closing = opening + day_net

            # Upsert the snapshot keyed by date/scope/bank/contractor
            models.BalanceSnapshot.objects.update_or_create(
                as_of_date=day_obj,
                scope=scope or "both",
                bank_account_id=int(bank_id) if bank_id else None,
                contractor_id=int(contractor_id) if contractor_id else None,
                defaults={
                    "opening_balance": opening,
                    "total_credit": day_credit,
                    "total_debit": day_debit,
                    "net": day_net,
                    "closing_balance": closing,
                },
            )

        return Response({
            "file": file_path,
            "type": report_type,
            "format": fmt,
            "start": start,
            "end": end,
            "bank": bank_id,
            "contractor": contractor_id,
            "scope": scope,
            "summary": summary,
        })


class BackupView(views.APIView):
    def post(self, request):
        action = request.data.get("action", "backup")
        if action == "backup":
            # Require backup_data permission for create backup
            from .decorators import _user_has_permission
            if not _user_has_permission(request.user, 'backup_data'):
                return Response({"error": "Access Denied", "message": "You do not have permission to create backup."}, status=status.HTTP_403_FORBIDDEN)
            file_path = create_backup()
            return Response({"file": file_path})
        if action == "restore":
            # Require restore_data permission for restore
            from .decorators import _user_has_permission
            if not _user_has_permission(request.user, 'restore_data'):
                return Response({"error": "Access Denied", "message": "You do not have permission to restore."}, status=status.HTTP_403_FORBIDDEN)
            file_path = request.data.get("file")
            try:
                restore_backup(file_path)
            except FileNotFoundError:
                return Response({"detail": "Backup file not found"}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            return Response({"restored": True})
        return Response({"detail": "Invalid action"}, status=status.HTTP_400_BAD_REQUEST)


class SettingsImagePathView(views.APIView):
    def get(self, request):
        s = models.Setting.objects.order_by("id").first()
        return Response({"image_path": (s.image_path if s and s.image_path else "")})


@method_decorator(login_required, name='dispatch')
class AccessDeniedView(views.APIView):
    """View to display access denied page"""
    
    def get(self, request):
        return render(request, 'app/access_denied.html')


