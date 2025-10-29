# system_health/urls.py
from django.urls import path
from . import views

app_name = 'system_health'

urlpatterns = [
    # Standard Django view for the dashboard
    path('dashboard/', views.health_dashboard, name='dashboard'),

    # --- API Endpoints ---

    # General system health endpoints
    path('api/health-check/', views.health_check, name='api_health_check'),
    path('api/metrics/', views.health_metrics, name='api_metrics'),

    # Endpoints related to the background task manager
    path('api/tasks/status/', views.health_task_status, name='api_task_status'),
    path('api/tasks/history/', views.health_task_history, name='api_task_history'),
    path('api/tasks/restart/', views.restart_health_monitoring, name='api_restart_tasks'),

    # Ecosystem Health API endpoints
    path('api/ecosystem/latest/', views.ecosystem_health_latest, name='api_ecosystem_latest'),
    path('api/ecosystem/trend/', views.ecosystem_health_trend, name='api_ecosystem_trend'),
    path('api/ecosystem/summary/', views.ecosystem_health_summary, name='api_ecosystem_summary'),

    # System Alerts API endpoints
    path('api/alerts/active/', views.system_alerts_active, name='api_alerts_active'),
    path('api/alerts/<int:alert_id>/resolve/', views.system_alert_resolve, name='api_alert_resolve'),

    # Service Health Checks API endpoints
    path('api/service-checks/', views.service_health_checks, name='api_service_checks'),

    # Performance Metrics API endpoints
    path('api/performance/', views.performance_metrics, name='api_performance_metrics'),

    # Docker Services Status API endpoint
    path('api/services/', views.docker_services_status, name='api_docker_services'),

    # Error Logs API endpoint
    path('api/error-logs/', views.system_error_logs, name='api_error_logs'),
]