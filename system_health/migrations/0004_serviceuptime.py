# Generated migration for ServiceUptime model

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('system_health', '0003_rename_system_heal_token_8f5c3d_idx_system_heal_token_866b2b_idx'),
    ]

    operations = [
        migrations.CreateModel(
            name='ServiceUptime',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('service_name', models.CharField(choices=[('main', 'Web Server'), ('indexer-live', 'Live Indexer'), ('indexer-scheduled', 'Scheduled Indexer'), ('vitality-analytics', 'Vitality Analytics'), ('health', 'Health Monitor'), ('postgres', 'PostgreSQL'), ('redis', 'Redis Cache'), ('config-listener', 'Config Listener')], max_length=50)),
                ('date', models.DateField(db_index=True)),
                ('uptime_percentage', models.DecimalField(decimal_places=2, default=0, help_text='Daily uptime percentage (0-100)', max_digits=5)),
                ('total_checks', models.IntegerField(default=0, help_text='Total health checks performed')),
                ('successful_checks', models.IntegerField(default=0, help_text='Number of successful checks')),
                ('failed_checks', models.IntegerField(default=0, help_text='Number of failed checks')),
                ('avg_response_time_ms', models.FloatField(blank=True, help_text='Average response time in milliseconds', null=True)),
                ('downtime_minutes', models.FloatField(default=0, help_text='Total downtime in minutes')),
                ('incidents_count', models.IntegerField(default=0, help_text='Number of downtime incidents')),
                ('metadata', models.JSONField(default=dict, help_text='Additional uptime metrics')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Service Uptime',
                'verbose_name_plural': 'Service Uptime Records',
                'ordering': ['-date', 'service_name'],
                'indexes': [
                    models.Index(fields=['service_name', '-date'], name='system_heal_service_6fc2a0_idx'),
                    models.Index(fields=['-date'], name='system_heal_date_c7d421_idx'),
                    models.Index(fields=['uptime_percentage'], name='system_heal_uptime__e42b18_idx'),
                ],
                'unique_together': {('service_name', 'date')},
            },
        ),
    ]
