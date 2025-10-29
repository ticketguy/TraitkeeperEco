# Wallet App

## Overview

Handles user authentication via Solana wallet connection and social auth (Google). Manages user profiles and wallet-based sessions.

## Purpose

- **Wallet-based authentication** - Users sign in with Solana wallets
- **Social authentication** - Optional Google OAuth integration
- **User profiles** - Store user preferences and settings
- **Session management** - Handle wallet signature verification

## Models

### CustomUser

Custom user model extending Django's AbstractUser.

**Key Fields:**

- `username` - Unique username
- `email` - User email
- `wallet_address` - Connected Solana wallet (optional)
- `is_verified` - Email/wallet verification status

**Authentication Methods:**

1. **Wallet signature** - Sign message to prove wallet ownership
2. **Google OAuth** - Sign in with Google account

## Features

- Wallet connection via Phantom, Solflare, etc.
- Message signing for authentication
- Social auth integration (django-allauth)
- User profile management

## TODO

- [ ] Add multi-wallet support per user
- [ ] Implement wallet change notifications
- [ ] Add 2FA for high-value accounts
