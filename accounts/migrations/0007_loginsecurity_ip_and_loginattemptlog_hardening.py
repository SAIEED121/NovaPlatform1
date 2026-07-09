from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_loginsecurity_loginattemptlog"),
    ]

    operations = [
        migrations.AddField(
            model_name="loginsecurity",
            name="last_failed_ip",
            field=models.GenericIPAddressField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="loginsecurity",
            name="last_successful_ip",
            field=models.GenericIPAddressField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="loginattemptlog",
            name="browser",
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name="loginattemptlog",
            name="operating_system",
            field=models.CharField(blank=True, max_length=128),
        ),
    ]
