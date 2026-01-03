# Generated manually for custodial wallet support

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('wallet', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='CustodialWallet',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('encrypted_private_key', models.TextField(help_text='AES-256 encrypted private key')),
                ('encryption_version', models.CharField(default='v1', help_text='Encryption scheme version for future upgrades', max_length=10)),
                ('salt', models.CharField(help_text='Salt for PBKDF2 key derivation', max_length=64)),
                ('is_exported', models.BooleanField(default=False, help_text='Has the user exported the private key/seed phrase?')),
                ('exported_at', models.DateTimeField(blank=True, help_text='When was the private key first exported', null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('wallet_profile', models.OneToOneField(help_text='Link to the WalletProfile', on_delete=django.db.models.deletion.CASCADE, related_name='custodial_data', to='wallet.walletprofile')),
            ],
            options={
                'verbose_name': 'Custodial Wallet',
                'verbose_name_plural': 'Custodial Wallets',
            },
        ),
        migrations.AddIndex(
            model_name='custodialwallet',
            index=models.Index(fields=['wallet_profile'], name='wallet_cust_wallet__idx'),
        ),
    ]
