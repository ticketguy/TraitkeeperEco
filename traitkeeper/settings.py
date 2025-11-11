"""
Django settings for the TraitKeeper project.

This file contains all the configuration settings for the Django project, including
database connections, installed apps, middleware, authentication backends, and more.
Settings are grouped into sections for better organization and readability.
"""

import sys
import os
from pathlib import Path
from dotenv import load_dotenv


# Build paths inside the project like this: BASE_DIR / 'subdir'.
# BASE_DIR points to the root directory of the project.
BASE_DIR = Path(__file__).resolve().parent.parent

# ----------------------------------------------------------------------------- 
# Environment Variables
# -----------------------------------------------------------------------------

# Only load .env file if running locally (not in Docker)
# In Docker, environment variables are set by docker-compose.yml
if os.path.exists(os.path.join(BASE_DIR, '.env')):
    load_dotenv(os.path.join(BASE_DIR, '.env'))
    print("✅ Loaded .env file")
else:
    print("ℹ️  Running in Docker - using environment variables from docker-compose")

# Helper function to convert string to boolean
def str_to_bool(value):
    """Convert string to boolean"""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).lower() in ('true', '1', 'yes', 'on')

# -----------------------------------------------------------------------------
# Migration Check
# -----------------------------------------------------------------------------
MIGRATING = 'migrate' in sys.argv

# -----------------------------------------------------------------------------
# Security Settings
# -----------------------------------------------------------------------------

# SECURITY WARNING: Keep the secret key used in production secret!
# This key is used for cryptographic signing. In production, it should be a securely generated value.
SECRET_KEY = os.getenv('SECRET_KEY', '')

# --- PROGRAM AUTHORITY KEY ---
# This is the 64-byte private key used to sign transactions originating from the server
# (e.g., configuring the Quest program).
PROGRAM_AUTHORITY_PRIVATE_KEY_B58 = os.getenv('PROGRAM_AUTHORITY_PRIVATE_KEY_B58', '')

# SECURITY WARNING: Don't run with debug turned on in production!
# Debug mode provides detailed error pages, which can expose sensitive information.
DEBUG = str_to_bool(os.getenv('DEBUG', 'True'))

# Allowed hosts for the application.
# In production, add your domain names (e.g., 'example.com', 'www.example.com').
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# Secure SSL settings for production.
# Ensures requests are redirected to HTTPS. Set to True in production.
SECURE_SSL_REDIRECT = str_to_bool(os.getenv('SECURE_SSL_REDIRECT', 'False'))

# Indicates that the app is behind a proxy and what header to trust for HTTPS.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# CSRF trusted origins for production (for AJAX requests)
CSRF_TRUSTED_ORIGINS = os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',') if os.getenv('CSRF_TRUSTED_ORIGINS') else []

# Additional security headers for production
if not DEBUG:
    # HTTP Strict Transport Security (HSTS)
    SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', '31536000'))  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = str_to_bool(os.getenv('SECURE_HSTS_INCLUDE_SUBDOMAINS', 'True'))
    SECURE_HSTS_PRELOAD = str_to_bool(os.getenv('SECURE_HSTS_PRELOAD', 'True'))

    # Additional security headers
    SECURE_CONTENT_TYPE_NOSNIFF = str_to_bool(os.getenv('SECURE_CONTENT_TYPE_NOSNIFF', 'True'))
    SECURE_BROWSER_XSS_FILTER = str_to_bool(os.getenv('SECURE_BROWSER_XSS_FILTER', 'True'))
    X_FRAME_OPTIONS = os.getenv('X_FRAME_OPTIONS', 'DENY')

    # Cookie security
    SESSION_COOKIE_SAMESITE = os.getenv('SESSION_COOKIE_SAMESITE', 'Lax')
    CSRF_COOKIE_SAMESITE = os.getenv('CSRF_COOKIE_SAMESITE', 'Lax')

# -----------------------------------------------------------------------------
# Application Definition
# -----------------------------------------------------------------------------

