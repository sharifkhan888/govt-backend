from django.db import migrations, models


def remap_roles_forward(apps, schema_editor):
    User = apps.get_model('app', 'User')
    # Old mapping: 1=Admin, 2=Clerk, 3=Viewer
    # New mapping: 1=Chief Officer, 2=Accountant Officer, 3=Auditor, 4=Clerk
    # Remap: 2 (old Clerk) -> 4 (new Clerk); 3 (Viewer) -> 3 (Auditor)
    User.objects.filter(role=2).update(role=4)
    User.objects.filter(role=3).update(role=3)


def remap_roles_backward(apps, schema_editor):
    User = apps.get_model('app', 'User')
    # Reverse: 4 (new Clerk) -> 2 (old Clerk); 3 (Auditor) -> 3 (Viewer)
    User.objects.filter(role=4).update(role=2)
    User.objects.filter(role=3).update(role=3)


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.PositiveSmallIntegerField(
                choices=((1, 'Chief Officer (Master Admin)'), (2, 'Accountant Officer'), (3, 'Auditor'), (4, 'Clerk')),
                default=4,
            ),
        ),
        migrations.RunPython(remap_roles_forward, remap_roles_backward),
    ]