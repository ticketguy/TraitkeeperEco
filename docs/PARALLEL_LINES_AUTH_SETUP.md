# Parallel Lines Webhook Authentication Setup

## Using admin_secure for Secret Management

TraitKeeper uses the `admin_secure` app for encrypted secret storage with full audit logging. All secrets are encrypted using Fernet and have complete access tracking.

## Setup Steps

### 1. Create Encrypted Secrets in Django Admin

Navigate to: **Django Admin → Admin Secure → Encrypted Secrets → Add**

#### Option A: HMAC Secret (Recommended for Production)

- **Name:** `parallel_lines_webhook_secret`
- **Secret Type:** Webhook Secret
- **Description:** "HMAC secret for authenticating Parallel Lines webhooks"
- **Encrypted Value:** (paste your shared secret key)
- **Is Active:** ✅ True

#### Option B: API Key (Alternative)

- **Name:** `parallel_lines_api_key`
- **Secret Type:** API Token
- **Description:** "API key for Parallel Lines authentication"
- **Encrypted Value:** (paste your API key)
- **Is Active:** ✅ True

### 2. Set Master Encryption Key

The `admin_secure` app requires a master encryption key in your environment:

```bash
# Add to .env or server environment
SECRET_ENCRYPTION_KEY=your-fernet-key-here
```

**Generate a new Fernet key:**
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 3. Enable Development Mode (Optional - Testing Only)

For local development/testing, you can bypass auth:

```python
# settings.py (ONLY for local development)
PARALLEL_LINES_DEV_MODE = True  # ⚠️ NEVER enable in production!
```

---

## How Authentication Works

### Webhook Flow

```
Parallel Lines → Webhook with HMAC signature → TraitKeeper
                                                    ↓
                                         perception_service.py
                                                    ↓
                              EncryptedSecret.get_secret_value()
                                  (cached for 5 minutes)
                                                    ↓
                                    HMAC signature verification
                                                    ↓
                                     ✅ Success / ❌ Failure
                                                    ↓
                                         Logged to SecretAccessLog
```

### Security Features

1. **Fernet Encryption:** All secrets encrypted at rest in database
2. **Access Logging:** Every secret access logged with:
   - Timestamp
   - User/component
   - IP address
   - Success/failure
3. **Caching:** Secrets cached for 5 minutes to reduce database load
4. **Audit Trail:** Complete history in `SecretAccessLog` model
5. **Constant-Time Comparison:** Prevents timing attacks on HMAC verification

---

## Parallel Lines Side Setup

### HMAC Authentication (Recommended)

```python
import hmac
import hashlib
import json
import requests

def send_perception_webhook(payload):
    """Send perception data to TraitKeeper with HMAC authentication."""

    # Your shared secret (must match TraitKeeper's admin_secure.EncryptedSecret)
    secret = "your-secret-key-here"

    # Generate HMAC-SHA256 signature
    # Important: Payload must be JSON-serialized with sorted keys for consistency
    signature = hmac.new(
        secret.encode(),
        json.dumps(payload, sort_keys=True).encode(),
        hashlib.sha256
    ).hexdigest()

    # Send webhook
    response = requests.post(
        'https://traitkeeper.com/api/perception/webhook',
        json=payload,
        headers={
            'X-Parallel-Lines-Signature': signature,
            'Content-Type': 'application/json'
        }
    )

    return response
```

### API Key Authentication (Alternative)

```python
import requests

def send_perception_webhook(payload):
    """Send perception data to TraitKeeper with API key authentication."""

    response = requests.post(
        'https://traitkeeper.com/api/perception/webhook',
        json=payload,
        headers={
            'X-API-Key': 'your-api-key-here',
            'Content-Type': 'application/json'
        }
    )

    return response
```

---

## Monitoring Secret Access

### View Access Logs

Navigate to: **Django Admin → Admin Secure → Secret Access Logs**

You'll see:
- All secret decryption attempts
- User/component that accessed the secret
- Timestamp and IP address
- Success/failure status

### Check Secret Usage

Navigate to: **Django Admin → Admin Secure → Encrypted Secrets**

Each secret shows:
- **Access Count:** Total number of times decrypted
- **Last Accessed At:** When it was last used
- **Created By / Last Modified By:** Audit trail

---

## Troubleshooting

### Webhook Returns 401 Unauthorized

**Possible Causes:**
1. Secret not created in `admin_secure.EncryptedSecret`
2. Secret name mismatch (must be `parallel_lines_webhook_secret` or `parallel_lines_api_key`)
3. HMAC signature doesn't match (check secret value on both sides)
4. `SECRET_ENCRYPTION_KEY` not set in environment

**Debug Steps:**
```bash
# Check if secret exists
python manage.py shell
>>> from admin_secure.models import EncryptedSecret
>>> EncryptedSecret.objects.filter(name='parallel_lines_webhook_secret', is_active=True).exists()
True  # Should be True

# Try to decrypt (requires superuser)
>>> secret = EncryptedSecret.objects.get(name='parallel_lines_webhook_secret')
>>> from admin_panel.models import AdminUser
>>> user = AdminUser.objects.filter(is_superuser=True).first()
>>> secret.decrypt_value(user)
'your-secret-value-here'
```

### Webhook Logs Show "Secret not found"

The secret names are hardcoded in `perception_service.py`:
- `parallel_lines_webhook_secret` (for HMAC)
- `parallel_lines_api_key` (for API key)

Make sure you created the secret with **exactly** this name (case-sensitive).

### Frequent Cache Misses

Secrets are cached for 5 minutes. If you see frequent decrypt calls in `SecretAccessLog`, it means cache is not working.

**Check Redis:**
```python
from django.core.cache import cache
cache_key = 'encrypted_secret:parallel_lines_webhook_secret'
cache.get(cache_key)  # Should return value if cached
```

---

## Best Practices

1. **Use HMAC for Production:** More secure than simple API keys
2. **Rotate Secrets Regularly:** Use the "Rotate Secret" action in admin
3. **Monitor Access Logs:** Set up alerts for unusual access patterns
4. **Never Commit Secrets:** Always use environment variables + admin_secure
5. **Test in Dev Mode First:** Enable `PARALLEL_LINES_DEV_MODE` locally before production

---

**Last Updated:** January 2025
**Integration:** marketplace/perception_service.py
**Admin Location:** admin_secure/models.py:EncryptedSecret
