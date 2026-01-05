# Critical Fixes Needed

## 1. Google OAuth Fix (URGENT)
**Error**: `redirect_uri_mismatch`
**Solution**: Add this to Google Cloud Console OAuth 2.0 settings:
```
https://traitkeeper.xyz/accounts/google/login/callback/
```

**Steps**:
1. Go to Google Cloud Console
2. APIs & Services → Credentials
3. Edit OAuth 2.0 Client ID
4. Add authorized redirect URI: `https://traitkeeper.xyz/accounts/google/login/callback/`
5. Save

## 2. Logout Functionality
**Problem**: Logout button shows sign-in message instead of logging out
**Current Implementation**:
- JS calls `/wallet/disconnect/` ✅
- View calls `logout(request)` ✅
- View returns `{'status': 'success'}` ✅

**Debug Steps Taken**:
- Added extensive console logging (🔴 LOGOUT prefix)
- Need to test and check console output

**Possible Issues**:
- CSRF token mismatch
- Session not clearing
- Response not being handled correctly

## 3. Automatic Custodial Wallet Creation
**Requirement**: "abstraction focused - logging in or joining without wallets auto creates an inapp wallet for that user"

**Implementation Needed**:
1. Create post-signup signal handler
2. When user signs up (traditional or OAuth):
   - Generate Solana keypair
   - Encrypt private key
   - Create CustodialWallet record
   - Link to user's WalletProfile

**Files to Modify**:
- `wallet/signals.py` (create if doesn't exist)
- `wallet/services/custodial_service.py` (enhance)
- `wallet/models.py` (ensure proper relationships)

## 4. WebSocket Notification Errors
**Error**: `WebSocket connection to 'wss://traitkeeper.xyz/ws/notifications/' failed`

**Cause**: WebSocket server not configured or not running

**Solution Options**:
1. **Disable if not needed**: Remove WebSocket initialization from wallet-connection.js
2. **Configure Daphne**: Set up ASGI server for WebSockets
3. **Use Django Channels**: Ensure channels is properly configured

**Quick Fix** (if notifications not critical):
```javascript
// In wallet-connection.js, wrap WebSocket code:
if (window.WEBSOCKET_ENABLED) {
    initializeNotificationWebSocket();
}
```

## 5. SSE Hero Slides Error
**Error**: `GET https://traitkeeper.xyz/stream-hero-slides/ net::ERR_HTTP2_PROTOCOL_ERROR`

**Cause**: Server-Sent Events endpoint failing

**Solution**: Check `/stream-hero-slides/` view implementation

## 6. NFT Detail Modal Error
**Error**: `NFT Detail Modal element not found`

**Cause**: Modal element missing from DOM

**Solution**: Check if modal HTML exists in base.html or relevant template

## 7. Console Violations
**Errors**:
- `'message' handler took 176ms`
- `Forced reflow while executing JavaScript took 159ms`

**Impact**: Performance warnings, not critical

**Solution**: Optimize JavaScript, batch DOM operations

## Current Work Completed
✅ Quest page 500 error fixed (added missing template tag)
✅ Mobile tabs show icons only
✅ Join date spacing improved
✅ Footer mobile alignment centered
✅ Stat cards made responsive and compact
✅ Mobile profile tabs centered

## Next Steps Priority
1. **Test logout** with console logs
2. **Fix Google OAuth** redirect URI
3. **Implement auto wallet creation** for new users
4. **Disable or fix WebSocket** notifications
5. **Redesign settings page**
6. **Rename EchoSafe → Genesis Gate**
