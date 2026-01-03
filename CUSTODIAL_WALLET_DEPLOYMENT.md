# Custodial Wallet System - Deployment Guide

## Overview
This deployment adds a secure custodial wallet system for email/password signups with AES-256 encryption.

## Features Implemented
1. ✅ Auto-create encrypted wallet on email signup
2. ✅ Username change system with 60-day rate limit
3. ✅ Wallet export UI with password verification (2FA)
4. ✅ Quest link in profile navigation
5. ✅ Fixed header to show username and proper avatars

## Deployment Steps

### 1. Pull Latest Changes
```bash
cd /path/to/traitkeeper
git pull origin main
```

### 2. Install Dependencies
```bash
# Ensure cryptography and mnemonic packages are installed
pip install cryptography==43.0.3 mnemonic==0.21
```

### 3. Run Migrations
```bash
python manage.py migrate profiles  # Username change history
python manage.py migrate wallet    # Custodial wallet tables
```

Expected migrations:
- `profiles.0003_add_username_change_history` - Adds UsernameChangeHistory model
- `wallet.0002_custodial_wallet` - Adds CustodialWallet model

### 4. Restart Application
```bash
# Restart your Django application server
# Example for systemd:
sudo systemctl restart traitkeeper

# Or for Docker:
docker-compose restart web

# Or for gunicorn:
sudo systemctl restart gunicorn
```

### 5. Verify Deployment

#### Test Username Change:
1. Log in to your account
2. Go to Settings → Account
3. Click "Change Username"
4. Verify 60-day cooldown works

#### Test Custodial Wallet:
1. Sign up with a new email/password account
2. Verify wallet is auto-created
3. Go to Settings → Wallets
4. Should see a "Custodial" badge on the wallet
5. Click "Export Keys"
6. Enter password
7. Verify seed phrase and private key display

#### Test Wallet Export:
1. Navigate to Settings → Wallets
2. Click "Export Keys" on a custodial wallet
3. Enter account password
4. Verify private key displays correctly
5. Test copy-to-clipboard functionality

## Database Schema Changes

### UsernameChangeHistory Table
```sql
CREATE TABLE profiles_usernamechangehistory (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    old_username VARCHAR(150) NOT NULL,
    new_username VARCHAR(150) NOT NULL,
    changed_at DATETIME NOT NULL,
    ip_address VARCHAR(39),
    reason VARCHAR(200),
    FOREIGN KEY (user_id) REFERENCES auth_user(id)
);
CREATE INDEX idx_user_changed_at ON profiles_usernamechangehistory(user_id, changed_at);
```

### CustodialWallet Table
```sql
CREATE TABLE wallet_custodialwallet (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    wallet_profile_id BIGINT NOT NULL UNIQUE,
    encrypted_private_key TEXT NOT NULL,
    encryption_version VARCHAR(10) NOT NULL DEFAULT 'v1',
    salt VARCHAR(64) NOT NULL,
    is_exported BOOLEAN NOT NULL DEFAULT FALSE,
    exported_at DATETIME,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY (wallet_profile_id) REFERENCES wallet_walletprofile(id)
);
```

## Security Features

### Encryption Details:
- **Algorithm**: AES-256-CBC
- **Key Derivation**: PBKDF2-HMAC-SHA256 (600,000 iterations)
- **Salt**: 32 random bytes per wallet
- **IV**: 16 random bytes per encryption
- **Password**: User's account password (hashed separately for login)

### Access Control:
- Private key decryption requires password confirmation
- Seed phrase shown only once after signup (stored in session)
- Export tracking with timestamp
- Only wallet owner can export their keys

## File Changes

### New Files:
- `wallet/models.py` - Added CustodialWallet model
- `wallet/services/encryption.py` - WalletEncryptionService
- `wallet/services/solana_wallet.py` - SolanaWalletService
- `wallet/migrations/0002_custodial_wallet.py`
- `profiles/models.py` - Added UsernameChangeHistory model
- `profiles/forms.py` - Added UsernameChangeForm
- `profiles/migrations/0003_add_username_change_history.py`
- `templates/wallet/export_wallet.html`
- `templates/profile/change_username.html`

### Modified Files:
- `wallet/views.py` - Added export_wallet_view, auto-create wallet on signup
- `wallet/urls.py` - Added export wallet route
- `profiles/views.py` - Added change_username_view
- `profiles/urls.py` - Added username change route
- `templates/profile/settings.html` - Added username change section, custodial badge
- `templates/profile/user_profile.html` - Added Quest link
- `templates/index page/base.html` - Fixed header to show username

## Environment Variables
No new environment variables required. Uses existing Django SECRET_KEY for password hashing.

## Rollback Plan
If issues occur:
```bash
# Rollback migrations
python manage.py migrate profiles 0002
python manage.py migrate wallet 0001

# Rollback code
git revert 18beb66  # Wallet export UI
git revert 0406f1f  # Auto-create wallet
git revert c588597  # Custodial wallet system
git push origin main
```

## Monitoring

### Check for Errors:
```bash
# Check application logs
tail -f /var/log/traitkeeper/error.log

# Check for wallet creation failures
grep "❌ Failed to create custodial wallet" /var/log/traitkeeper/app.log

# Check for decryption errors
grep "Error decrypting wallet" /var/log/traitkeeper/app.log
```

### Database Checks:
```sql
-- Count custodial wallets
SELECT COUNT(*) FROM wallet_custodialwallet;

-- Check recent username changes
SELECT * FROM profiles_usernamechangehistory ORDER BY changed_at DESC LIMIT 10;

-- Find exported wallets
SELECT * FROM wallet_custodialwallet WHERE is_exported = TRUE;
```

## Support & Troubleshooting

### Issue: Wallet Creation Fails on Signup
**Symptom**: New users don't get a wallet
**Solution**: Check that `cryptography` and `mnemonic` packages are installed

### Issue: Password Verification Fails
**Symptom**: Can't export wallet even with correct password
**Solution**: Verify user's password hash is correct in auth_user table

### Issue: Seed Phrase Not Showing
**Symptom**: Only private key shows, no seed phrase
**Solution**: Normal - seed phrase only available immediately after signup (session-based)

## Next Steps (Future Enhancements)
- [ ] Add TOTP 2FA for wallet export (replace password-only verification)
- [ ] Allow password creation for wallet-only users
- [ ] Implement wallet transfer to external wallet
- [ ] Add biometric authentication (WebAuthn)
- [ ] Add 6-digit PIN system

## Commits Included
1. `c588597` - feat: Add custodial wallet system with AES-256 encryption
2. `0406f1f` - feat: Auto-create custodial wallet on email signup
3. `18beb66` - feat: Add wallet export UI with password verification
4. `13b7446` - feat: Implement username change with 60-day rate limit
5. `5cd6d0a` - feat: Add Quest link, fix header profile display

---

**Deployed**: Ready for production
**Tested**: ✅ Local testing complete
**Documentation**: Complete
