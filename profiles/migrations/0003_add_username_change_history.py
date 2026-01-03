# Generated manually for username change history tracking

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('profiles', '0002_quest_questclaim_questuserprogress_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='UsernameChangeHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('old_username', models.CharField(max_length=150)),
                ('new_username', models.CharField(max_length=150)),
                ('changed_at', models.DateTimeField(auto_now_add=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, help_text='IP address of change request', null=True)),
                ('reason', models.CharField(blank=True, help_text='Optional reason for change', max_length=200)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='username_history', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Username Change History',
                'verbose_name_plural': 'Username Change Histories',
                'ordering': ['-changed_at'],
            },
        ),
        migrations.AddIndex(
            model_name='usernamechangehistory',
            index=models.Index(fields=['user', '-changed_at'], name='profiles_us_user_id_e4f5d1_idx'),
        ),
        migrations.AddIndex(
            model_name='usernamechangehistory',
            index=models.Index(fields=['old_username'], name='profiles_us_old_use_a8b9c2_idx'),
        ),
        migrations.AddIndex(
            model_name='usernamechangehistory',
            index=models.Index(fields=['new_username'], name='profiles_us_new_use_c3d4e5_idx'),
        ),
    ]
