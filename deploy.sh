#!/bin/bash

# ============================================================================
# TraitKeeper - One-Click Full Stack Deployment
# ============================================================================
# This script handles complete deployment of all services:
# - Database (PostgreSQL)
# - Cache (Redis)
# - Web Server
# - Live Indexer (optimized with batch processing)
# - Scheduled Indexer (optimized with batch processing)
# - Incremental Indexer
# - Analytics Services
# - Health Monitoring
# ============================================================================

set -e  # Exit on any error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_NAME="traitkeeper"
COMPOSE_FILE="docker-compose.yml"
MAX_RETRIES=30
RETRY_DELAY=2

# ============================================================================
# Helper Functions
# ============================================================================

print_header() {
    echo ""
    echo -e "${BLUE}============================================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}============================================================================${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# ============================================================================
# Pre-Deployment Checks
# ============================================================================

check_prerequisites() {
    print_header "Checking Prerequisites"

    # Check if docker is installed
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    print_success "Docker is installed"

    # Check if docker-compose is installed
    if ! command -v docker-compose &> /dev/null; then
        print_error "docker-compose is not installed. Please install docker-compose first."
        exit 1
    fi
    print_success "docker-compose is installed"

    # Check if .env file exists
    if [ ! -f .env ]; then
        print_error ".env file not found. Please create it first."
        exit 1
    fi
    print_success ".env file exists"

    print_success "All prerequisites met"
}

# ============================================================================
# Deployment Steps
# ============================================================================

pull_latest_code() {
    print_header "Pulling Latest Code from Git"

    # Check if we're in a git repository
    if [ -d .git ]; then
        print_info "Pulling latest changes from main branch..."
        git pull origin main || {
            print_warning "Failed to pull from git. Continuing with local code..."
        }
        print_success "Code updated"
    else
        print_warning "Not a git repository. Skipping git pull."
    fi
}

stop_running_services() {
    print_header "Stopping Running Services"

    print_info "Stopping all containers..."
    docker-compose -f $COMPOSE_FILE down || true
    print_success "All services stopped"
}

build_images() {
    print_header "Building Docker Images"

    print_info "Building fresh Docker images..."
    docker-compose -f $COMPOSE_FILE build --no-cache || {
        print_error "Docker build failed"
        exit 1
    }
    print_success "Docker images built successfully"
}

start_infrastructure() {
    print_header "Starting Infrastructure Services"

    print_info "Starting postgres and redis..."
    docker-compose -f $COMPOSE_FILE up -d postgres redis

    # Wait for postgres to be healthy
    print_info "Waiting for PostgreSQL to be ready..."
    RETRIES=0
    while [ $RETRIES -lt $MAX_RETRIES ]; do
        if docker-compose -f $COMPOSE_FILE ps postgres | grep -q "healthy"; then
            print_success "PostgreSQL is ready"
            break
        fi
        RETRIES=$((RETRIES + 1))
        echo -n "."
        sleep $RETRY_DELAY
    done

    if [ $RETRIES -eq $MAX_RETRIES ]; then
        print_error "PostgreSQL failed to start"
        exit 1
    fi

    # Wait for redis to be healthy
    print_info "Waiting for Redis to be ready..."
    RETRIES=0
    while [ $RETRIES -lt $MAX_RETRIES ]; do
        if docker-compose -f $COMPOSE_FILE ps redis | grep -q "healthy"; then
            print_success "Redis is ready"
            break
        fi
        RETRIES=$((RETRIES + 1))
        echo -n "."
        sleep $RETRY_DELAY
    done

    if [ $RETRIES -eq $MAX_RETRIES ]; then
        print_error "Redis failed to start"
        exit 1
    fi
}

run_migrations() {
    print_header "Running Database Migrations"

    print_info "Running Django migrations..."
    docker-compose -f $COMPOSE_FILE run --rm main python manage.py migrate --noinput || {
        print_error "Database migrations failed"
        exit 1
    }
    print_success "Database migrations completed"
}

start_all_services() {
    print_header "Starting All Services"

    print_info "Starting all services..."
    docker-compose -f $COMPOSE_FILE up -d

    print_success "All services started"
}

health_checks() {
    print_header "Performing Health Checks"

    print_info "Waiting for services to become healthy..."
    sleep 10

    # Check main web service
    print_info "Checking web server..."
    RETRIES=0
    while [ $RETRIES -lt $MAX_RETRIES ]; do
        if docker-compose -f $COMPOSE_FILE ps main | grep -q "healthy"; then
            print_success "Web server is healthy"
            break
        fi
        RETRIES=$((RETRIES + 1))
        echo -n "."
        sleep $RETRY_DELAY
    done

    if [ $RETRIES -eq $MAX_RETRIES ]; then
        print_warning "Web server health check timeout (may still be starting)"
    fi

    # Check indexers
    print_info "Checking indexers..."
    for service in indexer-live indexer-scheduled; do
        if docker-compose -f $COMPOSE_FILE ps $service | grep -q "Up"; then
            print_success "$service is running"
        else
            print_warning "$service is not running"
        fi
    done
}

show_service_status() {
    print_header "Service Status"

    docker-compose -f $COMPOSE_FILE ps

    print_header "Deployment Summary"
    print_success "Deployment completed successfully!"
    echo ""
    print_info "Services:"
    echo "  - Web Server: http://localhost:8000"
    echo "  - PostgreSQL: localhost:5432"
    echo "  - Redis: localhost:6379"
    echo ""
    print_info "View logs:"
    echo "  docker-compose -f $COMPOSE_FILE logs -f [service-name]"
    echo ""
    print_info "Available services:"
    echo "  - main (web server)"
    echo "  - indexer-live (real-time indexer)"
    echo "  - indexer-scheduled (periodic indexer)"
    echo "  - indexer-incremental (catch-up indexer)"
    echo "  - vitality-analytics"
    echo "  - health"
    echo "  - config-listener"
    echo ""
}

# ============================================================================
# Rollback Function
# ============================================================================

rollback() {
    print_header "Rolling Back Deployment"

    print_info "Stopping failed deployment..."
    docker-compose -f $COMPOSE_FILE down

    print_error "Deployment failed. Please check the logs and try again."
    exit 1
}

# ============================================================================
# Main Execution
# ============================================================================

main() {
    print_header "TraitKeeper Full Stack Deployment"

    # Set trap for errors to trigger rollback
    trap rollback ERR

    # Execute deployment steps
    check_prerequisites
    pull_latest_code
    stop_running_services
    build_images
    start_infrastructure
    run_migrations
    start_all_services
    health_checks
    show_service_status

    print_header "Deployment Complete! 🚀"
}

# Run main function
main
