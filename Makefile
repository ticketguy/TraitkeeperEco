# ===================================================================
# TraitKeeper Development & Production Management
# ===================================================================

.PHONY: help dev prod down rebuild clean logs migrate shell test

# Default target - show help
help:
	@echo "🚀 TraitKeeper Management Commands"
	@echo ""
	@echo "📦 Environment Management:"
	@echo "  make dev              - Start development environment (all services)"
	@echo "  make prod             - Start production environment (all services)"
	@echo "  make down             - Stop all development containers"
	@echo "  make restart          - Restart all development containers"
	@echo "  make rebuild          - Rebuild development containers without cache"
	@echo "  make clean            - Stop development containers and remove volumes"
	@echo ""
	@echo "🔧 Service Management:"
	@echo "  make dev-minimal      - Start only DB, Redis, and Web (minimal dev setup)"
	@echo "  make dev-web          - Start web server only (assumes DB/Redis running)"
	@echo "  make dev-indexing     - Start web + both indexers"
	@echo "  make dev-analytics    - Start web + vitality analytics"
	@echo ""
	@echo "📊 Individual Services:"
	@echo "  make start-live       - Start live indexer"
	@echo "  make start-scheduled  - Start scheduled indexer"
	@echo "  make start-vitality   - Start vitality analytics"
	@echo "  make start-health     - Start health monitoring"
	@echo "  make restart-live     - Restart live indexer"
	@echo "  make restart-scheduled - Restart scheduled indexer"
	@echo "  make restart-vitality - Restart vitality analytics"
	@echo ""
	@echo "📋 Logs & Monitoring:"
	@echo "  make logs             - View logs for all development services"
	@echo "  make logs-web         - View web server logs"
	@echo "  make logs-live        - View live indexer logs"
	@echo "  make logs-scheduled   - View scheduled indexer logs"
	@echo "  make logs-vitality    - View vitality analytics logs"
	@echo "  make logs-health      - View health monitor logs"
	@echo "  make logs-config      - View config listener logs"
	@echo "  make status           - Show status of all development containers"
	@echo ""
	@echo "🗄️  Database & Migrations:"
	@echo "  make migrate          - Run Django migrations (on dev)"
	@echo "  make makemigrations   - Create new migrations (on dev)"
	@echo "  make shell            - Open Django shell (on dev)"
	@echo "  make dbshell          - Open PostgreSQL shell (on dev)"
	@echo "  make redis-cli        - Open Redis CLI (on dev)"
	@echo ""
	@echo "🧪 Testing & Debugging:"
	@echo "  make test             - Run Django tests (on dev)"
	@echo "  make bash             - Open bash in main container (on dev)"
	@echo "  make collectstatic    - Collect static files (on dev)"
	@echo ""
	@echo "🧰 Utility Commands:"
	@echo "  make superuser        - Create a superuser (on dev)"
	@echo "  make admin-superuser  - Create an admin superuser (on dev)"
	@echo "  make flush            - Flush database (on dev)"
	@echo "  make calc-vitality    - Manually trigger vitality calculation (on dev)"
	@echo "  make calc-vitality-collection - Manually trigger vitality for one collection (on dev)"
	@echo "  make settings         - Show Django settings (on dev)"
	@echo "  make check            - Run Django deployment check (on dev)"
	@echo ""
	@echo "🐳 Docker Maintenance:"
	@echo "  make stats            - View resource usage"
	@echo "  make prune            - Remove unused Docker resources"
	@echo "  make clean-containers - Remove all stopped containers"
	@echo "  make clean-volumes    - Remove unused volumes"
	@echo "  make clean-images     - Remove unused images"


# ===================================================================
# ENVIRONMENT MANAGEMENT
# ===================================================================

# Development environment (all services)
dev:
	docker compose -f docker compose.dev.yml up --build

# Development environment in background
dev-bg:
	docker compose -f docker compose.dev.yml up -d --build

# Production environment
prod:
	docker compose -f docker compose.yml up -d --build

# Stop all development containers
down:
	docker compose -f docker compose.dev.yml down

# Restart all development containers
restart:
	docker compose -f docker compose.dev.yml restart

# Rebuild development containers without cache
rebuild:
	docker compose -f docker compose.dev.yml build --no-cache

# Clean everything (including development volumes)
clean:
	docker compose -f docker compose.dev.yml down -v
	docker system prune -f

# ===================================================================
# SELECTIVE SERVICE STARTUP
# ===================================================================

