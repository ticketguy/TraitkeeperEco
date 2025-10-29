# Makefile Quick Reference

## 🚀 Most Common Commands

```bash
make dev              # Start development environment (all services)
make down             # Stop all containers
make logs-web         # View web server logs
make logs-live        # View live indexer logs
make migrate          # Run database migrations
make shell            # Open Django shell
```

## 📋 Quick Workflows

### Starting Development

```bash
# Option 1: Full stack (recommended)
make dev

# Option 2: Minimal setup (frontend work only)
make dev-minimal

# Option 3: Background mode (don't want to see logs)
make dev-bg
```

### Working on Specific Features

```bash
# Working on live transaction processing
make dev-minimal        # Terminal 1: Start core services
make start-live         # Terminal 2: Start live indexer
make logs-live          # Terminal 3: Watch logs

# Working on vitality analytics
make dev-minimal
make start-vitality
make logs-vitality

# Working on scheduled indexing
make dev-minimal
make start-scheduled
make logs-scheduled
```

### Debugging Issues

```bash
# Check service status
make status

# View all logs
make logs

# View specific service logs
make logs-web
make logs-live
make logs-scheduled
make logs-vitality

# Access containers
make bash              # Open shell in main container
make dbshell           # Open PostgreSQL
make redis-cli         # Open Redis CLI
```

### Database Operations

```bash
# Run migrations
make migrate

# Create new migrations
make makemigrations

# Django shell for queries
make shell

# Reset database (careful!)
make flush
```

### Restarting Services

```bash
# Restart specific service (when code changes don't auto-reload)
make restart-live
make restart-scheduled
make restart-vitality
make restart-web

# Restart everything
make restart
```

### Cleanup

```bash
# Stop containers
make down

# Stop and remove volumes (fresh start)
make clean

# Remove Docker junk
make prune
```

## 🎯 Service-Specific Commands

### Live Indexer

```bash
make start-live         # Start
make restart-live       # Restart
make logs-live          # View logs
```

### Scheduled Indexer

```bash
make start-scheduled
make restart-scheduled
make logs-scheduled
```

### Vitality Analytics

```bash
make start-vitality
make restart-vitality
make logs-vitality
make calc-vitality      # Manual calculation for all
make calc-vitality-collection  # For specific collection
```

### Health Monitoring

```bash
make start-health
make restart-health
make logs-health
```

## 🔧 Advanced Usage

### Multiple Terminals Setup

**Terminal 1: Services**

```bash
make dev
```

**Terminal 2: Logs**

```bash
make logs-live
```

**Terminal 3: Commands**

```bash
make shell
make migrate
make test
```

### Selective Service Startup

```bash
# Core only
make dev-minimal

# Core + indexing
make dev-indexing

# Core + analytics
make dev-analytics
```

### Production Commands

```bash
# Start production
make prod

# View production logs
docker-compose logs -f

# Stop production
docker-compose down
```

## 💡 Pro Tips

### 1. Background Mode for Long-Running Tasks

```bash
# Start in background
make dev-bg

# View logs anytime
make logs

# Stop when done
make down
```

### 2. Quick Service Restart

```bash
# After code changes that don't auto-reload
make restart-live
make restart-vitality
```

### 3. Database Troubleshooting

```bash
# Check if migrations are needed
make shell
>>> from django.db import connection
>>> connection.cursor().execute("SELECT * FROM django_migrations ORDER BY applied DESC LIMIT 5;")

# Or use dbshell
make dbshell
SELECT * FROM django_migrations ORDER BY applied DESC LIMIT 5;
```

### 4. Clean Slate

```bash
# Complete reset
make clean          # Stop and remove volumes
make rebuild        # Rebuild images
make dev            # Start fresh
```

### 5. Check Service Health

```bash
make status

# Look for "(healthy)" status:
# NAME                              STATUS
# traitkeeper-main-dev              Up (healthy)
# traitkeeper-indexer-live-dev      Up (healthy)
```

## 🐛 Common Issues & Solutions

### Port 8000 Already in Use

```bash
# Stop everything
make down

# Check what's using port
lsof -i :8000

# Kill the process or change port in docker-compose.yml
```

### Containers Won't Start

```bash
# Check status
make status

# View logs
make logs

# Force rebuild
make rebuild
```

### Code Changes Not Reflecting

```bash
# For Python changes (should auto-reload)
# If not working, restart service:
make restart-web

# For static files
make collectstatic

# For requirements.txt changes
make rebuild
```

### Database Connection Issues

```bash
# Check if postgres is running
make status | grep postgres

# Check postgres logs
docker-compose logs postgres

# Recreate postgres
make down
make dev
```

## 📊 Monitoring in Development

### Check All Services

```bash
# View status
make status

# View resource usage
make stats

# View all logs
make logs
```

### Follow Specific Service

```bash
# Open multiple terminals, one per service:
make logs-web          # Terminal 1
make logs-live         # Terminal 2
make logs-vitality     # Terminal 3
```

## 🎓 Cheat Sheet

| Task | Command |
|------|---------|
| Start dev | `make dev` |
| Stop all | `make down` |
| View logs | `make logs` |
| Run migrations | `make migrate` |
| Django shell | `make shell` |
| Restart service | `make restart-live` |
| Fresh start | `make clean && make dev` |
| Test code | `make test` |
| Check status | `make status` |
| Calculate vitality | `make calc-vitality` |

## 🔗 Related Files

- `docker-compose.yml` - Production configuration
- `docker-compose.dev.yml` - Development configuration
- `Dockerfile` - Container build instructions
- `.env` - Environment variables

## 📖 Full Command List

Run `make help` to see all available commands organized by category.
