# system_health/urls.py
from django.urls import path
from . import views

app_name = 'system_health'

urlpatterns = [
    # Standard Django views
    path('dashboard/', views.health_dashboard, name='dashboard'),
    path('error-logs/', views.error_logs_page, name='error_logs'),

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

    # Transaction Health API endpoint
    path('api/transaction-health/', views.transaction_health, name='api_transaction_health'),

    # Vitality Calculation Metrics API endpoint
    path('api/vitality-metrics/', views.vitality_metrics, name='api_vitality_metrics'),

    # Health Sharing API endpoints (Public & Admin)
    path('api/share/generate/', views.generate_share_token, name='api_generate_share_token'),
    path('api/share/<str:token>/', views.shared_health_stats, name='api_shared_health_stats'),
    path('share/<str:token>/', views.shared_health_page, name='shared_health_page'),

    # Service Uptime Dashboard (QuickNode-style)
    path('uptime/', views.uptime_dashboard, name='uptime_dashboard'),
    path('api/uptime/history/', views.service_uptime_history, name='api_uptime_history'),
    path('api/uptime/summary/', views.service_uptime_summary, name='api_uptime_summary'),
]