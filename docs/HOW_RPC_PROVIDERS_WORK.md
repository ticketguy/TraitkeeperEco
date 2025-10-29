# How RPC Providers Work in TraitKeeper

### 1. Admin Panel Configuration (Database-Driven)

```
┌─────────────────────────────────────────────────┐
│         Admin Panel (Web UI)                    │
│  http://localhost:8000/admin/                   │
└─────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────┐
│    Admin Panel → Primary Provider Settings      │
│                                                  │
│  Add Provider:                                  │
│  ┌────────────────────────────────────────┐    │
│  │ Name: helius                           │    │
│  │ RPC URL: https://mainnet.helius-rpc... │    │
│  │ API Key: your-helius-api-key-here      │    │
│  │ WS URL: wss://mainnet.helius-rpc...    │    │
│  │ Is Active: ✓                           │    │
│  │ Is Primary: ✓                          │    │
│  └────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────┐
│      PostgreSQL Database                        │
│                                                  │
│  Table: admin_panel_primaryprovidersetting      │
│  ┌──────────────────────────────────────────┐  │
│  │ id  name     rpc_url     api_key  ...   │  │
│  │ 1   helius   https://... abc123   ...   │  │
│  └──────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────┐
│      APIProviderManager (Runtime)               │
│                                                  │
│  On startup:                                    │
│  1. Reads PrimaryProviderSetting from DB        │
│  2. Dynamically loads provider classes          │
│  3. Initializes HeliusProvider with API key     │
│  4. Makes RPC calls using configured provider   │
└─────────────────────────────────────────────────┘
```

---

## 📁 Where API Keys Live

### ❌ NOT Here (.env file)

```bash
# .env
HELIUS_API_KEY=xxx  # ❌ NOT USED!
```

### ✅ HERE (Admin Panel → Database)

```
Admin Panel → Primary Provider Settings → PostgreSQL
```

---

## 🔍 Code Flow

### Step 1: Admin Panel Model

**File:** `admin_panel/models.py`

```python
class PrimaryProviderSetting(models.Model):
    name = models.CharField(max_length=50, unique=True)
    rpc_url = models.URLField(max_length=200)
    api_key = models.CharField(max_length=100)  # ← API key stored here
    ws_url = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    is_primary = models.BooleanField(default=False)
```

### Step 2: APIProviderManager Loads Settings

**File:** `indexer/api_provider/api_providers.py`

```python
class APIProviderManager:
    def __init__(self):
        # Initialize providers from active settings
        providers = PrimaryProviderSetting.objects.filter(is_active=True)

        for provider_setting in providers:
            provider_name = provider_setting.name.lower()

            # Create provider instance with API key from database
            instance = HeliusProvider(
                rpc_url=provider_setting.rpc_url,
                api_key=provider_setting.api_key  # ← From database!
            )

            self.rpc_providers[provider_name] = instance
```

### Step 3: Provider Uses API Key

**File:** `indexer/api_provider/helius_provider.py`

```python
class HeliusProvider(SolanaRPCProvider):
    def __init__(self, rpc_url: str, api_key: str):
        super().__init__(rpc_url)
        self.api_key = api_key  # ← Stored for use

    async def fetch_collection_nfts(self, collection_address: str):
        url = f"{self.rpc_url}/?api-key={self.api_key}"  # ← Used here
        # Make API calls with the key
```

---

## 🎯 Why This Design?

### Benefits

1. **Dynamic Configuration** - Change API keys without redeploying
2. **Multiple Providers** - Support Helius, QuickNode, etc. simultaneously
3. **Failover** - Switch providers if one fails
4. **No Secrets in Code** - API keys in database, not version control
5. **Admin-Friendly** - Non-technical users can update keys via UI

### vs. Environment Variables

| Feature | Admin Panel | .env File |
|---------|-------------|-----------|
| Change without restart | ✅ Yes | ❌ No |
| Multiple providers | ✅ Yes | ❌ Hard |
| Failover support | ✅ Yes | ❌ No |
| User-friendly | ✅ Web UI | ❌ SSH/terminal |
| Version controlled | ❌ No (good!) | ⚠️ Risk |

---

## 🚀 How to Configure RPC Providers

