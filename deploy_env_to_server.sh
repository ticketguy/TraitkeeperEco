#!/bin/bash
# Copy .env file to DigitalOcean server

SERVER_IP="138.199.6.184"
SERVER_USER="root"
PROJECT_PATH="TraitkeeperEco"

echo "📤 Copying .env file to production server..."

scp .env $SERVER_USER@$SERVER_IP:~/$PROJECT_PATH/.env

if [ $? -eq 0 ]; then
    echo "✅ .env file copied successfully!"
    echo ""
    echo "Now SSH to server and restart containers:"
    echo "  ssh $SERVER_USER@$SERVER_IP"
    echo "  cd $PROJECT_PATH"
    echo "  docker compose restart"
else
    echo "❌ Failed to copy .env file"
    exit 1
fi
