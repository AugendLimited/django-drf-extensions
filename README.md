# Django DRF Extensions

Advanced operation extensions for Django REST Framework providing intelligent sync/async routing with a clean, unified API design.

## Installation

```bash
pip install django-drf-extensions
```

### Requirements

- Python 3.11+
- Django 4.0+
- Django REST Framework 3.14+
- Celery 5.2+
- Redis 4.3+
- django-redis 5.2+

## Quick Setup

1. Add to your `INSTALLED_APPS`:
```python
INSTALLED_APPS = [
    # ... your other apps
    'rest_framework',
    'django_drf_extensions',
]
```

2. Configure Redis cache:
```python
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}
```

3. Configure Celery:
```python
# settings.py
CELERY_BROKER_URL = 'redis://127.0.0.1:6379/0'
CELERY_RESULT_BACKEND = 'redis://127.0.0.1:6379/0'
```

## Overview

This package extends Django REST Framework with a unified mixin that intelligently routes between synchronous and asynchronous processing based on your data size and requirements.

### The Extension System

1. **Enhanced Standard Endpoints**: Smart sync operations for immediate results
2. **Bulk Endpoints**: Dedicated async endpoints for large dataset processing  
3. **Intelligent Routing**: Automatic sync/async decision based on dataset size
4. **Progress Tracking**: Redis-based monitoring for async operations
5. **Status Management**: Comprehensive operation status and results

## Features

- ✅ **Unified API Design**: Single mixin provides both sync and async capabilities
- ✅ **Smart Standard Endpoints**: Enhanced ViewSet methods with intelligent array handling
- ✅ **Dedicated Bulk Endpoints**: Clean `/bulk/` endpoints for async operations
- ✅ **Immediate Results**: Synchronous operations for small datasets with instant feedback
- ✅ **Scalable Processing**: Asynchronous operations for large datasets without blocking
- ✅ **Real-time Monitoring**: Live progress tracking and detailed status reporting
- ✅ **Comprehensive Error Handling**: Detailed validation and error reporting per item
- ✅ **Result Persistence**: Automatic caching of results for fast retrieval
- ✅ **Full Validation**: Complete DRF serializer validation ensuring data integrity
- ✅ **Transaction Safety**: Atomic database operations with rollback on failures

## Package Philosophy

This package provides a modern approach to scalable operations by offering:

1. **Clean API Design**: Enhances existing endpoints rather than creating parallel ones
2. **Intelligent Processing**: Automatically determines optimal processing method
3. **Unified Architecture**: Single mixin extends your ViewSets without complexity
4. **Production-Ready**: Built-in monitoring, error handling, and progress tracking

## Usage

### Adding Extensions to a ViewSet

```python
from rest_framework import viewsets
from django_drf_extensions.mixins import OperationsMixin

class ContractViewSet(OperationsMixin, viewsets.ModelViewSet):
    """
    Enhanced ViewSet with intelligent operation routing.
    
    Provides:
    - Standard CRUD operations
    - Smart sync operations for small datasets
    - Bulk async operations for large datasets
    """
    queryset = Contract.objects.all()
    serializer_class = ContractSerializer
```

Your ViewSet now provides these endpoints:

```bash
# Standard ModelViewSet endpoints (enhanced for arrays)
GET    /api/contracts/                    # List (enhanced with ?ids= support)
POST   /api/contracts/                    # Create (enhanced with array + ?unique_fields= support)
GET    /api/contracts/{id}/               # Retrieve single
PATCH  /api/contracts/                    # Update (enhanced with array + ?unique_fields= support)
PUT    /api/contracts/                    # Replace (enhanced with array + ?unique_fields= support)
DELETE /api/contracts/{id}/               # Delete single

# Bulk endpoints for async processing
GET    /api/contracts/bulk/               # Async retrieve multiple
POST   /api/contracts/bulk/               # Async create multiple  
PATCH  /api/contracts/bulk/               # Async update/upsert multiple
PUT    /api/contracts/bulk/               # Async replace/upsert multiple
DELETE /api/contracts/bulk/               # Async delete multiple

# Operation monitoring
GET    /api/operations/{task_id}/status/  # Check async status
```

## API Design

### Enhanced Standard Endpoints (Sync Operations)

Smart enhancements to standard ViewSet methods for immediate results with small datasets:

#### Multi-Get
```bash
# Small dataset - immediate results
GET /api/contracts/?ids=1,2,3,4,5

# Response (immediate)
{
  "count": 5,
  "results": [...],
  "is_sync": true
}
```

