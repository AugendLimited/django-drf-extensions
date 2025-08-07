# Django Settings Optimization for django-drf-extensions
# Add these settings to your Django settings.py file

# django-drf-extensions Configuration
DRF_EXT_CHUNK_SIZE = 200                    # Increased from default 100
DRF_EXT_MAX_RECORDS = 50000                 # Increased from default 10000
DRF_EXT_BATCH_SIZE = 2000                   # Increased from default 1000
DRF_EXT_CACHE_TIMEOUT = 86400               # Cache timeout (24 hours)
DRF_EXT_PROGRESS_UPDATE_INTERVAL = 5        # More frequent progress updates
DRF_EXT_USE_OPTIMIZED_TASKS = True
DRF_EXT_AUTO_OPTIMIZE_QUERIES = True
DRF_EXT_QUERY_TIMEOUT = 600                 # 10 minutes timeout
DRF_EXT_ENABLE_METRICS = True               # Enable performance metrics

# Sync Upsert Settings - Optimized for your use case
DRF_EXT_SYNC_UPSERT_MAX_ITEMS = 200         # Increased from default 50
DRF_EXT_SYNC_UPSERT_BATCH_SIZE = 2000       # Increased from default 1000
DRF_EXT_SYNC_UPSERT_TIMEOUT = 60            # Increased from default 30 seconds

# Database Optimization Settings
DATABASES = {
    'default': {
        # ... your existing database config ...
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            'charset': 'utf8mb4',
        },
        'CONN_MAX_AGE': 600,  # 10 minutes connection pooling
    }
}

# Cache Configuration (if not already configured)
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'CONNECTION_POOL_KWARGS': {
                'max_connections': 50,
                'retry_on_timeout': True,
            },
        },
        'KEY_PREFIX': 'drf_ext',
        'TIMEOUT': 86400,  # 24 hours
    }
}

# Celery Configuration (if not already configured)
CELERY_BROKER_URL = 'redis://127.0.0.1:6379/0'
CELERY_RESULT_BACKEND = 'redis://127.0.0.1:6379/0'
CELERY_TASK_SOFT_TIME_LIMIT = 600  # 10 minutes
CELERY_TASK_TIME_LIMIT = 900       # 15 minutes
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ACKS_LATE = True

# REST Framework Settings
REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 100,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '1000/hour',
        'user': '10000/hour',
    },
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
    ],
}

# Logging Configuration for Performance Monitoring
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
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': 'django_drf_extensions.log',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django_drf_extensions': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}
