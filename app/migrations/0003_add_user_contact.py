from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0002_update_role_choices'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='contact',
            field=models.CharField(max_length=50, blank=True),
        ),
    ]