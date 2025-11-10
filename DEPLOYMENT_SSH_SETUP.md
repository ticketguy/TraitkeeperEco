# Production Deployment SSH Setup Guide

## Problem

Your GitHub Actions deployment is failing with:
```
ssh.ParsePrivateKey: ssh: no key found
ssh: handshake failed: ssh: unable to authenticate
```

This means the SSH private key is not properly configured in GitHub repository secrets.

---

## Solution: Configure SSH Authentication

### Step 1: Generate SSH Key Pair (if you don't have one)

On your **local machine** or **production server**, run:

```bash
# Generate a new SSH key pair specifically for GitHub Actions deployment
ssh-keygen -t ed25519 -C "github-actions-deployment" -f ~/.ssh/github_actions_deploy

# This creates two files:
# - github_actions_deploy (private key) - DO NOT SHARE
# - github_actions_deploy.pub (public key) - Safe to share
```

**Important**:
- When prompted for a passphrase, press Enter (leave it empty) - GitHub Actions cannot use password-protected keys
- Keep the private key secure and never commit it to your repository

---

### Step 2: Add Public Key to Production Server

Copy the **public key** to your production server's authorized keys:

```bash
# On your local machine, copy the public key content:
cat ~/.ssh/github_actions_deploy.pub

# Output will look like:
# ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAbCdEfGhIjKlMnOpQrStUvWxYz github-actions-deployment
```

Then on your **production server**, add this public key:

```bash
# SSH into your production server
ssh user@your-production-server.com

# Add the public key to authorized_keys
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAbCdEfGhIjKlMnOpQrStUvWxYz github-actions-deployment" >> ~/.ssh/authorized_keys

# Set proper permissions
chmod 600 ~/.ssh/authorized_keys
chmod 700 ~/.ssh
```

---

### Step 3: Add Secrets to GitHub Repository

Go to your GitHub repository settings and add these secrets:

**Navigate to**: `Settings` → `Secrets and variables` → `Actions` → `New repository secret`

Add the following secrets:

#### 1. `PRODUCTION_SSH_KEY`
```bash
# On your local machine, copy the PRIVATE key:
cat ~/.ssh/github_actions_deploy

# Copy the ENTIRE output including:
# -----BEGIN OPENSSH PRIVATE KEY-----
# (all the lines)
# -----END OPENSSH PRIVATE KEY-----
```

**Paste this entire content** (including BEGIN/END lines) into the secret value.

#### 2. `PRODUCTION_HOST`
Your production server hostname or IP address:
```
your-server.com
# OR
192.168.1.100
```

#### 3. `PRODUCTION_USER`
The SSH username on your production server:
```
user
# OR whatever username you use to SSH into the server
```

#### 4. `PRODUCTION_SSH_PORT` (Optional)
Only add this if you use a non-standard SSH port:
```
22  # Default - can omit this secret if using port 22
# OR
2222  # If you changed SSH to a different port
```

---

### Step 4: Verify Configuration

#### Test SSH connection locally first:

```bash
# Test that you can SSH with the new key
ssh -i ~/.ssh/github_actions_deploy user@your-production-server.com

# If successful, you should be logged into your server
```

#### Check GitHub Secrets are set:

1. Go to `Settings` → `Secrets and variables` → `Actions`
2. You should see:
   - ✅ `PRODUCTION_SSH_KEY`
   - ✅ `PRODUCTION_HOST`
   - ✅ `PRODUCTION_USER`
   - ✅ `PRODUCTION_SSH_PORT` (optional)

---

### Step 5: Trigger Deployment

Once secrets are configured, trigger a deployment:

**Option A: Push to main/production branch**
```bash
git push origin main
```

**Option B: Manual trigger**
1. Go to `Actions` tab in GitHub
2. Select "Production Deployment" workflow
3. Click "Run workflow"
4. Select branch and click "Run workflow"

---

## Troubleshooting

### Error: "Permission denied (publickey)"

**Cause**: Public key not added to production server

**Solution**:
```bash
# On production server, verify authorized_keys exists:
ls -la ~/.ssh/authorized_keys

# Verify permissions:
chmod 600 ~/.ssh/authorized_keys
chmod 700 ~/.ssh
```

### Error: "ssh: no key found"

**Cause**: Private key not properly added to GitHub secrets

**Solution**:
- Verify `PRODUCTION_SSH_KEY` secret contains the **entire** private key
- Must include `-----BEGIN OPENSSH PRIVATE KEY-----` and `-----END OPENSSH PRIVATE KEY-----`
- No extra spaces or line breaks

### Error: "Host key verification failed"

**Cause**: Server not in known_hosts

**Solution**: This shouldn't happen with the current workflow, but if it does:
```yaml
# Add to SSH action in workflow:
script: |
  export TERM=xterm
  ssh-keyscan -H ${{ secrets.PRODUCTION_HOST }} >> ~/.ssh/known_hosts
```

### Still not working?

**Test the SSH key manually**:
```bash
# Copy private key to a test file
cat ~/.ssh/github_actions_deploy

# Try connecting
ssh -i ~/.ssh/github_actions_deploy -v user@production-server.com

# The -v flag shows verbose output for debugging
```

---

## Security Best Practices

1. ✅ **Use dedicated deployment key** - Don't reuse your personal SSH key
2. ✅ **No passphrase** - GitHub Actions can't handle password-protected keys
3. ✅ **Restrict key permissions** - Use `chmod 600` on private key files
4. ✅ **Never commit private keys** - Always use GitHub Secrets
5. ✅ **Rotate keys periodically** - Update deployment keys every 6-12 months
6. ✅ **Use ed25519 keys** - More secure and faster than RSA

---

## Quick Reference

### File Locations

**Local Machine:**
- Private key: `~/.ssh/github_actions_deploy`
- Public key: `~/.ssh/github_actions_deploy.pub`

**Production Server:**
- Authorized keys: `~/.ssh/authorized_keys`

### GitHub Secrets Required

| Secret Name | Description | Example |
|------------|-------------|---------|
| `PRODUCTION_SSH_KEY` | Private key content | `-----BEGIN OPENSSH PRIVATE KEY-----...` |
| `PRODUCTION_HOST` | Server hostname/IP | `server.example.com` |
| `PRODUCTION_USER` | SSH username | `user` |
| `PRODUCTION_SSH_PORT` | SSH port (optional) | `22` |

---

## Workflow File Reference

The deployment workflow at `.github/workflows/deploy-production.yml:250-256` uses:

```yaml
- name: Deploy to production server
  uses: appleboy/ssh-action@v1.0.0
  with:
    host: ${{ secrets.PRODUCTION_HOST }}
    username: ${{ secrets.PRODUCTION_USER }}
    key: ${{ secrets.PRODUCTION_SSH_KEY }}
    port: ${{ secrets.PRODUCTION_SSH_PORT || 22 }}
```

This requires all the secrets listed above to be properly configured.

---

**After configuring these secrets, your deployment should work!** 🚀
