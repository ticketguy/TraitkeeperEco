# Development Environment Guide

## 🚀 Quick Start

### Start All Services

```bash
docker-compose -f docker-compose.dev.yml up
```

This starts:
- ✅ PostgreSQL & Redis (with healthchecks)
- ✅ Main web server (Django runserver on port 8000)
- ✅ Live indexer (WebSocket)
- ✅ Scheduled indexer (Historical polling)
- ✅ Vitality analytics
- ✅ Health monitoring
- ✅ Config listener

### Start in Detached Mode

```bash
docker-compose -f docker-compose.dev.yml up -d
```

---

## 🎯 Development-Specific Features

### Hot Reload
All services have volume mounts (`- .:/app`), so code changes reload automatically:

```yaml
volumes:
  - .:/app  # Your code changes are immediately reflected
```

**No need to rebuild containers for code changes!**

### Debug Mode
All services run with `DEBUG=1`:

```yaml
environment:
  - DEBUG=1
```

This enables:
- Detailed error pages
- SQL query logging
- Django debug toolbar (if installed)

### Django Development Server
The main service uses `runserver` instead of `gunicorn`:

```bash
python manage.py runserver 0.0.0.0:8000
```

**Advantages:**
- Auto-reload on code changes
- Better error messages
- Easier debugging

### Healthchecks
All services have healthchecks enabled for better monitoring:
- PostgreSQL: `pg_isready` check
- Redis: `redis-cli ping` check
- Main: HTTP check on port 8000
- Background services: Process checks

---

## 📦 Service Management

### Start Specific Services Only

```bash
# Just database and web server (minimal setup)
docker-compose -f docker-compose.dev.yml up postgres redis main

# Add live indexing for testing real-time features
docker-compose -f docker-compose.dev.yml up postgres redis main indexer-live

# Add vitality for testing analytics
docker-compose -f docker-compose.dev.yml up postgres redis main vitality-analytics
```

### Stop Services

```bash
# Stop all
docker-compose -f docker-compose.dev.yml down

# Stop but keep data
docker-compose -f docker-compose.dev.yml stop

# Stop and remove volumes (fresh start)
docker-compose -f docker-compose.dev.yml down -v
```

### View Logs

```bash
# All services
docker-compose -f docker-compose.dev.yml logs -f

# Specific service
docker-compose -f docker-compose.dev.yml logs -f indexer-live
docker-compose -f docker-compose.dev.yml logs -f vitality-analytics

# Multiple services
docker-compose -f docker-compose.dev.yml logs -f main indexer-live
```

---

## 🔧 Common Development Workflows

### 1. Working on Frontend/Backend Only

```bash
# Minimal setup - just web server
docker-compose -f docker-compose.dev.yml up postgres redis main
```

Open: http://localhost:8000

### 2. Testing Live Transaction Processing

```bash
# Web server + live indexer
docker-compose -f docker-compose.dev.yml up postgres redis main indexer-live
```

Watch logs:

```bash
docker-compose -f docker-compose.dev.yml logs -f indexer-live
```

### 3. Testing Historical Indexing

```bash
# Web server + scheduled indexer
docker-compose -f docker-compose.dev.yml up postgres redis main indexer-scheduled
```

The scheduled indexer runs every 15 minutes by default.

### 4. Testing Vitality Calculations

```bash
# Web server + vitality analytics
docker-compose -f docker-compose.dev.yml up postgres redis main vitality-analytics
```

Or manually trigger:

```bash
docker-compose -f docker-compose.dev.yml exec main python manage.py calculate_vitality --all
```

### 5. Full Stack Testing

```bash
# Start everything
docker-compose -f docker-compose.dev.yml up
```

---

## 🐛 Debugging

### Access Django Shell

```bash
docker-compose -f docker-compose.dev.yml exec main python manage.py shell
```

### Run Tests

```bash
docker-compose -f docker-compose.dev.yml exec main python manage.py test
```

### Database Access

```bash
# PostgreSQL
docker-compose -f docker-compose.dev.yml exec postgres psql -U postgres -d traitkeeper_db

# Redis
docker-compose -f docker-compose.dev.yml exec redis redis-cli
```

### Check Service Status

```bash
docker-compose -f docker-compose.dev.yml ps
```

### Restart Single Service

```bash
docker-compose -f docker-compose.dev.yml restart indexer-live
```

---

## 🔄 Database Management

### Apply Migrations

```bash
docker-compose -f docker-compose.dev.yml exec main python manage.py migrate
```

### Create Migrations

```bash
docker-compose -f docker-compose.dev.yml exec main python manage.py makemigrations
```

### Reset Database

