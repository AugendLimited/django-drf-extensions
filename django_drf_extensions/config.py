"""
Configuration validation for django-drf-extensions.
"""
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def validate_drf_extensions_config():
    """
    Validate that required settings are configured for django-drf-extensions.
    
    Raises:
        ImproperlyConfigured: If required settings are missing or invalid
    """
    # Check if cache is configured
    if not hasattr(settings, 'CACHES') or 'default' not in settings.CACHES:
        raise ImproperlyConfigured(
            "django-drf-extensions requires a cache backend to be configured. "
            "Please add CACHES setting to your Django settings."
        )
    
    # Check if Celery is configured
    if not hasattr(settings, 'CELERY_BROKER_URL'):
        raise ImproperlyConfigured(
            "django-drf-extensions requires Celery to be configured. "
            "Please add CELERY_BROKER_URL setting to your Django settings."
        )
    
    # Check if REST framework is installed
    if 'rest_framework' not in getattr(settings, 'INSTALLED_APPS', []):
        raise ImproperlyConfigured(
            "django-drf-extensions requires Django REST Framework to be installed. "
            "Please add 'rest_framework' to INSTALLED_APPS."
        )


def get_drf_extensions_settings():
    """
    Get django-drf-extensions specific settings with defaults.
    
    Returns:
        dict: Settings dictionary with defaults applied
    """
    return {
        'DRF_EXT_CHUNK_SIZE': getattr(settings, 'DRF_EXT_CHUNK_SIZE', 100),
        'DRF_EXT_MAX_RECORDS': getattr(settings, 'DRF_EXT_MAX_RECORDS', 10000),
        'DRF_EXT_CACHE_TIMEOUT': getattr(settings, 'DRF_EXT_CACHE_TIMEOUT', 86400),
        'DRF_EXT_PROGRESS_UPDATE_INTERVAL': getattr(settings, 'DRF_EXT_PROGRESS_UPDATE_INTERVAL', 10),
        'DRF_EXT_BATCH_SIZE': getattr(settings, 'DRF_EXT_BATCH_SIZE', 1000),
        'DRF_EXT_USE_OPTIMIZED_TASKS': getattr(settings, 'DRF_EXT_USE_OPTIMIZED_TASKS', True),
        'DRF_EXT_AUTO_OPTIMIZE_QUERIES': getattr(settings, 'DRF_EXT_AUTO_OPTIMIZE_QUERIES', True),
        'DRF_EXT_QUERY_TIMEOUT': getattr(settings, 'DRF_EXT_QUERY_TIMEOUT', 300),  # 5 minutes
        'DRF_EXT_ENABLE_METRICS': getattr(settings, 'DRF_EXT_ENABLE_METRICS', False),
        
        # Sync Upsert Settings
        'DRF_EXT_SYNC_UPSERT_MAX_ITEMS': getattr(settings, 'DRF_EXT_SYNC_UPSERT_MAX_ITEMS', 50),
        'DRF_EXT_SYNC_UPSERT_BATCH_SIZE': getattr(settings, 'DRF_EXT_SYNC_UPSERT_BATCH_SIZE', 1000),
        'DRF_EXT_SYNC_UPSERT_TIMEOUT': getattr(settings, 'DRF_EXT_SYNC_UPSERT_TIMEOUT', 30),  # 30 seconds
    } 