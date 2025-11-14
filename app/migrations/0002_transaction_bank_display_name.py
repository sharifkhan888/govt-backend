from django.db import migrations, models


def _backfill_bank_display_name(apps, schema_editor):
    Transaction = apps.get_model('app', 'Transaction')
    BankAccount = apps.get_model('app', 'BankAccount')
    for tx in Transaction.objects.all():
        try:
            if tx.bank_account_id and not (tx.bank_display_name or '').strip():
                b = BankAccount.objects.filter(pk=tx.bank_account_id).first()
                if b:
                    label = (b.account_name or '').strip() or (str(b.account_no or '').strip()) or (b.bank_name or '').strip()
                    tx.bank_display_name = label
                    tx.save(update_fields=['bank_display_name'])
        except Exception:
            pass


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='transaction',
            name='bank_display_name',
            field=models.CharField(max_length=250, blank=True),
        ),
        migrations.RunPython(_backfill_bank_display_name, migrations.RunPython.noop),
    ]