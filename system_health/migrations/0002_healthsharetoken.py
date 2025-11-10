# Generated manually for HealthShareToken model

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('system_health', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='HealthShareToken',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token', models.CharField(db_index=True, max_length=64, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField()),
                ('include_performance', models.BooleanField(default=True, help_text='Include CPU, Memory, Disk stats')),
                ('include_services', models.BooleanField(default=True, help_text='Include service status')),
                ('include_marketplace', models.BooleanField(default=True, help_text='Include marketplace stats')),
                ('include_uptime', models.BooleanField(default=True, help_text='Include system uptime')),
                ('view_count', models.IntegerField(default=0)),
                ('last_accessed', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'verbose_name': 'Health Share Token',
                'verbose_name_plural': 'Health Share Tokens',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='healthsharetoken',
            index=models.Index(fields=['token', 'expires_at'], name='system_heal_token_8f5c3d_idx'),
        ),
    ]