# List of installed Django apps, third-party apps, and project-specific apps.
INSTALLED_APPS = [
    # Django Core Apps
    'django.contrib.admin',           # Admin interface
    'django.contrib.auth',            # Authentication system
    'django.contrib.contenttypes',    # Content types framework
    'django.contrib.sessions',        # Session management
    'django.contrib.messages',        # Messaging framework
    'django.contrib.staticfiles',     # Static files management
    'django.contrib.sites',           # Required by django-allauth for multi-site support

    # Project-Specific Apps
    'admin_panel.apps.AdminPanelConfig',  # Admin panel app
    'wallet',                    # Wallet management app
    'profiles',                  # User profiles app
    'core',                      # Core utilities and services
#    'learn',                     # Learn app
    'analytics',                 # Analytics app
    'nft_data',                  # NFT data management app
    'nftmemories',               # NFT memories app
    'marketplace',               # Marketplace app
    'system_health',             # System health monitoring app
    'admin_secure',              # Secure encrypted storage for sensitive credentials
    "advertisement",             # Advertisement app
    'indexer',                   # Indexer app for blockchain data
    'notifications',             # Notifications app
    'traitkeeper',               # Main app for TraitKeeper

    # Django-Allauth Apps (for social authentication)
    'allauth',                   # Core allauth app
    'allauth.account',           # Account management
    'allauth.socialaccount',     # Social account integration
    'allauth.socialaccount.providers.google',  # Google OAuth provider

    # Third-Party Apps
    'import_export',             # Data import/export functionality
    'webpush',                   # Web push notifications
    'django_admin_listfilter_dropdown',  # Dropdown filters in admin
    'corsheaders',               # CORS headers support
    'rest_framework',            # REST API framework
    'rest_framework.authtoken',  # Token authentication for REST API
    'drf_spectacular',           # API schema generation
    'channels',                  # WebSocket support
]

# Site ID for django-allauth (required for multi-site support).
SITE_ID = int(os.getenv('SITE_ID', '1'))

# -----------------------------------------------------------------------------
# Authentication Settings
# -----------------------------------------------------------------------------

# Custom user model for regular users (replaces Django's default User model).
AUTH_USER_MODEL = 'wallet.CustomUser'

# Custom user model for admin users (used in the admin panel).
ADMIN_USER_MODEL = 'admin_panel.AdminUser'

# Authentication backends for different user types and allauth.
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',   # Default Django authentication
    'allauth.account.auth_backends.AuthenticationBackend',  # Django-allauth backend for social auth
    'wallet.auth_backends.CustomAuthBackend',     # Custom backend for wallet users (CustomUser)
    'admin_panel.auth_backends.AdminAuthBackend',  # Custom backend for admin users (AdminUser)
]

# REST Framework settings for API authentication, permissions, and throttling.
REST_FRAMEWORK = {
    # Authentication classes for API requests.
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'traitkeeper.authentication.ExpiringTokenAuthentication',  # Custom token authentication with expiry
        'rest_framework.authentication.TokenAuthentication',      # Standard token authentication
        'rest_framework.authentication.SessionAuthentication',    # Session authentication (useful for admin)
    ],
    # Specify the custom token model for REST Framework.
    'DEFAULT_AUTH_TOKEN_MODEL': 'traitkeeper.Token',
    # Permission classes for API endpoints.
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',  # Require authentication by default
    ],
    # Throttling to limit API request rates.
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',  # For anonymous users
        'rest_framework.throttling.UserRateThrottle',  # For authenticated users
    ],
    # Throttle rates for anonymous and authenticated users.
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',  # 100 requests per hour for anonymous users
        'user': '500/hour',  # 500 requests per hour for authenticated users
    },
    # API schema generation using drf-spectacular.
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    # Re-specify the token model for clarity.
    'TOKEN_MODEL': 'traitkeeper.Token',
}

# -----------------------------------------------------------------------------
# Middleware
# -----------------------------------------------------------------------------

