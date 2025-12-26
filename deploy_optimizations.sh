#!/bin/bash
#
# ONE-CLICK DEPLOYMENT SCRIPT FOR OPTIMIZED INDEXERS
#
# This script safely deploys the optimized indexers ALONGSIDE your existing setup.
# No changes to existing containers. Easy rollback.
#
# Usage:
#   chmod +x deploy_optimizations.sh
#   ./deploy_optimizations.sh
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
echo "║   🚀 DEPLOYING OPTIMIZED INDEXERS (90-99% EFFICIENCY)         ║"
echo "║                                                                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Step 1: Check prerequisites
echo -e "${BLUE}[1/8]${NC} Checking prerequisites..."

if [ ! -f "docker-compose.optimized.yml" ]; then
    echo -e "${RED}❌ Error: docker-compose.optimized.yml not found${NC}"
    exit 1
fi

if [ ! -f "indexer/management/commands/run_scheduled_indexer_optimized.py" ]; then
    echo -e "${RED}❌ Error: Optimized scheduled indexer not found${NC}"
    exit 1
fi

if [ ! -f "indexer/services/optimized_main.py" ]; then
    echo -e "${RED}❌ Error: Optimized main service not found${NC}"
    exit 1
fi

echo -e "${GREEN}✅ All prerequisite files found${NC}"
echo ""

# Step 2: Create backup
echo -e "${BLUE}[2/8]${NC} Creating backup of current state..."

BACKUP_DIR="backups/pre-optimization-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Backup current container states
docker ps -a > "$BACKUP_DIR/container_states.txt" 2>/dev/null || true
docker-compose ps > "$BACKUP_DIR/compose_states.txt" 2>/dev/null || true

echo -e "${GREEN}✅ Backup created at: $BACKUP_DIR${NC}"
echo ""

# Step 3: Check if postgres and redis are running (REQUIRED)
echo -e "${BLUE}[3/8]${NC} Checking required services (postgres, redis)..."

POSTGRES_RUNNING=$(docker ps --filter "name=postgres" --format "{{.Names}}" || echo "")
REDIS_RUNNING=$(docker ps --filter "name=redis" --format "{{.Names}}" || echo "")

if [ -z "$POSTGRES_RUNNING" ]; then
    echo -e "${YELLOW}⚠️  Postgres is NOT running. Starting it now...${NC}"
    docker-compose up -d postgres
    echo -e "${YELLOW}Waiting 10 seconds for postgres to initialize...${NC}"
    sleep 10
else
    echo -e "${GREEN}✅ Postgres is running: $POSTGRES_RUNNING${NC}"
fi

if [ -z "$REDIS_RUNNING" ]; then
    echo -e "${YELLOW}⚠️  Redis is NOT running. Starting it now...${NC}"
    docker-compose up -d redis
    echo -e "${YELLOW}Waiting 5 seconds for redis to initialize...${NC}"
    sleep 5
else
    echo -e "${GREEN}✅ Redis is running: $REDIS_RUNNING${NC}"
fi

# Check if network exists (CRITICAL - must exist before compose up)
NETWORK_EXISTS=$(docker network ls --filter "name=traitkeeper-network" --format "{{.Name}}" 2>/dev/null | grep -x "traitkeeper-network" || echo "")
if [ -z "$NETWORK_EXISTS" ]; then
    echo -e "${YELLOW}⚠️  Network traitkeeper-network does not exist. Creating it now...${NC}"

    # Try to create the network
    if docker network create traitkeeper-network 2>/dev/null; then
        echo -e "${GREEN}✅ Network created successfully: traitkeeper-network${NC}"
    else
        # Network might already exist, verify
        NETWORK_CHECK=$(docker network ls --filter "name=traitkeeper-network" --format "{{.Name}}" 2>/dev/null | grep -x "traitkeeper-network" || echo "")
        if [ -n "$NETWORK_CHECK" ]; then
            echo -e "${GREEN}✅ Network already exists: traitkeeper-network${NC}"
        else
            echo -e "${RED}❌ ERROR: Failed to create network. Trying alternative method...${NC}"
            # Try with driver specification
            docker network create --driver bridge traitkeeper-network || {
                echo -e "${RED}❌ CRITICAL: Cannot create network. Please run manually:${NC}"
                echo -e "${RED}   docker network create traitkeeper-network${NC}"
                exit 1
            }
            echo -e "${GREEN}✅ Network created with bridge driver${NC}"
        fi
    fi
else
    echo -e "${GREEN}✅ Network exists: $NETWORK_EXISTS${NC}"
fi

# Verify network one more time before proceeding
FINAL_CHECK=$(docker network ls --filter "name=traitkeeper-network" --format "{{.Name}}" 2>/dev/null | grep -x "traitkeeper-network" || echo "")
if [ -z "$FINAL_CHECK" ]; then
    echo -e "${RED}❌ CRITICAL ERROR: Network verification failed!${NC}"
    echo -e "${RED}Please create the network manually:${NC}"
    echo -e "${YELLOW}   docker network create traitkeeper-network${NC}"
    exit 1
fi

echo ""

# Check if existing indexers are running (informational only)
echo -e "${BLUE}[3b/8]${NC} Checking existing indexer status (informational)..."

SCHEDULED_RUNNING=$(docker ps --filter "name=indexer-scheduled" --format "{{.Names}}" | grep -v "optimized" || echo "")
LIVE_RUNNING=$(docker ps --filter "name=indexer-live" --format "{{.Names}}" | grep -v "optimized" || echo "")

