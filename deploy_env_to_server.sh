#!/bin/bash
# Copy .env file to production server
#
# Usage:
#   ./deploy_env_to_server.sh [SERVER_IP] [SERVER_USER] [PROJECT_PATH]
#
# Examples:
#   ./deploy_env_to_server.sh                              # Use defaults
#   ./deploy_env_to_server.sh 138.199.6.184 root           # Custom IP and user
#   ./deploy_env_to_server.sh 138.199.6.184 root myproject # Full custom

# Accept parameters or use defaults
SERVER_IP="${1:-138.199.6.184}"
SERVER_USER="${2:-root}"
PROJECT_PATH="${3:-traitkeeper}"

echo "📤 Copying .env file to production server..."
echo "   Server: $SERVER_USER@$SERVER_IP"
echo "   Path: ~/$PROJECT_PATH"
echo ""

scp .env $SERVER_USER@$SERVER_IP:~/$PROJECT_PATH/.env

if [ $? -eq 0 ]; then
    echo "✅ .env file copied successfully!"
    echo ""
    echo "Next steps - SSH to server and restart containers:"
    echo "  ssh $SERVER_USER@$SERVER_IP"
    echo "  cd $PROJECT_PATH"
    echo "  docker compose restart"
    echo ""
    echo "Or use the deployment script:"
    echo "  ssh $SERVER_USER@$SERVER_IP 'cd $PROJECT_PATH && ./deploy.sh'"
else
    echo "❌ Failed to copy .env file"
    echo "Make sure:"
    echo "  1. SSH access is configured (try: ssh $SERVER_USER@$SERVER_IP)"
    echo "  2. The project directory exists on the server: ~/$PROJECT_PATH"
    exit 1
fi
