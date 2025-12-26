#!/bin/bash
#
# EMERGENCY DISK SPACE CLEANUP SCRIPT
#
# This script frees up disk space by cleaning logs and Docker resources
#
# Usage:
#   chmod +x cleanup_disk_space.sh
#   ./cleanup_disk_space.sh
#

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                                                                ║"
echo "║         🧹 EMERGENCY DISK SPACE CLEANUP                       ║"
echo "║                                                                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Step 1: Check current disk usage
echo -e "${BLUE}[1/5]${NC} Current disk usage:"
df -h | grep -E "Filesystem|/$"
echo ""

# Step 2: Clean up log files
echo -e "${BLUE}[2/5]${NC} Cleaning up log files..."
LOG_SIZE=$(du -sh logs/ 2>/dev/null | awk '{print $1}' || echo "0")
echo -e "${YELLOW}Current logs directory size: $LOG_SIZE${NC}"

if [ -d "logs" ]; then
    # Keep only the last 100 lines of each log file
    for logfile in logs/*.log; do
        if [ -f "$logfile" ]; then
            echo "Truncating: $logfile"
            tail -n 100 "$logfile" > "$logfile.tmp" 2>/dev/null || true
            mv "$logfile.tmp" "$logfile" 2>/dev/null || true
        fi
    done
    echo -e "${GREEN}✅ Log files truncated${NC}"
else
    echo -e "${YELLOW}No logs directory found${NC}"
fi

NEW_LOG_SIZE=$(du -sh logs/ 2>/dev/null | awk '{print $1}' || echo "0")
echo -e "${GREEN}New logs directory size: $NEW_LOG_SIZE${NC}"
echo ""

# Step 3: Clean up Docker resources
echo -e "${BLUE}[3/5]${NC} Cleaning up Docker resources..."
echo -e "${YELLOW}This will remove:${NC}"
echo "  - All stopped containers"
echo "  - All unused images"
echo "  - All unused volumes"
echo "  - All build cache"
echo ""

docker system prune -a --volumes -f

echo -e "${GREEN}✅ Docker resources cleaned${NC}"
echo ""

# Step 4: Clean up Python cache
echo -e "${BLUE}[4/5]${NC} Cleaning up Python cache files..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true
echo -e "${GREEN}✅ Python cache cleaned${NC}"
echo ""

# Step 5: Clean up git garbage
echo -e "${BLUE}[5/5]${NC} Optimizing git repository..."
git gc --aggressive --prune=now
echo -e "${GREEN}✅ Git repository optimized${NC}"
echo ""

# Final disk usage
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                    CLEANUP SUMMARY                             ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo -e "${BLUE}Disk usage after cleanup:${NC}"
df -h | grep -E "Filesystem|/$"
echo ""
echo -e "${GREEN}✅ Cleanup complete!${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Try deploying again: ./deploy_optimizations.sh"
echo "2. If still having issues, consider upgrading server storage"
echo ""
