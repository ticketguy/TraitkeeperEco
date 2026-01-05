# Remaining Profile & Mobile Issues

## Issues to Fix:

### 1. Logout Functionality
- **Problem**: Logout button shows sign-in message instead of logging out
- **Location**: wallet-connection.js disconnectWalletGlobal function
- **Debug**: Check console logs added (🔴 LOGOUT prefix)

### 2. Notification System  
- **Problem**: Notification icon doesn't show tab in mobile, leads to 500 error
- **Tasks**:
  - Fix notification URL/view causing 500 error
  - Make notification dropdown work in mobile
  - Ensure notification pipeline is active

### 3. Console Errors
- NFT Detail Modal element not found
- Duplicate ID: #notification-settings-form (2 elements)
- Connect wallet button retry timeout message
- WebSocket connection failures (expected if not configured)

### 4. Market Stats Carousel
- **Problem**: Stats overlapping in mobile, then correcting
- **Likely cause**: CSS/JS loading timing issue
- **Solution**: Add proper loading state or fix initial styles

### 5. Settings Page Redesign
- Match modern profile page aesthetic
- Add stat cards, better spacing
- Improve mobile responsiveness

### 6. Index Page Loading State
- **Problem**: Page looks correct when loading, changes after load completes
- **Solution**: Investigate what's changing after page load

## Completed:
✅ Quest page 500 error (missing template tag)
✅ Mobile tabs (icons only)
✅ Join date spacing
✅ Footer alignment in mobile

## Next Steps:
1. Debug logout with console logs
2. Fix notification 500 error
3. Remove duplicate IDs
4. Fix market carousel timing
5. Redesign settings page