### Method 1: Via Admin Panel (Recommended)

1. **Access Admin Panel:**

   ```
   http://localhost:8000/admin/
   ```

2. **Navigate to Primary Provider Settings:**

   ```
   Admin Panel → Primary Provider Settings → Add
   ```

3. **Add Helius Provider:**
   - **Name:** `helius`
   - **RPC URL:** `https://mainnet.helius-rpc.com`
   - **API Key:** `your-helius-api-key-here`
   - **WS URL:** `wss://mainnet.helius-rpc.com`
   - **Is Active:** ✓
   - **Is Primary:** ✓

4. **Save**

5. **Restart Data Service** (to reload providers):

   ```bash
   docker-compose restart data
   ```

### Method 2: Via Django Shell (For Automation)

```bash
docker-compose exec main python manage.py shell
```

```python
from admin_panel.models import PrimaryProviderSetting

# Create Helius provider
PrimaryProviderSetting.objects.create(
    name='helius',
    rpc_url='https://mainnet.helius-rpc.com',
    api_key='your-helius-api-key-here',
    ws_url='wss://mainnet.helius-rpc.com',
    is_active=True,
    is_primary=True
)

# Create QuickNode provider (backup)
PrimaryProviderSetting.objects.create(
    name='quicknode',
    rpc_url='https://your-quicknode-url.com',
    api_key='your-quicknode-api-key',
    ws_url='wss://your-quicknode-url.com',
    is_active=True,
    is_primary=False  # Secondary provider
)
```

---

## 🔄 Provider Failover

The system automatically fails over to backup providers:

```python
# If Helius fails:
APIProviderManager
  ↓ Try Helius (primary) → FAILED
  ↓ Try QuickNode (backup) → SUCCESS
  ✓ Continue with QuickNode
```

---

## 🛠️ Troubleshooting

### Issue: "No active RPC provider"

**Cause:** No provider configured in Admin Panel

**Fix:**

```bash
# Check if providers exist
docker-compose exec main python manage.py shell

>>> from admin_panel.models import PrimaryProviderSetting
>>> PrimaryProviderSetting.objects.all()
<QuerySet []>  # Empty = no providers!

# Add provider via Admin Panel (see above)
```

### Issue: "Invalid API key"

**Cause:** Wrong API key in database

**Fix:**

```bash
# Update API key
docker-compose exec main python manage.py shell

>>> from admin_panel.models import PrimaryProviderSetting
>>> provider = PrimaryProviderSetting.objects.get(name='helius')
>>> provider.api_key = 'new-correct-api-key'
>>> provider.save()

# Restart data service
docker-compose restart data
```

### Issue: API key in .env not working

**Cause:** System doesn't read API keys from .env!

**Fix:** Configure in Admin Panel instead (see above)

---

## 📊 Checking Current Configuration

### View Active Providers

```bash
docker-compose exec main python manage.py shell
```

```python
from admin_panel.models import PrimaryProviderSetting

# List all providers
for provider in PrimaryProviderSetting.objects.filter(is_active=True):
    print(f"Name: {provider.name}")
    print(f"RPC URL: {provider.rpc_url}")
    print(f"API Key: {provider.api_key[:10]}...")  # Show first 10 chars
    print(f"Primary: {provider.is_primary}")
    print("---")
```

---

## 🎓 Summary

### What You Need to Know

1. ✅ **API keys go in Admin Panel, NOT .env**
2. ✅ **Stored in PostgreSQL database**
3. ✅ **Dynamically loaded at runtime**
4. ✅ **Support multiple providers with failover**
5. ✅ **Change keys without redeploying code**

### Quick Setup

```
1. Start Docker Compose
2. Create superuser
3. Login to Admin Panel
4. Add Primary Provider Setting (with API key)
5. Restart data service
6. Add collections
7. System starts indexing!
```

---

## 🔗 Related Documentation

- **Admin Panel Guide:** [docs/ADMIN_PANEL.md](./docs/ADMIN_PANEL.md) *(to be created)*
- **Provider Architecture:** [indexer/api_provider/README.md](./indexer/api_provider/README.md)
- **Quick Start:** [QUICK_START.md](./QUICK_START.md)