# Middleware classes that process requests and responses.
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',        # Security enhancements
    'django.contrib.sessions.middleware.SessionMiddleware', # Session management
    'corsheaders.middleware.CorsMiddleware',                # CORS headers for cross-origin requests
    'django.middleware.common.CommonMiddleware',            # Common middleware for request/response handling
    'django.middleware.csrf.CsrfViewMiddleware',            # CSRF protection
    'django.contrib.auth.middleware.AuthenticationMiddleware',  # Authentication support
    'django.contrib.messages.middleware.MessageMiddleware', # Messaging framework
    'django.middleware.clickjacking.XFrameOptionsMiddleware',  # Clickjacking protection
    'allauth.account.middleware.AccountMiddleware',         # Django-allauth middleware
]

# -----------------------------------------------------------------------------
# URL Configuration
# -----------------------------------------------------------------------------

# Root URL configuration file for the project.
ROOT_URLCONF = 'traitkeeper.urls'

# -----------------------------------------------------------------------------
# Templates
# -----------------------------------------------------------------------------

# Template engine configuration.
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',  # Use Django's template engine
        'DIRS': [BASE_DIR / 'templates'],  # Custom template directory
        'APP_DIRS': True,  # Enable template loading from app directories
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',         # Debug context
                'django.template.context_processors.request',      # Request context
                'django.contrib.auth.context_processors.auth',     # Authentication context
                'django.contrib.messages.context_processors.messages',  # Messages context
            ],
            'libraries': {
                'admin_extras': 'admin_panel.templatetags.admin_extras',  # Custom template tags
            },
        },
    },
]

# -----------------------------------------------------------------------------
# WSGI and ASGI Applications
# -----------------------------------------------------------------------------

# WSGI application for traditional HTTP requests.
WSGI_APPLICATION = 'traitkeeper.wsgi.application'

# Channels configuration for WebSocket support.
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",  # Use Redis for WebSocket channels
        "CONFIG": {
            "hosts": [os.getenv('REDIS_CHANNEL_URL', 'redis://localhost:6379/1')],  
        },
    },
}

# -----------------------------------------------------------------------------
# Database Configuration
# -----------------------------------------------------------------------------

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('POSTGRES_DB'),
        'USER': os.getenv('POSTGRES_USER'),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD'),
        'HOST': os.getenv('POSTGRES_HOST'),
        'PORT': os.getenv('POSTGRES_PORT'),
    }
}

# -----------------------------------------------------------------------------
# Password Validation
# -----------------------------------------------------------------------------

# Password validation rules for user passwords.
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',  # Prevents passwords similar to user attributes
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',  # Enforces minimum password length
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',  # Prevents common passwords
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',  # Prevents fully numeric passwords
    },
]

# -----------------------------------------------------------------------------
# Session Settings
# -----------------------------------------------------------------------------

# Session engine and settings.
SESSION_ENGINE = 'django.contrib.sessions.backends.db'  # Store sessions in the database
SESSION_COOKIE_AGE = int(os.getenv('SESSION_COOKIE_AGE', '1209600'))  # Session duration: 2 weeks in seconds
SESSION_COOKIE_SECURE = str_to_bool(os.getenv('SESSION_COOKIE_SECURE', 'False'))  # Set to True in production to ensure cookies are sent over HTTPS
SESSION_COOKIE_HTTPONLY = True  # Prevent JavaScript access to session cookies
SESSION_EXPIRE_AT_BROWSER_CLOSE = str_to_bool(os.getenv('SESSION_EXPIRE_AT_BROWSER_CLOSE', 'False'))  # Keep sessions for SESSION_COOKIE_AGE duration (2 weeks)
CSRF_COOKIE_SECURE = str_to_bool(os.getenv('CSRF_COOKIE_SECURE', 'False'))  # Set to True in production for secure CSRF cookies
CSRF_COOKIE_HTTPONLY = True  # Prevent JavaScript access to CSRF cookies

# -----------------------------------------------------------------------------
# Background Task Settings
# -----------------------------------------------------------------------------

BACKGROUND_TASKS = {
    'MAX_WORKERS': int(os.getenv('BACKGROUND_TASK_MAX_WORKERS', '4')),
    'BUFFER_TIMEOUT': int(os.getenv('BACKGROUND_TASK_BUFFER_TIMEOUT', '5')),  # seconds
    'RETRY_DELAY': int(os.getenv('BACKGROUND_TASK_RETRY_DELAY', '120')),  # seconds
    'MAX_RETRIES': int(os.getenv('BACKGROUND_TASK_MAX_RETRIES', '3')),
}