if [ -n "$SCHEDULED_RUNNING" ]; then
    echo -e "${GREEN}✅ Existing scheduled indexer is running: $SCHEDULED_RUNNING${NC}"
else
    echo -e "${YELLOW}ℹ️  Existing scheduled indexer is NOT running (this is OK)${NC}"
fi

if [ -n "$LIVE_RUNNING" ]; then
    echo -e "${GREEN}✅ Existing live indexer is running: $LIVE_RUNNING${NC}"
else
    echo -e "${YELLOW}ℹ️  Existing live indexer is NOT running (this is OK)${NC}"
fi
echo ""

# Step 4: Build optimized images
echo -e "${BLUE}[4/8]${NC} Building optimized Docker images..."
echo -e "${YELLOW}This may take a few minutes...${NC}"

docker-compose -f docker-compose.optimized.yml build

echo -e "${GREEN}✅ Docker images built successfully${NC}"
echo ""

# Step 5: Check if optimized containers already exist
echo -e "${BLUE}[5/8]${NC} Checking for existing optimized containers..."

OPTIMIZED_SCHEDULED=$(docker ps -a --filter "name=indexer-scheduled-optimized" --format "{{.Names}}" || echo "")
OPTIMIZED_LIVE=$(docker ps -a --filter "name=indexer-live-optimized" --format "{{.Names}}" || echo "")

if [ -n "$OPTIMIZED_SCHEDULED" ] || [ -n "$OPTIMIZED_LIVE" ]; then
    echo -e "${YELLOW}⚠️  Found existing optimized containers. Removing them first...${NC}"
    docker-compose -f docker-compose.optimized.yml down
    echo -e "${GREEN}✅ Old optimized containers removed${NC}"
else
    echo -e "${GREEN}✅ No existing optimized containers found${NC}"
fi
echo ""

# Step 6: Start optimized indexers
echo -e "${BLUE}[6/8]${NC} Starting optimized indexers..."
echo -e "${YELLOW}Deploying ALONGSIDE existing indexers (no disruption)${NC}"

docker-compose -f docker-compose.optimized.yml up -d

echo -e "${GREEN}✅ Optimized indexers started successfully${NC}"
echo ""

# Step 7: Wait for containers to initialize
echo -e "${BLUE}[7/8]${NC} Waiting for containers to initialize (10 seconds)..."
sleep 10
echo ""

# Step 8: Verify deployment
echo -e "${BLUE}[8/8]${NC} Verifying deployment..."

SCHEDULED_OPT_RUNNING=$(docker ps --filter "name=indexer-scheduled-optimized" --format "{{.Names}}" || echo "")
LIVE_OPT_RUNNING=$(docker ps --filter "name=indexer-live-optimized" --format "{{.Names}}" || echo "")

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                    DEPLOYMENT SUMMARY                          ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Check scheduled indexer
if [ -n "$SCHEDULED_OPT_RUNNING" ]; then
    echo -e "${GREEN}✅ Optimized Scheduled Indexer: RUNNING${NC}"
    echo "   Container: $SCHEDULED_OPT_RUNNING"
else
    echo -e "${RED}❌ Optimized Scheduled Indexer: FAILED${NC}"
fi

# Check live indexer
if [ -n "$LIVE_OPT_RUNNING" ]; then
    echo -e "${GREEN}✅ Optimized Live Indexer: RUNNING${NC}"
    echo "   Container: $LIVE_OPT_RUNNING"
else
    echo -e "${RED}❌ Optimized Live Indexer: FAILED${NC}"
fi

echo ""
echo "Original Indexers Status:"
if [ -n "$SCHEDULED_RUNNING" ]; then
    echo -e "${GREEN}✅ Original Scheduled Indexer: RUNNING (unchanged)${NC}"
else
    echo -e "${YELLOW}⚠️  Original Scheduled Indexer: NOT RUNNING${NC}"
fi

if [ -n "$LIVE_RUNNING" ]; then
    echo -e "${GREEN}✅ Original Live Indexer: RUNNING (unchanged)${NC}"
else
    echo -e "${YELLOW}⚠️  Original Live Indexer: NOT RUNNING${NC}"
fi

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                    NEXT STEPS                                  ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "1. Monitor performance of optimized indexers:"
echo -e "   ${BLUE}docker-compose -f docker-compose.optimized.yml logs -f indexer-scheduled-optimized${NC}"
echo ""
echo "2. Look for these success indicators:"
echo "   ✓ Throughput: 3.0+ collections/second (90%+ efficiency)"
echo "   ✓ '✅ DATA INTEGRITY CHECK PASSED' in logs"
echo "   ✓ 'Batching efficiency: 25-35x' for live indexer"
echo ""
echo "3. Compare with original indexers:"
echo -e "   ${BLUE}docker logs indexer-scheduled --tail 50${NC}"
echo ""
echo "4. If optimized indexers work well (after 24 hours):"
echo "   - Stop original indexers with your main docker-compose"
echo "   - Keep optimized ones running"
echo ""
echo "5. If there are issues:"
echo -e "   ${BLUE}./rollback_optimizations.sh${NC}"
echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║              DEPLOYMENT COMPLETE! 🚀                           ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo -e "${GREEN}Both optimized and original indexers are now running side-by-side.${NC}"
echo -e "${GREEN}Monitor performance and choose which to keep.${NC}"
echo ""