#### Sync Upsert
```bash
# Small dataset - immediate upsert
POST /api/contracts/?unique_fields=contract_number,year
Content-Type: application/json
[
  {"contract_number": "C001", "year": 2024, "amount": 1000},
  {"contract_number": "C002", "year": 2024, "amount": 2000}
]

# Response (immediate)
{
  "message": "Upsert completed successfully",
  "total_items": 2,
  "created_count": 1,
  "updated_count": 1,
  "created_ids": [123],
  "updated_ids": [124],
  "is_sync": true
}
```

### Bulk Endpoints (Async Operations)

Dedicated endpoints for large dataset processing via background tasks:

#### Async Multi-Get
```bash
# Large dataset - background processing
GET /api/contracts/bulk/?ids=1,2,3,...,1000

# Response (task started)
{
  "message": "Bulk get task started for 1000 items",
  "task_id": "abc123-def456",
  "status_url": "/api/operations/abc123-def456/status/",
  "is_async": true
}
```

#### Async Upsert
```bash
# Large dataset - background processing
PATCH /api/contracts/bulk/?unique_fields=contract_number,year
Content-Type: application/json
[
  {"contract_number": "C001", "year": 2024, "amount": 1000},
  ... // 500+ items
]

# Response (task started)
{
  "message": "Bulk upsert task started for 500 items",
  "task_id": "def456-ghi789",
  "unique_fields": ["contract_number", "year"],
  "status_url": "/api/operations/def456-ghi789/status/"
}
```

## Operation Types

### Sync Operations (Standard Endpoints)
- **Best for**: ≤50-100 items, immediate results needed
- **Use cases**: Real-time user interactions, form submissions, small API integrations
- **Response**: Immediate data or results
- **Endpoints**: Enhanced standard ViewSet methods

### Async Operations (Bulk Endpoints)  
- **Best for**: >100 items, can wait for results
- **Use cases**: Data imports, batch processing, CSV uploads
- **Response**: Task ID for monitoring
- **Endpoints**: Dedicated `/bulk/` endpoints

## Configuration

### Custom Settings

```python
# Operation Settings
DRF_EXT_CHUNK_SIZE = 100                    # Items per processing chunk
DRF_EXT_MAX_RECORDS = 10000                 # Maximum records per operation
DRF_EXT_BATCH_SIZE = 1000                   # Database batch size
DRF_EXT_CACHE_TIMEOUT = 86400               # Cache timeout (24 hours)
DRF_EXT_PROGRESS_UPDATE_INTERVAL = 10       # Progress update frequency

# Sync Operation Limits
DRF_EXT_SYNC_MAX_ITEMS = 50                 # Max items for sync operations
DRF_EXT_SYNC_MULTI_GET_MAX = 100            # Max items for sync multi-get
```

## Example Usage

### Basic Contract Management

```python
# Small dataset - sync operations (immediate results)
curl -X POST "/api/contracts/?unique_fields=contract_number" \
  -H "Content-Type: application/json" \
  -d '[
    {"contract_number": "C001", "amount": 1000},
    {"contract_number": "C002", "amount": 2000}
  ]'

# Large dataset - async operations (background processing)
curl -X POST "/api/contracts/bulk/" \
  -H "Content-Type: application/json" \
  -d '[...500 contracts...]'

# Check async status
curl "/api/operations/{task_id}/status/"
```

### Migration from Previous Versions

If you're coming from older versions:

```python
# Old (separate mixins)
class ContractViewSet(SyncUpsertMixin, AsyncOperationsMixin, viewsets.ModelViewSet):
    queryset = Contract.objects.all()
    serializer_class = ContractSerializer

# New (unified mixin)
class ContractViewSet(OperationsMixin, viewsets.ModelViewSet):
    queryset = Contract.objects.all()
    serializer_class = ContractSerializer
```

### Endpoint Changes

| Operation | Old Endpoints | New Endpoints |
|-----------|---------------|---------------|
| Sync Upsert | `POST /upsert/` | `POST /?unique_fields=...` |
| Async Create | `POST /operations/` | `POST /bulk/` |
| Async Update | `PATCH /operations/` | `PATCH /bulk/` |
| Async Delete | `DELETE /operations/` | `DELETE /bulk/` |

## Error Handling

The system provides comprehensive error handling:

- **Validation Errors**: Field-level validation using DRF serializers
- **Size Limits**: Automatic routing suggestion for oversized sync requests
- **Database Errors**: Transaction rollback on failures
- **Task Failures**: Detailed error reporting in async task status

## Performance Considerations

- **Database Efficiency**: Uses optimized database operations for all bulk processing
- **Memory Management**: Processes large datasets in configurable chunks
- **Intelligent Routing**: Automatic sync/async decision based on dataset size
- **Progress Tracking**: Redis-based monitoring without database overhead
- **Result Caching**: Efficient caching of async operation results

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License.