# -----------------------------------------------------------------------------
# Internationalization
# -----------------------------------------------------------------------------

# Language and timezone settings.
LANGUAGE_CODE = 'en-us'  # Default language
TIME_ZONE = 'UTC'        # Default timezone
USE_I18N = True          # Enable internationalization
USE_TZ = True            # Enable timezone support

# -----------------------------------------------------------------------------
# Static and Media Files
# -----------------------------------------------------------------------------

# Static files configuration (CSS, JavaScript, images).
STATIC_URL = os.getenv('STATIC_URL', 'static/')  # URL prefix for static files
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]  # Directories for static files
STATIC_ROOT = BASE_DIR / "staticfiles"  # Directory for collected static files in production

# Media files configuration (user-uploaded files).
MEDIA_URL = os.getenv('MEDIA_URL', 'media/')  # URL prefix for media files
MEDIA_ROOT = BASE_DIR / 'media'  # Directory for media files

# -----------------------------------------------------------------------------
# Default Primary Key Field Type
# -----------------------------------------------------------------------------

# Default primary key type for models.
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# -----------------------------------------------------------------------------
# CORS Settings
# -----------------------------------------------------------------------------

# CORS (Cross-Origin Resource Sharing) settings for API access.
CORS_ALLOWED_ORIGINS = os.getenv(
    'CORS_ALLOWED_ORIGINS',
    'https://cdnjs.cloudflare.com,https://api.mainnet-beta.solana.com,http://localhost:8085'
).split(',')

CORS_ALLOW_CREDENTIALS = str_to_bool(os.getenv('CORS_ALLOW_CREDENTIALS', 'True'))  # Allow credentials (e.g., cookies) in cross-origin requests
CORS_ALLOW_ALL_CREDENTIALS = False  # Explicitly disable allowing all credentials

# Allowed headers in CORS requests.
CORS_ALLOW_HEADERS = [
    'content-type',
    'authorization',
    'x-csrf-token',
]

# -----------------------------------------------------------------------------
# Django-Allauth Configuration
# -----------------------------------------------------------------------------

# Django-allauth settings for authentication.
ACCOUNT_LOGIN_METHODS = {'email'}  # Allow login via email only
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']  # Required fields for signup
ACCOUNT_EMAIL_VERIFICATION = 'none'  # Disable email verification for simplicity
ACCOUNT_AUTO_SIGNUP = True  # Automatically sign up users after social login
ACCOUNT_EMAIL_AUTHENTICATION = True  # Allow authentication via email
SOCIALACCOUNT_LOGIN_ON_GET = True  # Allow social login without POST request

# Google OAuth settings for social login.
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': os.getenv('GOOGLE_OAUTH_CLIENT_ID', ''),  # Google OAuth client ID
            'secret': os.getenv('GOOGLE_OAUTH_SECRET', ''),  # Google OAuth secret
            'key': ''  # Not used for Google provider
        },
        'SCOPE': [
            'profile',  # Access user profile information
            'email',    # Access user email
        ],
        'AUTH_PARAMS': {
            'access_type': 'online',  # Use online access for OAuth
        }
    }
}

# -----------------------------------------------------------------------------
# Solana RPC Configuration (Commented Out)
# -----------------------------------------------------------------------------

# API keys and endpoints for Solana RPC providers (commented out for reference).
HELIUS_API_KEY = os.getenv('HELIUS_API_KEY')
QUICKNODE_API_KEY = os.getenv('QUICKNODE_API_KEY')
QUICKNODE_ENDPOINT = os.getenv('QUICKNODE_ENDPOINT')
SOLANA_RPC_URL = os.getenv('SOLANA_RPC_URL')
PRIMARY_RPC_PROVIDER = os.getenv('PRIMARY_RPC_PROVIDER')

# -----------------------------------------------------------------------------
# Caching Configuration
# -----------------------------------------------------------------------------
"""
# Caching configuration using local memory cache.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',  # Use local memory cache
        'LOCATION': 'unique-snowflake',  # Unique identifier for the cache
    }
}

"""

REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# And caching configuration to use Redis:
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

# -----------------------------------------------------------------------------
# Cache Manager Configuration
# -----------------------------------------------------------------------------

# Cache Manager Settings - Centralized cache coordination with priority-based TTLs
CACHE_MANAGER = {
    # Enable cache manager logging for debugging
    'DEBUG_LOGGING': str_to_bool(os.getenv('CACHE_DEBUG_LOGGING', str(DEBUG))),  # Set to False in production
    
    # Collection priority settings - these map to your NFTCollection.priority_tier field
    'COLLECTION_PRIORITIES': {
        'VIP': {
            'min_volume_24h': float(os.getenv('VIP_MIN_VOLUME_24H', '100.0')),  # SOL
            'min_holder_count': int(os.getenv('VIP_MIN_HOLDER_COUNT', '1000')),
            'featured_threshold': str_to_bool(os.getenv('VIP_FEATURED_THRESHOLD', 'True'))
        },
        'ACTIVE': {
            'min_volume_24h': float(os.getenv('ACTIVE_MIN_VOLUME_24H', '10.0')),   # SOL
            'min_holder_count': int(os.getenv('ACTIVE_MIN_HOLDER_COUNT', '100')),
            'featured_threshold': str_to_bool(os.getenv('ACTIVE_FEATURED_THRESHOLD', 'False'))
        },
        'INACTIVE': {
            'max_days_since_activity': int(os.getenv('INACTIVE_MAX_DAYS_SINCE_ACTIVITY', '30')),
            'max_volume_24h': float(os.getenv('INACTIVE_MAX_VOLUME_24H', '10.0'))    # SOL
        }
    },
    
    # TTL Configuration by Priority (in seconds)
    'TTL_CONFIG': {
        'VIP': {
            'STATS': int(os.getenv('CACHE_VIP_STATS_TTL', '300')),      # 5 minutes - high activity collections
            'PROVIDER': int(os.getenv('CACHE_VIP_PROVIDER_TTL', '600')),   # 10 minutes - Magic Eden, Tensor data
            'METRICS': int(os.getenv('CACHE_VIP_METRICS_TTL', '900')),    # 15 minutes - analytics data
            'GLOBAL': int(os.getenv('CACHE_VIP_GLOBAL_TTL', '1800')),    # 30 minutes - featured collections
            'RATE_LIMIT': int(os.getenv('CACHE_VIP_RATE_LIMIT_TTL', '300'))  # 5 minutes - quota tracking
        },
        'ACTIVE': {
            'STATS': int(os.getenv('CACHE_ACTIVE_STATS_TTL', '1800')),     # 30 minutes - medium activity
            'PROVIDER': int(os.getenv('CACHE_ACTIVE_PROVIDER_TTL', '3600')),  # 1 hour - provider data
            'METRICS': int(os.getenv('CACHE_ACTIVE_METRICS_TTL', '7200')),   # 2 hours - analytics
            'GLOBAL': int(os.getenv('CACHE_ACTIVE_GLOBAL_TTL', '7200')),    # 2 hours - global data
            'RATE_LIMIT': int(os.getenv('CACHE_ACTIVE_RATE_LIMIT_TTL', '1800'))  # 30 minutes - quota tracking
        },
        'INACTIVE': {
            'STATS': int(os.getenv('CACHE_INACTIVE_STATS_TTL', '14400')),    # 4 hours - low activity
            'PROVIDER': int(os.getenv('CACHE_INACTIVE_PROVIDER_TTL', '21600')), # 6 hours - provider data
            'METRICS': int(os.getenv('CACHE_INACTIVE_METRICS_TTL', '86400')),  # 24 hours - analytics
            'GLOBAL': int(os.getenv('CACHE_INACTIVE_GLOBAL_TTL', '21600')),   # 6 hours - global data
            'RATE_LIMIT': int(os.getenv('CACHE_INACTIVE_RATE_LIMIT_TTL', '3600'))  # 1 hour - quota tracking
        }
    },
    
    # Cache dependency invalidation settings
    'DEPENDENCY_CONFIG': {
        'MAX_CASCADE_DEPTH': int(os.getenv('CACHE_MAX_CASCADE_DEPTH', '3')),        # Maximum dependency cascade levels
        'BATCH_INVALIDATION_SIZE': int(os.getenv('CACHE_BATCH_INVALIDATION_SIZE', '50')), # Process invalidations in batches
        'INVALIDATION_TIMEOUT': int(os.getenv('CACHE_INVALIDATION_TIMEOUT', '30'))     # Timeout for invalidation operations (seconds)
    },
    
    # Cache warming settings
    'CACHE_WARMING': {
        'ENABLED': str_to_bool(os.getenv('CACHE_WARMING_ENABLED', 'True')),
        'VIP_WARM_INTERVAL': int(os.getenv('CACHE_VIP_WARM_INTERVAL', '7200')),     # Warm VIP caches every 2 hours
        'WARM_ON_STARTUP': str_to_bool(os.getenv('CACHE_WARM_ON_STARTUP', 'True')),       # Warm important caches on application startup
        'MAX_CONCURRENT_WARMING': int(os.getenv('CACHE_MAX_CONCURRENT_WARMING', '5'))    # Max concurrent cache warming operations
    },
    
    # Monitoring and alerting
    'MONITORING': {
        'TRACK_CACHE_HITS': True,      # Track cache hit/miss ratios
        'TRACK_INVALIDATIONS': True,   # Track cache invalidation statistics
        'ALERT_ON_HIGH_MISS_RATE': 0.3, # Alert if cache miss rate > 30%
        'PERFORMANCE_LOGGING': str_to_bool(os.getenv('CACHE_DEBUG_LOGGING', str(DEBUG)))    # Log cache operation performance
    }
}

