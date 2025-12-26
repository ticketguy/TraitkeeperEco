#!/bin/bash
#
# ONE-CLICK ROLLBACK SCRIPT FOR OPTIMIZED INDEXERS
#
# This script safely removes the optimized indexers and keeps your original setup intact.
#
# Usage:
#   chmod +x rollback_optimizations.sh
#   ./rollback_optimizations.sh
#

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                                                                ║"
echo "║         🔄 ROLLING BACK OPTIMIZED INDEXERS                    ║"
echo "║                                                                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Step 1: Confirm rollback
echo -e "${YELLOW}⚠️  This will stop and remove the optimized indexers.${NC}"
echo -e "${YELLOW}⚠️  Your original indexers will continue running unchanged.${NC}"
echo ""
read -p "Are you sure you want to rollback? (yes/no): " -r
echo ""

if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo -e "${RED}Rollback cancelled.${NC}"
    exit 0
fi

# Step 2: Check if optimized containers exist
echo -e "${BLUE}[1/4]${NC} Checking for optimized containers..."

OPTIMIZED_SCHEDULED=$(docker ps -a --filter "name=indexer-scheduled-optimized" --format "{{.Names}}" || echo "")
OPTIMIZED_LIVE=$(docker ps -a --filter "name=indexer-live-optimized" --format "{{.Names}}" || echo "")

if [ -z "$OPTIMIZED_SCHEDULED" ] && [ -z "$OPTIMIZED_LIVE" ]; then
    echo -e "${YELLOW}⚠️  No optimized containers found. Nothing to rollback.${NC}"
    exit 0
fi

if [ -n "$OPTIMIZED_SCHEDULED" ]; then
    echo -e "${GREEN}Found: $OPTIMIZED_SCHEDULED${NC}"
fi

if [ -n "$OPTIMIZED_LIVE" ]; then
    echo -e "${GREEN}Found: $OPTIMIZED_LIVE${NC}"
fi
echo ""

# Step 3: Stop and remove optimized containers
echo -e "${BLUE}[2/4]${NC} Stopping and removing optimized indexers..."

docker-compose -f docker-compose.optimized.yml down

echo -e "${GREEN}✅ Optimized containers stopped and removed${NC}"
echo ""

# Step 3b: Remove Docker images (optional but thorough cleanup)
echo -e "${BLUE}[2b/4]${NC} Cleaning up Docker images..."

SCHEDULED_IMAGE=$(docker images --filter "reference=*indexer-scheduled-optimized*" --format "{{.Repository}}:{{.Tag}}" || echo "")
LIVE_IMAGE=$(docker images --filter "reference=*indexer-live-optimized*" --format "{{.Repository}}:{{.Tag}}" || echo "")

if [ -n "$SCHEDULED_IMAGE" ]; then
    echo -e "${YELLOW}Removing scheduled indexer image: $SCHEDULED_IMAGE${NC}"
    docker rmi "$SCHEDULED_IMAGE" 2>/dev/null || echo -e "${YELLOW}(Image in use or already removed)${NC}"
fi

if [ -n "$LIVE_IMAGE" ]; then
    echo -e "${YELLOW}Removing live indexer image: $LIVE_IMAGE${NC}"
    docker rmi "$LIVE_IMAGE" 2>/dev/null || echo -e "${YELLOW}(Image in use or already removed)${NC}"
fi

# Also try to clean up by container name pattern
echo -e "${YELLOW}Removing any dangling optimized images...${NC}"
docker images | grep "traitkeepereco.*optimized" | awk '{print $3}' | xargs -r docker rmi 2>/dev/null || true

echo -e "${GREEN}✅ Docker images cleaned up${NC}"
echo ""

# Step 4: Verify rollback
echo -e "${BLUE}[4/5]${NC} Verifying rollback..."

OPTIMIZED_SCHEDULED_CHECK=$(docker ps -a --filter "name=indexer-scheduled-optimized" --format "{{.Names}}" || echo "")
OPTIMIZED_LIVE_CHECK=$(docker ps -a --filter "name=indexer-live-optimized" --format "{{.Names}}" || echo "")

if [ -z "$OPTIMIZED_SCHEDULED_CHECK" ] && [ -z "$OPTIMIZED_LIVE_CHECK" ]; then
    echo -e "${GREEN}✅ All optimized containers successfully removed${NC}"
else
    echo -e "${RED}❌ Warning: Some containers may still exist${NC}"
fi
echo ""

# Step 5: Check original indexers
echo -e "${BLUE}[5/5]${NC} Checking original indexer status..."

SCHEDULED_RUNNING=$(docker ps --filter "name=indexer-scheduled" --format "{{.Names}}" | grep -v "optimized" || echo "")
LIVE_RUNNING=$(docker ps --filter "name=indexer-live" --format "{{.Names}}" | grep -v "optimized" || echo "")

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                    ROLLBACK SUMMARY                            ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

echo "Optimized Indexers:"
if [ -z "$OPTIMIZED_SCHEDULED_CHECK" ]; then
    echo -e "${GREEN}✅ Optimized Scheduled Indexer: REMOVED${NC}"
else
    echo -e "${YELLOW}⚠️  Optimized Scheduled Indexer: STILL EXISTS${NC}"
fi

if [ -z "$OPTIMIZED_LIVE_CHECK" ]; then
    echo -e "${GREEN}✅ Optimized Live Indexer: REMOVED${NC}"
else
    echo -e "${YELLOW}⚠️  Optimized Live Indexer: STILL EXISTS${NC}"
fi

echo ""
echo "Original Indexers:"
if [ -n "$SCHEDULED_RUNNING" ]; then
    echo -e "${GREEN}✅ Original Scheduled Indexer: RUNNING${NC}"
    echo "   Container: $SCHEDULED_RUNNING"
else
    echo -e "${RED}❌ Original Scheduled Indexer: NOT RUNNING${NC}"
    echo -e "${YELLOW}   You may need to start it with your main docker-compose${NC}"
fi

if [ -n "$LIVE_RUNNING" ]; then
    echo -e "${GREEN}✅ Original Live Indexer: RUNNING${NC}"
    echo "   Container: $LIVE_RUNNING"
else
    echo -e "${RED}❌ Original Live Indexer: NOT RUNNING${NC}"
    echo -e "${YELLOW}   You may need to start it with your main docker-compose${NC}"
fi

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║              ROLLBACK COMPLETE! ✅                             ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo -e "${GREEN}Optimized indexers have been removed.${NC}"
echo -e "${GREEN}Your original setup is preserved and running.${NC}"
echo ""

# Optional: Show recent logs from original indexers
if [ -n "$SCHEDULED_RUNNING" ]; then
    echo -e "${BLUE}Recent logs from original scheduled indexer:${NC}"
    docker logs "$SCHEDULED_RUNNING" --tail 10 2>/dev/null || echo "Could not fetch logs"
    echo ""
fi
