#!/bin/bash
# ==================================================
# TraitKeeper Production Setup Script
# ==================================================
# This script sets up SSL, Nginx, and production environment
# Run as: sudo bash setup_production.sh
# ==================================================

set -e  # Exit on any error

echo "🚀 TraitKeeper Production Setup"
echo "================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Domain configuration
DOMAIN="traitkeeper.xyz"
EMAIL="admin@traitkeeper.xyz"

# Project directory (can be overridden with environment variable or defaults to current directory parent)
PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "$0")" && pwd)}"

# Detect the user who invoked sudo (or current user if not using sudo)
DEPLOY_USER="${SUDO_USER:-$(whoami)}"

# Function to print colored output
print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ️  $1${NC}"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "Please run as root (use sudo)"
    exit 1
fi

print_info "Starting production setup for $DOMAIN..."

# ==================================================
# 1. Install Nginx
# ==================================================
print_info "Installing Nginx..."
apt-get update
apt-get install -y nginx

print_success "Nginx installed"

# ==================================================
# 2. Install Certbot for Let's Encrypt SSL
# ==================================================
print_info "Installing Certbot..."
apt-get install -y certbot python3-certbot-nginx

print_success "Certbot installed"

# ==================================================
# 3. Copy Nginx Configuration
# ==================================================
print_info "Setting up Nginx configuration..."

# Create certbot webroot directory
mkdir -p /var/www/certbot

# Copy nginx config
cp $PROJECT_DIR/nginx/traitkeeper.conf /etc/nginx/sites-available/traitkeeper

# Remove default site
rm -f /etc/nginx/sites-enabled/default

# Enable our site
ln -sf /etc/nginx/sites-available/traitkeeper /etc/nginx/sites-enabled/

# Test nginx config
nginx -t

print_success "Nginx configured"

# ==================================================
# 4. Obtain SSL Certificate
# ==================================================
print_info "Obtaining SSL certificate from Let's Encrypt..."

# Stop nginx temporarily
systemctl stop nginx

# Get certificate (standalone mode since nginx is stopped)
certbot certonly --standalone \
    -d $DOMAIN \
    -d www.$DOMAIN \
    --non-interactive \
    --agree-tos \
    --email $EMAIL \
    --preferred-challenges http

if [ $? -eq 0 ]; then
    print_success "SSL certificate obtained successfully!"
else
    print_error "Failed to obtain SSL certificate"
    print_info "You may need to:"
    print_info "1. Ensure your domain DNS is pointing to this server"
    print_info "2. Ensure port 80 and 443 are open in your firewall"
    exit 1
fi

# ==================================================
# 5. Set Up Auto-Renewal
# ==================================================
print_info "Setting up SSL certificate auto-renewal..."

# Create renewal hook to reload nginx
cat > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh <<EOF
#!/bin/bash
systemctl reload nginx
EOF

chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh

# Test renewal (dry run)
certbot renew --dry-run

print_success "SSL auto-renewal configured"

# ==================================================
# 6. Start Nginx
# ==================================================
print_info "Starting Nginx..."
systemctl start nginx
systemctl enable nginx

print_success "Nginx started and enabled"

# ==================================================
# 7. Configure Firewall (UFW)
# ==================================================
print_info "Configuring firewall..."

# Install UFW if not installed
apt-get install -y ufw

# Allow SSH (important!)
ufw allow 22/tcp

# Allow HTTP and HTTPS
ufw allow 80/tcp
ufw allow 443/tcp

# Enable firewall
echo "y" | ufw enable

print_success "Firewall configured"

# ==================================================
# 8. Set File Permissions
# ==================================================
print_info "Setting file permissions..."

# Ensure nginx can read static files
chown -R $DEPLOY_USER:$DEPLOY_USER $PROJECT_DIR
chmod -R 755 $PROJECT_DIR/staticfiles
chmod -R 755 $PROJECT_DIR/media

print_success "File permissions set"

# ==================================================
# 9. Final Checks
# ==================================================
echo ""
echo "================================"
print_success "Production Setup Complete!"
echo "================================"
echo ""

print_info "Next steps:"
echo "1. Update your .env file with production values"

# Check if Docker is running
if systemctl is-active --quiet docker; then
    echo "2. Start Docker containers: cd $PROJECT_DIR && docker compose up -d"
else
    echo "2. Start Docker service first: sudo systemctl start docker"
    echo "3. Then start containers: cd $PROJECT_DIR && docker compose up -d"
fi

echo "3. Test your site: https://$DOMAIN"
echo "4. Check SSL rating: https://www.ssllabs.com/ssltest/analyze.html?d=$DOMAIN"
echo ""

print_info "Important URLs:"
echo "   🌐 Website: https://$DOMAIN"
echo "   🔒 SSL Labs Test: https://www.ssllabs.com/ssltest/analyze.html?d=$DOMAIN"
echo "   📊 Security Headers: https://securityheaders.com/?q=https://$DOMAIN"
echo ""

print_info "SSL Certificate Locations:"
echo "   📜 Certificate: /etc/letsencrypt/live/$DOMAIN/fullchain.pem"
echo "   🔑 Private Key: /etc/letsencrypt/live/$DOMAIN/privkey.pem"
echo "   📅 Auto-renewal: Configured (runs twice daily)"
echo ""