# Minimal dev setup (DB + Redis + Web only)
dev-minimal:
	docker compose -f docker compose.dev.yml up -d postgres redis main

# Web server only
dev-web:
	docker compose -f docker compose.dev.yml up -d main

# Web + both indexers
dev-indexing:
	docker compose -f docker compose.dev.yml up -d postgres redis main indexer-live indexer-scheduled

# Web + analytics
dev-analytics:
	docker compose -f docker compose.dev.yml up -d postgres redis main vitality-analytics

# ===================================================================
# INDIVIDUAL SERVICE MANAGEMENT
# ===================================================================

# Start individual services
start-live:
	docker compose -f docker compose.dev.yml up -d indexer-live

start-scheduled:
	docker compose -f docker compose.dev.yml up -d indexer-scheduled

start-vitality:
	docker compose -f docker compose.dev.yml up -d vitality-analytics

start-health:
	docker compose -f docker compose.dev.yml up -d health

# Restart individual services
restart-live:
	docker compose -f docker compose.dev.yml restart indexer-live

restart-scheduled:
	docker compose -f docker compose.dev.yml restart indexer-scheduled

restart-vitality:
	docker compose -f docker compose.dev.yml restart vitality-analytics

restart-health:
	docker compose -f docker compose.dev.yml restart health

restart-web:
	docker compose -f docker compose.dev.yml restart main

# ===================================================================
# LOGS & MONITORING
# ===================================================================

# View all logs
logs:
	docker compose -f docker compose.dev.yml logs -f

# View specific service logs
logs-web:
	docker compose -f docker compose.dev.yml logs -f main

logs-live:
	docker compose -f docker compose.dev.yml logs -f indexer-live

logs-scheduled:
	docker compose -f docker compose.dev.yml logs -f indexer-scheduled

logs-vitality:
	docker compose -f docker compose.dev.yml logs -f vitality-analytics

logs-health:
	docker compose -f docker compose.dev.yml logs -f health

logs-config:
	docker compose -f docker compose.dev.yml logs -f config-listener

# Show container status
status:
	docker compose -f docker compose.dev.yml ps

# ===================================================================
# DATABASE & MIGRATIONS
# ===================================================================

# Run migrations
migrate:
	docker compose -f docker compose.dev.yml exec main python manage.py migrate

# Create new migrations
makemigrations:
	docker compose -f docker compose.dev.yml exec main python manage.py makemigrations

# Django shell
shell:
	docker compose -f docker compose.dev.yml exec main python manage.py shell

# PostgreSQL shell
dbshell:
	docker compose -f docker compose.dev.yml exec postgres psql -U ${POSTGRES_USER} -d ${POSTGRES_DB}

# Redis CLI
redis-cli:
	docker compose -f docker compose.dev.yml exec redis redis-cli

# ===================================================================
# TESTING & DEBUGGING
# ===================================================================

# Run tests
test:
	docker compose -f docker compose.dev.yml exec main python manage.py test

# Bash shell in main container
bash:
	docker compose -f docker compose.dev.yml exec main bash

# Collect static files
collectstatic:
	docker compose -f docker compose.dev.yml exec main python manage.py collectstatic --noinput

# ===================================================================
# UTILITY COMMANDS
# ===================================================================

# Create admin superuser
admin-superuser:
	docker compose -f docker compose.dev.yml exec main python manage.py createadminsuperuser

# Create superuser
superuser:
	docker compose -f docker compose.dev.yml exec main python manage.py createsuperuser

# Flush database
flush:
	docker compose -f docker compose.dev.yml exec main python manage.py flush --noinput

# Calculate vitality (manual trigger)
calc-vitality:
	docker compose -f docker compose.dev.yml exec main python manage.py calculate_vitality --all

# Calculate vitality for specific collection
calc-vitality-collection:
	@read -p "Enter collection address: " addr; \
	docker compose -f docker compose.dev.yml exec main python manage.py calculate_vitality --collection $$addr

# Show Django settings
settings:
	docker compose -f docker compose.dev.yml exec main python manage.py diffsettings

# Check deployment
check:
	docker compose -f docker compose.dev.yml exec main python manage.py check --deploy

# ===================================================================
# DOCKER MAINTENANCE
# ===================================================================

# View resource usage
stats:
	docker stats

# Remove unused Docker resources
prune:
	docker system prune -f

# Remove all stopped containers
clean-containers:
	docker container prune -f

# Remove unused volumes
clean-volumes:
	docker volume prune -f

# Remove unused images
clean-images:
	docker image prune -f