```bash
# Stop services
docker-compose -f docker-compose.dev.yml down

# Remove database volume
docker volume rm traitkeeper_postgres_data_dev

# Start fresh
docker-compose -f docker-compose.dev.yml up
```

### Load Fixtures

```bash
docker-compose -f docker-compose.dev.yml exec main python manage.py loaddata fixtures/initial_data.json
```

---

## 📊 Monitoring in Development

### Check Service Health

```bash
# View running services
docker-compose -f docker-compose.dev.yml ps

# Check resource usage
docker stats
```

### View All Logs

```bash
# Tail all logs
docker-compose -f docker-compose.dev.yml logs -f

# Last 100 lines
docker-compose -f docker-compose.dev.yml logs --tail=100

# Since specific time
docker-compose -f docker-compose.dev.yml logs --since 10m
```

---

## 🎨 Code Changes & Hot Reload

### Backend Changes (Python)
✅ **Auto-reload enabled** - Just save your Python files!

The development server will automatically restart:

```
Watching for file changes with StatReloader
Performing system checks...
System check identified no issues (0 silenced).
Django version 5.0.7, using settings 'traitkeeper.settings'
Starting development server at http://0.0.0.0:8000/
```

### Frontend Changes (Static Files)
If you modify CSS/JS:

```bash
docker-compose -f docker-compose.dev.yml exec main python manage.py collectstatic --noinput
```

### Requirements Changes
If you add new Python packages to `requirements.txt`:

```bash
# Rebuild containers
docker-compose -f docker-compose.dev.yml build

# Restart
docker-compose -f docker-compose.dev.yml up
```

---

## 🚨 Troubleshooting

### Port Already in Use (8000)

```bash
# Find what's using port 8000
lsof -i :8000

# Or use different port
# Edit docker-compose.dev.yml: "8001:8000"
```

### Database Connection Issues

```bash
# Check if postgres is running
docker-compose -f docker-compose.dev.yml ps postgres

# Check logs
docker-compose -f docker-compose.dev.yml logs postgres
```

### Container Won't Start

```bash
# View detailed logs
docker-compose -f docker-compose.dev.yml logs service-name

# Force rebuild
docker-compose -f docker-compose.dev.yml build --no-cache service-name

# Remove and recreate
docker-compose -f docker-compose.dev.yml up --force-recreate service-name
```

### Out of Sync Containers

```bash
# Full rebuild
docker-compose -f docker-compose.dev.yml down
docker-compose -f docker-compose.dev.yml build
docker-compose -f docker-compose.dev.yml up
```

---

## 💡 Tips & Best Practices

### 1. Run Services in Background

```bash
# Detached mode
docker-compose -f docker-compose.dev.yml up -d

# Check logs anytime
docker-compose -f docker-compose.dev.yml logs -f
```

### 2. Clean Up Regularly

```bash
# Remove stopped containers
docker-compose -f docker-compose.dev.yml down

# Remove volumes too (fresh DB)
docker-compose -f docker-compose.dev.yml down -v

# Remove unused images
docker image prune
```

### 3. Environment Variables
Create `.env.dev` for development-specific settings:

```bash
DEBUG=1
POSTGRES_DB=traitkeeper_dev
HELIUS_API_KEY=your_dev_key
```

Then use:

```bash
docker-compose -f docker-compose.dev.yml --env-file .env.dev up
```

### 4. Check Service Health

```bash
# View service status (including health)
docker-compose -f docker-compose.dev.yml ps

# Check specific service
docker-compose -f docker-compose.dev.yml ps main
```

---

## 🔄 Development vs Production

| Feature | Development | Production |
|---------|------------|------------|
| Web Server | `runserver` | `gunicorn` |
| Debug Mode | `DEBUG=1` | `DEBUG=0` |
| Hot Reload | ✅ Enabled | ❌ Disabled |
| Healthchecks | ✅ Enabled | ✅ Enabled |
| Volume Mounts | ✅ Code mounted | ❌ Code in image |
| Restart Policy | Default | `unless-stopped` |
| Container Names | `-dev` suffix | Production names |

---

## 🎯 Recommended Setups

### Minimal (Frontend/API Work Only)

```bash
docker-compose -f docker-compose.dev.yml up postgres redis main
```

Only database, cache, and web server.

### Standard (Most Development)

```bash
docker-compose -f docker-compose.dev.yml up
```

All services running - ready for full integration testing.

### Selective Services

```bash
# Web + Live indexer only
docker-compose -f docker-compose.dev.yml up postgres redis main indexer-live

# Web + Vitality only
docker-compose -f docker-compose.dev.yml up postgres redis main vitality-analytics
```

Start only the services you're working on.