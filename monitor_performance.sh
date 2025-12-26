#!/bin/bash
#
# PERFORMANCE MONITORING SCRIPT
#
# Compare performance between original and optimized indexers
#
# Usage:
#   chmod +x monitor_performance.sh
#   ./monitor_performance.sh
#

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

clear
echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                                                                ║"
echo "║            📊 INDEXER PERFORMANCE MONITOR                     ║"
echo "║                                                                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Function to get container status
get_status() {
    local container_name=$1
    local status=$(docker ps --filter "name=$container_name" --format "{{.Status}}" 2>/dev/null)
    if [ -n "$status" ]; then
        echo -e "${GREEN}RUNNING${NC}"
    else
        echo -e "${YELLOW}STOPPED${NC}"
    fi
}

# Function to get recent performance metrics from logs
get_metrics() {
    local container_name=$1
    echo ""
    echo -e "${CYAN}Recent Performance Metrics:${NC}"
    docker logs "$container_name" --tail 200 2>/dev/null | grep -E "PERFORMANCE|Throughput|Efficiency|Batching|collections/second|DATA INTEGRITY" | tail -15 || echo "No metrics found"
}

# Check optimized scheduled indexer
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}OPTIMIZED SCHEDULED INDEXER${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
OPT_SCHEDULED=$(docker ps --filter "name=indexer-scheduled-optimized" --format "{{.Names}}" 2>/dev/null || echo "")
if [ -n "$OPT_SCHEDULED" ]; then
    echo "Container: $OPT_SCHEDULED"
    echo -e "Status: $(get_status "$OPT_SCHEDULED")"
    get_metrics "$OPT_SCHEDULED"
else
    echo -e "${YELLOW}Not deployed${NC}"
fi

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}ORIGINAL SCHEDULED INDEXER${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
ORIG_SCHEDULED=$(docker ps --filter "name=indexer-scheduled" --format "{{.Names}}" | grep -v "optimized" 2>/dev/null || echo "")
if [ -n "$ORIG_SCHEDULED" ]; then
    echo "Container: $ORIG_SCHEDULED"
    echo -e "Status: $(get_status "$ORIG_SCHEDULED")"
    echo ""
    echo -e "${CYAN}Recent Activity:${NC}"
    docker logs "$ORIG_SCHEDULED" --tail 50 2>/dev/null | grep -E "📊|✅|💾|Processing|collections" | tail -10 || echo "No activity logs found"
else
    echo -e "${YELLOW}Not running${NC}"
fi

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}OPTIMIZED LIVE INDEXER${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
OPT_LIVE=$(docker ps --filter "name=indexer-live-optimized" --format "{{.Names}}" 2>/dev/null || echo "")
if [ -n "$OPT_LIVE" ]; then
    echo "Container: $OPT_LIVE"
    echo -e "Status: $(get_status "$OPT_LIVE")"
    get_metrics "$OPT_LIVE"
else
    echo -e "${YELLOW}Not deployed${NC}"
fi

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}ORIGINAL LIVE INDEXER${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
ORIG_LIVE=$(docker ps --filter "name=indexer-live" --format "{{.Names}}" | grep -v "optimized" 2>/dev/null || echo "")
if [ -n "$ORIG_LIVE" ]; then
    echo "Container: $ORIG_LIVE"
    echo -e "Status: $(get_status "$ORIG_LIVE")"
    echo ""
    echo -e "${CYAN}Recent Activity:${NC}"
    docker logs "$ORIG_LIVE" --tail 50 2>/dev/null | grep -E "🔔|LIVE EVENT|Processing|event" | tail -10 || echo "No activity logs found"
else
    echo -e "${YELLOW}Not running${NC}"
fi

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                    QUICK COMMANDS                              ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Watch optimized scheduled indexer logs:"
echo -e "  ${CYAN}docker-compose -f docker-compose.optimized.yml logs -f indexer-scheduled-optimized${NC}"
echo ""
echo "Watch optimized live indexer logs:"
echo -e "  ${CYAN}docker-compose -f docker-compose.optimized.yml logs -f indexer-live-optimized${NC}"
echo ""
echo "Compare side-by-side:"
echo -e "  ${CYAN}# Terminal 1${NC}"
echo -e "  ${CYAN}docker logs -f $OPT_SCHEDULED 2>&1 | grep 'PERFORMANCE'${NC}"
echo -e "  ${CYAN}# Terminal 2${NC}"
echo -e "  ${CYAN}docker logs -f $ORIG_SCHEDULED 2>&1 | grep 'collections'${NC}"
echo ""
echo "Refresh this monitor:"
echo -e "  ${CYAN}./monitor_performance.sh${NC}"
echo ""