# Redis-specific cache manager settings
CACHE_MANAGER_REDIS = {
    'CONNECTION_POOL_SIZE': int(os.getenv('REDIS_CONNECTION_POOL_SIZE', '10')),        # Redis connection pool size
    'SOCKET_TIMEOUT': int(os.getenv('REDIS_SOCKET_TIMEOUT', '5')),               # Socket timeout in seconds
    'RETRY_ON_TIMEOUT': str_to_bool(os.getenv('REDIS_RETRY_ON_TIMEOUT', 'True')),          # Retry on Redis timeout
    'DECODE_RESPONSES': True,          # Automatically decode Redis responses
    'HEALTH_CHECK_INTERVAL': int(os.getenv('REDIS_HEALTH_CHECK_INTERVAL', '60'))        # Check Redis health every 60 seconds
}

# Cache key prefixes for organization (prevents collisions)
CACHE_KEY_PREFIXES = {
    'COLLECTION_STATS': 'cs',          # Collection statistics
    'PROVIDER_DATA': 'pd',             # Magic Eden, Tensor data
    'TRAIT_METRICS': 'tm',             # Trait analytics
    'NFT_METADATA': 'nm',              # NFT metadata
    'USER_DATA': 'ud',                 # User-specific data
    'GLOBAL_STATS': 'gs',              # Global/site-wide statistics
    'RATE_LIMITS': 'rl',               # Rate limiting data
    'DEPENDENCIES': 'dep'              # Dependency tracking
}

# Background task integration with cache manager
BACKGROUND_TASKS_CACHE = {
    'INVALIDATE_ON_COMPLETION': True,   # Invalidate relevant caches after background tasks
    'CACHE_TASK_RESULTS': True,        # Cache background task results
    'TASK_RESULT_TTL': 3600,           # Cache task results for 1 hour
    'FAILED_TASK_RETRY_DELAY': 300     # Retry failed cache operations after 5 minutes
}

