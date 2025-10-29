# Notifications App

## Overview

Handles web push notifications and real-time alerts for users. Supports privacy-preserving notifications for marketplace events.

## Purpose

- **Web push notifications** - Browser notifications via Service Worker
- **Privacy-preserving alerts** - Notify without revealing sensitive data
- **Event-driven notifications** - Auto-notify on bids, sales, auctions

## Features

### Notification Types

1. **Marketplace Events**
   - New bid received (amount hidden until owner views)
   - Auction outbid
   - Auction won

2. **Collection Events**
   - Floor price changes
   - Sweep detected
   - High-profile transfer

3. **System Events**
   - Vitality score updates
   - Featured collection status

## Privacy Design

- Bid amounts **not** included in push notifications
- Users must visit app to see details
- Encrypted notification payloads (Arcium integration planned)

## Configuration

Uses `django-webpush` for VAPID key management.

**Settings:**

```python
WEBPUSH_SETTINGS = {
    "VAPID_PUBLIC_KEY": "...",
    "VAPID_PRIVATE_KEY": "...",
    "VAPID_ADMIN_EMAIL": "admin@example.com"
}
```

## TODO

- [ ] Implement encrypted notification content
- [ ] Add notification preferences per user
- [ ] Create notification history/inbox
- [ ] Add email notifications
