# Admin Panel App

## Overview

Custom admin interface with separate AdminUser model for platform administrators. Provides monitoring dashboards, collection management, and system health oversight.

## Purpose

- **Separate admin authentication** - AdminUser model independent of regular users
- **Collection management** - Approve submissions, set featured status
- **System monitoring** - View indexer status, failed transactions
- **Analytics oversight** - Monitor calculation jobs, data quality

## Models

### AdminUser

Separate admin user model (not CustomUser).

**Key Fields:**

- `username` - Admin username
- `email` - Admin email
- `role` - Admin role (super_admin, moderator, analyst)
- `permissions` - JSON of specific permissions

## Features

- Custom admin dashboard
- Collection approval workflow
- Pending submission review
- Failed transaction viewer
- Unknown discriminator approver
- System health monitoring

## Access Control

- Super admins: Full access
- Moderators: Collection management only
- Analysts: Read-only analytics access

## TODO

- [ ] Add audit logging for admin actions
- [ ] Implement role-based dashboards
- [ ] Add bulk collection operations