# Provider-specific cache settings
PROVIDER_CACHE_CONFIG = {
    'MAGIC_EDEN': {
        'DEFAULT_TTL': int(os.getenv('MAGIC_EDEN_DEFAULT_TTL', '900')),             # 15 minutes default TTL
        'COLLECTION_DATA_TTL': int(os.getenv('MAGIC_EDEN_COLLECTION_TTL', '1800')),    # 30 minutes for collection data
        'ACTIVITY_DATA_TTL': int(os.getenv('MAGIC_EDEN_ACTIVITY_TTL', '300')),       # 5 minutes for recent activity
        'SLUG_CACHE_TTL': int(os.getenv('MAGIC_EDEN_SLUG_CACHE_TTL', '604800'))        # 7 days for ME slugs
    },
    'TENSOR': {
        'DEFAULT_TTL': int(os.getenv('TENSOR_DEFAULT_TTL', '900')),             # 15 minutes default TTL
        'UUID_CACHE_TTL': int(os.getenv('TENSOR_UUID_CACHE_TTL', '86400')),        # 24 hours for Tensor UUIDs
        'COLLECTION_DATA_TTL': int(os.getenv('TENSOR_COLLECTION_TTL', '1800')),    # 30 minutes for collection data
        'ACTIVITY_DATA_TTL': int(os.getenv('TENSOR_ACTIVITY_TTL', '300'))        # 5 minutes for recent activity
    },
    'BLOCKCHAIN': {
        'TRANSACTION_TTL': int(os.getenv('BLOCKCHAIN_TRANSACTION_TTL', '1800')),        # 30 minutes for transaction data
        'METADATA_TTL': int(os.getenv('BLOCKCHAIN_METADATA_TTL', '3600')),           # 1 hour for NFT metadata
        'EVENT_DATA_TTL': int(os.getenv('BLOCKCHAIN_EVENT_DATA_TTL', '600'))           # 10 minutes for event data
    }
}

# Cache manager error handling
CACHE_MANAGER_ERROR_HANDLING = {
    'FALLBACK_TO_DB_ON_CACHE_FAIL': True,  # Fall back to database if cache fails
    'LOG_CACHE_ERRORS': True,              # Log cache operation errors
    'CONTINUE_ON_CACHE_ERROR': True,       # Don't break app flow on cache errors
    'CACHE_ERROR_ALERT_THRESHOLD': 10      # Alert after 10 consecutive cache errors
}

# Development/Debug settings (disable in production)
if DEBUG:
    CACHE_MANAGER['DEBUG_LOGGING'] = True
    CACHE_MANAGER['MONITORING']['PERFORMANCE_LOGGING'] = True
    # Shorter TTLs for faster development iteration
    CACHE_MANAGER['TTL_CONFIG']['VIP']['STATS'] = 60    # 1 minute in development
    CACHE_MANAGER['TTL_CONFIG']['ACTIVE']['STATS'] = 300 # 5 minutes in development
else:
    # Production optimizations
    CACHE_MANAGER['DEBUG_LOGGING'] = False
    CACHE_MANAGER['MONITORING']['PERFORMANCE_LOGGING'] = False
    # Enable connection pooling for better performance
    CACHE_MANAGER_REDIS['CONNECTION_POOL_SIZE'] = 20

# Export cache configuration for use by cache_manager.py
def get_cache_manager_config():
    """Get cache manager configuration for import by cache_manager.py"""
    return {
        'ttl_config': CACHE_MANAGER['TTL_CONFIG'],
        'dependency_config': CACHE_MANAGER['DEPENDENCY_CONFIG'],
        'cache_warming': CACHE_MANAGER['CACHE_WARMING'],
        'monitoring': CACHE_MANAGER['MONITORING'],
        'key_prefixes': CACHE_KEY_PREFIXES,
        'provider_config': PROVIDER_CACHE_CONFIG,
        'redis_config': CACHE_MANAGER_REDIS,
        'error_handling': CACHE_MANAGER_ERROR_HANDLING
    }

# -----------------------------------------------------------------------------
# URL Redirects
# -----------------------------------------------------------------------------

# Redirect URLs for login, logout, and admin actions.
LOGIN_REDIRECT_URL = '/'  # Redirect to homepage for non-admin users after login
LOGIN_URL = 'admin_panel:login'  # Admin login URL
LOGOUT_REDIRECT_URL = 'admin_panel:login'  # Redirect to admin login after logout

# -----------------------------------------------------------------------------
# Email Configuration
# -----------------------------------------------------------------------------

