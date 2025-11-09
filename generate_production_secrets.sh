#!/bin/bash
# ==================================================
# TraitKeeper Production Secrets Generator
# ==================================================
# This script generates all required secrets for production deployment
# Run this script and copy the output to your .env.production file
# ==================================================

set -e

echo "=================================================="
echo "TraitKeeper Production Secrets Generator"
echo "=================================================="
echo ""
echo "Generating production secrets..."
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "=================================================="
echo "1. Django SECRET_KEY"
echo "=================================================="
echo ""
SECRET_KEY=$(python3 -c "import secrets; print(''.join(secrets.choice('abcdefghijklmnopqrstuvwxyz0123456789!@#\$%^&*(-_=+)') for i in range(50)))")
echo -e "${GREEN}SECRET_KEY=$SECRET_KEY${NC}"
echo ""

echo "=================================================="
echo "2. Database Password"
echo "=================================================="
echo ""
DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
echo -e "${GREEN}POSTGRES_PASSWORD=$DB_PASSWORD${NC}"
echo ""

echo "=================================================="
echo "3. Redis Password (Optional but recommended)"
echo "=================================================="
echo ""
REDIS_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
echo -e "${GREEN}REDIS_PASSWORD=$REDIS_PASSWORD${NC}"
echo ""
echo -e "${YELLOW}Note: If using Redis password, update REDIS_URL to:${NC}"
echo "REDIS_URL=redis://:$REDIS_PASSWORD@redis:6379/0"
echo "REDIS_CHANNEL_URL=redis://:$REDIS_PASSWORD@redis:6379/1"
echo ""

echo "=================================================="
echo "4. Encryption Key (for admin_secure app)"
echo "=================================================="
echo ""
echo -e "${YELLOW}IMPORTANT: If you already have encrypted data in development,${NC}"
echo -e "${YELLOW}copy the existing SECRET_ENCRYPTION_KEY from your .env file!${NC}"
echo ""
echo -e "${BLUE}If this is a new deployment, use this new key:${NC}"
ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
echo -e "${GREEN}SECRET_ENCRYPTION_KEY=$ENCRYPTION_KEY${NC}"
echo ""

echo "=================================================="
echo "5. VAPID Keys (for Web Push Notifications)"
echo "=================================================="
echo ""
echo -e "${YELLOW}Checking for py_vapid package...${NC}"

# Check if py_vapid is installed
if python3 -c "import py_vapid" 2>/dev/null; then
    echo -e "${GREEN}✓ py_vapid is installed${NC}"
    echo ""
    echo "Generating VAPID keys..."
    echo ""

    VAPID_OUTPUT=$(python3 -c "
from py_vapid import Vapid
vapid = Vapid()
vapid.generate_keys()
print('VAPID_PUBLIC_KEY=' + str(vapid.public_key))
print('VAPID_PRIVATE_KEY=' + str(vapid.private_key))
")

    echo -e "${GREEN}$VAPID_OUTPUT${NC}"
    echo ""
else
    echo -e "${YELLOW}⚠ py_vapid is not installed${NC}"
    echo ""
    echo "To generate VAPID keys, run ONE of these commands:"
    echo ""
    echo "Option 1 (if using Docker - recommended):"
    echo "  docker-compose exec web python3 generate_vapid_keys.py"
    echo ""
    echo "Option 2 (if using Poetry locally):"
    echo "  poetry install"
    echo "  poetry run python generate_vapid_keys.py"
    echo ""
    echo "Option 3 (install py_vapid and run this script again):"
    echo "  pip install py-vapid"
    echo "  ./generate_production_secrets.sh"
    echo ""
fi

echo "=================================================="
echo "6. Summary - Copy to .env.production"
echo "=================================================="
echo ""
echo "Copy these values to your .env.production file:"
echo ""
echo "# Core Security"
echo "SECRET_KEY=$SECRET_KEY"
echo ""
echo "# Database"
echo "POSTGRES_PASSWORD=$DB_PASSWORD"
echo ""
echo "# Redis (optional)"
echo "# REDIS_PASSWORD=$REDIS_PASSWORD"
echo "# REDIS_URL=redis://:$REDIS_PASSWORD@redis:6379/0"
echo "# REDIS_CHANNEL_URL=redis://:$REDIS_PASSWORD@redis:6379/1"
echo ""
echo "# Encryption"
echo "SECRET_ENCRYPTION_KEY=$ENCRYPTION_KEY"
echo ""

if python3 -c "import py_vapid" 2>/dev/null; then
    echo "# VAPID Keys"
    echo "$VAPID_OUTPUT"
    echo ""
fi

echo "=================================================="
echo "✅ Secrets generated successfully!"
echo "=================================================="
echo ""
echo "Next steps:"
echo "1. Copy the values above to .env.production"
echo "2. Update other fields in .env.production (API keys, domain, etc.)"
echo "3. Review PRODUCTION_DEPLOYMENT.md for complete deployment guide"
echo ""
echo "⚠️  SECURITY WARNINGS:"
echo "  - Never commit .env or .env.production to git"
echo "  - Store secrets in a secure password manager"
echo "  - Rotate secrets regularly (every 90 days)"
echo "  - Use environment-specific secrets (never reuse dev secrets in prod)"
echo ""
