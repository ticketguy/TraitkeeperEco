# This __init__.py is intentionally minimal to avoid Django app loading issues
# Background tasks are started via AppConfig.ready() in individual apps when Django is fully loaded
default_app_config = 'traitkeeper.apps.TraitkeeperConfig'
