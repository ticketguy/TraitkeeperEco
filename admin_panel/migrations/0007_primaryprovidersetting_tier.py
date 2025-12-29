# Generated manually for tier field addition

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admin_panel', '0006_delete_adminnotification'),
    ]

    operations = [
        migrations.AddField(
            model_name='primaryprovidersetting',
            name='tier',
            field=models.CharField(
                choices=[
                    ('free', 'Free'),
                    ('developer', 'Developer'),
                    ('professional', 'Professional'),
                    ('business', 'Business'),
                    ('build', 'Build'),
                    ('scale', 'Scale'),
                    ('default', 'Default')
                ],
                default='free',
                help_text='Subscription tier for quota and rate limiting',
                max_length=20
            ),
        ),
    ]
