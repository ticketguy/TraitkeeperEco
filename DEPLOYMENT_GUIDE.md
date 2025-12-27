# TraitKeeper Deployment Guide

**Last Updated**: 2025-12-27

## Table of Contents
- [Overview](#overview)
- [Consolidated System](#consolidated-system)
- [Deployment Methods](#deployment-methods)
- [Service Management](#service-management)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)

---

## Overview

TraitKeeper is now consolidated into a **single, optimized system** with:
- ✅ **Hybrid collection resolution** (DB-first + API fallback)
- ✅ **Batch event processing** (30-second windows)
- ✅ **Redis caching** (90%+ hit rate after warmup)
- ✅ **Auto-discovery** of new NFTs in tracked collections
- ✅ **90-99% efficiency** with zero data loss tolerance

---

## Consolidated System

### What Changed

#### Before (Dual System)
```
indexer/services/
├── main.py                    # Original indexer
└── optimized_main.py          # Optimized indexer

docker-compose.yml             # Original services
docker-compose.optimized.yml   # Optimized services
```

#### After (Consolidated)
```
indexer/services/
├── main.py                    # Unified optimized indexer
└── main_legacy.py             # Backup (reference only)

docker-compose.yml             # All services (optimized)
deploy.sh                      # One-click deployment
```

### Benefits
- **Simpler**: Single codebase, no duplication
- **Faster**: All indexers use optimized batch processing
- **Easier**: One-click deployment script
- **Cleaner**: No separate optimized versions to maintain

---

## Deployment Methods

### Method 1: One-Click Deployment (Recommended)

```bash
# On your server
cd /path/to/traitkeeper
git pull origin main
./deploy.sh
```

**What it does:**
1. ✅ Pulls latest code from git
2. ✅ Stops running services
3. ✅ Builds fresh Docker images
4. ✅ Starts postgres & redis
5. ✅ Runs database migrations
6. ✅ Starts all services
7. ✅ Performs health checks
8. ✅ Shows service status

**Output:**
```
============================================================================
TraitKeeper Full Stack Deployment
============================================================================

✅ All prerequisites met
✅ Code updated
✅ All services stopped
✅ Docker images built successfully
✅ PostgreSQL is ready
✅ Redis is ready
✅ Database migrations completed
✅ All services started
✅ Web server is healthy
✅ indexer-live is running
✅ indexer-scheduled is running

============================================================================
Deployment Complete! 🚀
============================================================================
```

---

### Method 2: Manual Deployment

```bash
# Pull latest code
git pull origin main

# Stop running services
docker-compose down

# Build images
docker-compose build

# Start all services
docker-compose up -d

# Check status
docker-compose ps
```

---

## Service Management

### All Services

```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose down

# Restart all services
docker-compose restart

# View all logs
docker-compose logs -f

# Check status
docker-compose ps
```

### Individual Services

```bash
# Restart specific service
docker-compose restart indexer-live

# View specific logs
docker-compose logs -f indexer-live

# Execute command in service
docker-compose exec main python manage.py shell
```

### Available Services

| Service | Description | Container Name |
|---------|-------------|----------------|
| **postgres** | PostgreSQL database | traitkeeper-postgres |
| **redis** | Redis cache | traitkeeper-redis |
| **main** | Web server (Django/Gunicorn) | traitkeeper-main |
| **indexer-live** | Real-time WebSocket indexer | traitkeeper-indexer-live |
| **indexer-scheduled** | Periodic historical indexer | traitkeeper-indexer-scheduled |
| **indexer-incremental** | Catch-up indexer (every 4h) | traitkeeper-indexer-incremental |
| **vitality-analytics** | Vitality calculations | vitality-analytics |
| **health** | System health monitoring | traitkeeper-health |
| **config-listener** | Provider config watcher | traitkeeper-config-listener |

---

## Monitoring

### Real-Time Logs

```bash
# Live indexer (optimized with batch processing)
docker-compose logs -f indexer-live

# Scheduled indexer (optimized)
docker-compose logs -f indexer-scheduled

# All indexers
docker-compose logs -f indexer-live indexer-scheduled indexer-incremental
```

### Success Indicators

Look for these log messages to confirm optimization is working:

#### Batch Processing
```
📦 Processing batch of X events (window: 30s)
✅ Batch parsed: X/Y successful
⚡ Batch completed in X.XXs (efficiency: X.X events/sec)
```

#### Collection Resolution
```
🔍 Pre-resolving collections for N unique mints from database
✅ Batch resolution complete: X cached from DB, Y will be resolved individually via API
[CACHE HIT] Collection ...
[UNKNOWN NFT] Resolving collection via Helius for mint ...
```

#### Auto-Discovery
```
🆕 NEW NFT in tracked collection ...
✅ Resolved via Helius: ... for mint ...
```

### Performance Metrics

Target metrics:
- **Success Rate**: 80-95% (for tracked collections)
- **Cache Hit Rate**: 90%+ after 1 hour warmup
- **Processing Efficiency**: 2.5-3.5 events/sec
- **API Calls**: 5-10x reduction via batching

### Health Checks

```bash
# Check all service health
docker-compose ps

# Check specific service
docker inspect traitkeeper-indexer-live | grep -A 10 Health
```

---

## Troubleshooting

### Indexer Not Processing Events

```bash
# 1. Check logs for errors
docker-compose logs -f indexer-live

# 2. Restart the service
docker-compose restart indexer-live

# 3. Check database connection
docker-compose exec main python manage.py dbshell
```

### Low Cache Hit Rate

```bash
# Clear Redis cache and let it warm up
docker-compose exec redis redis-cli FLUSHALL

# Wait 1 hour for cache to warm up naturally
# Then check logs for [CACHE HIT] messages
```

### Database Migration Issues

```bash
# Run migrations manually
docker-compose exec main python manage.py migrate

# Or rebuild and migrate
docker-compose down
docker-compose up -d postgres redis
sleep 10
docker-compose run --rm main python manage.py migrate
docker-compose up -d
```

### Service Won't Start

```bash
# Check service logs
docker-compose logs [service-name]

# Remove containers and restart
docker-compose down
docker-compose up -d

# If persistent, rebuild
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Rollback to Previous Version

```bash
# Stop services
docker-compose down

# Revert to previous commit
git log --oneline -n 5  # Find commit hash
git revert [commit-hash]
git push origin main

# On server
git pull origin main
docker-compose build
docker-compose up -d
```

---

## Configuration Files

### Environment Variables

Edit `.env` file:
```bash
# Database
POSTGRES_DB=traitkeeper
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password

# API Keys
HELIUS_API_KEY=your_helius_key
QUICKNODE_RPC_URL=your_quicknode_url

# Django
SECRET_KEY=your_secret_key
DEBUG=False
```

### Docker Compose

Edit `docker-compose.yml` to:
- Adjust resource limits (CPU/memory)
- Change port mappings
- Modify environment variables
- Add new services

**Example: Increase indexer memory:**
```yaml
indexer-live:
  deploy:
    resources:
      limits:
        cpus: '2.0'        # was: '1.0'
        memory: 2G         # was: 1G
```

---

## Best Practices

### Deployment
1. **Always** pull latest code before deploying
2. **Always** run migrations after pulling
3. **Always** use `./deploy.sh` for full deployments
4. **Monitor** logs for first 10 minutes after deployment

### Monitoring
1. Check logs daily for errors
2. Monitor cache hit rate (should be 90%+)
3. Watch for rate limit warnings
4. Verify success rate is 80-95% for tracked collections

### Maintenance
1. Backup database daily
2. Clean up old logs weekly
3. Review failed transactions monthly
4. Update dependencies quarterly

---

## Quick Reference

```bash
# One-click deployment
./deploy.sh

# View live indexer logs
docker-compose logs -f indexer-live

# Restart indexer
docker-compose restart indexer-live

# Run migrations
docker-compose exec main python manage.py migrate

# Django shell
docker-compose exec main python manage.py shell

# Check service status
docker-compose ps

# Stop everything
docker-compose down

# Start everything
docker-compose up -d
```

---

## Support

**Issue**: Something not working?
1. Check logs first
2. Review this guide
3. Try restarting services
4. If persistent, check GitHub issues

**Success**: Everything working?
- Monitor logs for success indicators
- Verify metrics are within target ranges
- Check that volume data is being captured

---

**🚀 Happy Deploying!**
