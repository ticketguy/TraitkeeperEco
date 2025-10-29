# TraitKeeper - Main Project App

## Overview

This is the **main Django project** app containing settings, URL routing, authentication backends, and global configurations.

## Purpose

- **Project settings** - All Django configuration
- **URL routing** - Root URL configuration
- **Authentication** - Custom token authentication
- **Middleware** - CORS, sessions, security
- **API configuration** - DRF and drf-spectacular setup

## Key Files

### settings.py

**All Django configuration**.

**Key Settings:**

- Database: PostgreSQL
- Cache: Redis
- Channels: Redis (WebSockets)
- Authentication: Custom token + session + allauth
- API: DRF with token auth and throttling

### urls.py

**Root URL configuration**.

Routes to:

- `/admin/` - Django admin
- `/api/` - REST API endpoints
- `/marketplace/` - Marketplace views
- `/wallet/` - Wallet authentication
- `/notifications/` - Notification endpoints

### authentication.py

**Custom authentication backends**.

**ExpiringTokenAuthentication:**

- Token-based auth for API
- Tokens expire after configured period
- Used by mobile/web clients

### permissions.py

Custom permission classes for API endpoints.

### models.py

**Custom Token model** (extends DRF token).

## Configuration

### Installed Apps

Core Django apps + Custom apps:

- nft_data
- indexer
- analytics
- marketplace
- wallet
- admin_panel
- core
- notifications
- system_health

### Authentication Backends

1. Django ModelBackend (default)
2. Allauth backend (social auth)
3. CustomAuthBackend (wallet users)
4. AdminAuthBackend (admin users)

### REST Framework

```python
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'traitkeeper.authentication.ExpiringTokenAuthentication',
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '500/hour',
    },
}
```

### Cache Configuration

**Redis-backed caching** with priority-based TTLs.

See `core/README.md` for cache manager details.

### Background Tasks

**Celery** (planned) for:

- Periodic vitality calculations
- Collection indexing
- Analytics updates



## Security Settings

- CSRF protection enabled
- XFrame options
- Secure SSL redirect (production)
- CORS configured for specific origins

