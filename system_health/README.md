# System Health App

## Overview

Monitors the health and performance of TraitKeeper's systems, including indexer status, database performance, and API availability.

## Purpose

- **System monitoring** - Track uptime and performance
- **Error tracking** - Log and alert on system errors
- **Performance metrics** - Monitor response times, throughput
- **Health checks** - Periodic checks of all services

## Features

### Health Checks

- Database connectivity
- Redis connectivity
- RPC provider status (QuickNode, Helius)
- WebSocket connection status
- Background task status

### Metrics Tracked

- Indexer events per second
- Database query performance
- API response times
- Cache hit rates
- Failed transaction count

## Endpoints

- `/health/` - Overall system health (200 or 500)
- `/health/detailed/` - Component-level health status
- `/health/metrics/` - Performance metrics

## Alerts

Configured to alert when:

- RPC provider down > 5 minutes
- Database queries > 1 second
- Cache hit rate < 70%
- Failed transactions > 100/hour

## TODO

- [ ] Add custom metrics dashboard
- [ ] Implement alerting webhooks (Slack, Discord)
- [ ] Add performance trending
- [ ] Create health check API for monitoring tools