# Email backend for sending emails.
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')  # SMTP host
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))  # SMTP port for SSL
EMAIL_USE_TLS = str_to_bool(os.getenv('EMAIL_USE_TLS', 'True'))  # Disable TLS since we're using SSL
EMAIL_USE_SSL = str_to_bool(os.getenv('EMAIL_USE_SSL', 'False'))  # Enable SSL for Gmail SMTP
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')  # Gmail address for sending emails
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')  # App-specific password for Gmail
DEFAULT_FROM_EMAIL = os.getenv('EMAIL_HOST_USER', 'noreply@traitkeeper.com')  # Default sender email


# -----------------------------------------------------------------------------
# Background Task Logging Configuration
# -----------------------------------------------------------------------------

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': os.getenv('LOG_LEVEL', 'INFO'),
            'class': 'logging.FileHandler',
            'filename': os.getenv('LOG_FILE_PATH', 'background_tasks.log'),
            'formatter': 'verbose',
        },
        'console': {
            'level': os.getenv('LOG_LEVEL', 'INFO'),
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'indexer.background_task_manager': {
            'handlers': ['file', 'console'],
            'level': os.getenv('LOG_LEVEL', 'INFO'),
            'propagate': True,
        },
        'indexer.services': {
            'handlers': ['file', 'console'],
            'level': os.getenv('LOG_LEVEL', 'INFO'),
            'propagate': True,
        },
        'nft_data.services': {
            'handlers': ['file', 'console'],
            'level': os.getenv('LOG_LEVEL', 'INFO'),
            'propagate': True,
        },
        'core.api_provider.quicknode_provider': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': True,
        },
    },
}

# -----------------------------------------------------------------------------
# Webpush Settings
# -----------------------------------------------------------------------------

# Webpush settings for push notifications.
WEBPUSH_SETTINGS = {
    "VAPID_PUBLIC_KEY": os.getenv('VAPID_PUBLIC_KEY', ''),
    "VAPID_PRIVATE_KEY": os.getenv('VAPID_PRIVATE_KEY', ''),
    "VAPID_ADMIN_EMAIL": os.getenv('VAPID_ADMIN_EMAIL', 'admin@traitkeeper.com'),
}

# Assign VAPID public key for use in templates or views.
VAPID_PUBLIC_KEY = WEBPUSH_SETTINGS["VAPID_PUBLIC_KEY"]


# =============================================================================
# PROVIDER QUOTA MANAGER CONFIGURATION
# =============================================================================

PROVIDER_QUOTA_CONFIGS = {
    'helius': {
        'free': {
            'daily_credits': int(os.getenv('HELIUS_FREE_DAILY_CREDITS', '1000000')), 
            'requests_per_second': int(os.getenv('HELIUS_FREE_RPS', '10'))
        },
        'developer': {
            'daily_credits': int(os.getenv('HELIUS_DEV_DAILY_CREDITS', '10000000')), 
            'requests_per_second': int(os.getenv('HELIUS_DEV_RPS', '50'))
        }
    },
    'quicknode': {
        'free': {
            'daily_credits': int(os.getenv('QUICKNODE_FREE_DAILY_CREDITS', '10000000')), 
            'requests_per_second': int(os.getenv('QUICKNODE_FREE_RPS', '15'))
        },
        'build': {
            'daily_credits': int(os.getenv('QUICKNODE_BUILD_DAILY_CREDITS', '80000000')), 
            'requests_per_second': int(os.getenv('QUICKNODE_BUILD_RPS', '50'))
        }
    },
}

PROVIDER_PRIORITY_ALLOCATIONS = {
    # Percentage of daily credits allocated to each tier
    'VIP': float(os.getenv('PROVIDER_VIP_ALLOCATION', '0.60')),      # 60%
    'ACTIVE': float(os.getenv('PROVIDER_ACTIVE_ALLOCATION', '0.30')),   # 30%
    'INACTIVE': float(os.getenv('PROVIDER_INACTIVE_ALLOCATION', '0.10'))  # 10%
}

# --- BACKGROUND TASK SETTINGS ---
# Set to False during development when you don't want the indexer running
RUN_BACKGROUND_TASKS = str_to_bool(os.getenv('RUN_BACKGROUND_TASKS', 'True'))