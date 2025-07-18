# Django DRF Extensions

Enhanced operations for Django REST Framework using Celery workers and Redis for progress tracking.

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

This implementation provides both **asynchronous operations** and **synchronous upsert operations** for your Django REST Framework API endpoints using Celery workers and Redis for progress tracking.

## Overview

The operations system consists of:

1. **Processing Tasks** (`django_drf_extensions.processing`) - Celery tasks for handling async operations
2. **Mixins** (`django_drf_extensions.mixins`) - DRF ViewSet mixins to add operation endpoints
3. **Sync Upsert Mixin** (`django_drf_extensions.mixins.SyncUpsertMixin`) - DRF ViewSet mixin for synchronous upsert operations
4. **Redis Cache** (`django_drf_extensions.cache`) - Progress tracking and result caching
5. **Status Views** (`django_drf_extensions.views`) - API endpoints to check task status

## Features

- ✅ **Asynchronous Processing**: Long-running operations don't block the API
- ✅ **Synchronous Upserts**: Immediate results for small datasets (≤50 items)
- ✅ **Progress Tracking**: Real-time progress updates via Redis
- ✅ **Error Handling**: Detailed error reporting for failed items
- ✅ **Result Caching**: Final results cached in Redis for 24 hours
- ✅ **Validation**: Full DRF serializer validation for all items
- ✅ **Atomic Operations**: Database transactions ensure data consistency
- ✅ **Unified Endpoint**: Single `/operations` endpoint supports both JSON and CSV via Content-Type detection
- ✅ **RESTful Design**: Uses HTTP methods (GET, POST, PATCH, PUT, DELETE) for different operations
- ✅ **Smart Routing**: Automatically chooses sync vs async based on dataset size and endpoint

## Content-Type Detection

The system automatically detects the input format based on the HTTP `Content-Type` header:

- **`Content-Type: application/json`** → JSON data processing
- **`Content-Type: multipart/form-data`** → CSV file upload processing

This means you can use the same `/operations` endpoint for both JSON and CSV operations, making the API clean and RESTful.

## Available Operations

### Synchronous Operations

#### 1. Sync Upsert (Insert or Update)
- **Endpoint**: `POST|PATCH|PUT /api/{model}/upsert/?unique_fields=field1,field2`
- **Method**: POST, PATCH, or PUT
- **Input**: Single object or array of objects (≤50 items by default)
- **Output**: Immediate results with created/updated counts and IDs
- **Use Case**: Real-time form submissions, small API integrations, user interactions requiring instant feedback

```bash
# Single item sync upsert
curl -X POST "http://localhost:8000/api/financial-transactions/upsert/?unique_fields=financial_account,datetime" \
  -H "Content-Type: application/json" \
  -d '{"financial_account": 1, "datetime": "2025-01-01T10:00:00Z", "amount": "100.50"}'

# Multiple items sync upsert  
curl -X POST "http://localhost:8000/api/financial-transactions/upsert/?unique_fields=financial_account,datetime&update_fields=amount,description" \
  -H "Content-Type: application/json" \
  -d '[
    {"financial_account": 1, "datetime": "2025-01-01T10:00:00Z", "amount": "100.50"},
    {"financial_account": 1, "datetime": "2025-01-01T11:00:00Z", "amount": "200.75"}
  ]'
```

**Response:**
```json
{
  "message": "Upsert completed successfully",
  "total_items": 2,
  "created_count": 1,
  "updated_count": 1,
  "error_count": 0,
  "created_ids": [123],
  "updated_ids": [124],
  "errors": [],
  "unique_fields": ["financial_account", "datetime"],
  "update_fields": ["amount", "description"],
  "is_sync": true
}
```

### Asynchronous Operations

### 2. Async Retrieve
- **Endpoint**: `GET /api/{model}/operations/?ids=1,2,3`
- **Method**: GET
- **Input**: Query parameters (`ids`) or request body (complex filters)
- **Output**: Serialized data (direct) or Task ID for large results

### 3. Async Create
- **Endpoint**: `POST /api/{model}/operations/`
- **Method**: POST
- **Input**: Array of objects to create
- **Output**: Task ID and status URL

### 4. Async Update (Partial)
- **Endpoint**: `PATCH /api/{model}/operations/`
- **Method**: PATCH
- **Input**: Array of objects with `id` and partial update data
- **Output**: Task ID and status URL

### 5. Async Replace (Full Update)
- **Endpoint**: `PUT /api/{model}/operations/`
- **Method**: PUT
- **Input**: Array of complete objects with `id` and all required fields
- **Output**: Task ID and status URL

### 6. Async Delete
- **Endpoint**: `DELETE /api/{model}/operations/`
- **Method**: DELETE
- **Input**: Array of IDs to delete
- **Output**: Task ID and status URL

### 7. Async Upsert (Insert or Update)
- **Endpoint**: `PATCH /api/{model}/operations/` or `PUT /api/{model}/operations/`
- **Method**: PATCH or PUT
- **Input**: Object with `data` array, `unique_fields`, and optional `update_fields`
- **Output**: Task ID and status URL
- **Description**: Similar to Django's `bulk_create` with `update_conflicts=True`. Integrated into existing PATCH/PUT endpoints.

### CSV-based Operations (Async)

All CSV operations use the same `/operations` endpoint with `Content-Type: multipart/form-data`:

### 8. CSV Create
- **Endpoint**: `POST /api/{model}/operations/`
- **Method**: POST
- **Content-Type**: `multipart/form-data`
- **Input**: CSV file upload with headers matching model fields
- **Output**: Task ID and status URL

### 9. CSV Update (Partial)
- **Endpoint**: `PATCH /api/{model}/operations/`
- **Method**: PATCH
- **Content-Type**: `multipart/form-data`
- **Input**: CSV file with `id` column and fields to update
- **Output**: Task ID and status URL

### 10. CSV Replace (Full Update)
- **Endpoint**: `PUT /api/{model}/operations/`
- **Method**: PUT
- **Content-Type**: `multipart/form-data`
- **Input**: CSV file with `id` column and all required fields
- **Output**: Task ID and status URL

### 11. CSV Delete
- **Endpoint**: `DELETE /api/{model}/operations/`
- **Method**: DELETE
- **Content-Type**: `multipart/form-data`
- **Input**: CSV file with `id` column containing IDs to delete
- **Output**: Task ID and status URL

### 12. CSV Upsert
- **Endpoint**: `PATCH /api/{model}/operations/` or `PUT /api/{model}/operations/`
- **Method**: PATCH or PUT
- **Content-Type**: `multipart/form-data`
- **Input**: CSV file with headers matching model fields + form fields for `unique_fields` and optional `update_fields`
- **Output**: Task ID and status URL
- **Description**: Similar to Django's `bulk_create` with `update_conflicts=True`. Integrated into existing PATCH/PUT endpoints.

### 13. Status Tracking
- **Endpoint**: `GET /api/operations/{task_id}/status/`
- **Output**: Task status, progress, and results

## HTTP Method Differences

- **GET**: Retrieve multiple records by IDs or complex queries
- **POST**: Creates new records (all fields required based on your model)
- **PATCH**: Partial updates - only include fields you want to change (requires `id`)
- **PUT**: Full replacement - all required fields must be provided (requires `id`) 
- **DELETE**: Removes records (provide array of IDs)
- **PATCH/PUT /operations/**: Partial/full updates or upsert records based on unique constraints (when `data`, `unique_fields` provided)
- **POST/PATCH/PUT /upsert/**: Synchronous upsert with immediate results (≤50 items)

## When to Use Sync vs Async

### Use **Sync Upsert** (`/upsert`) when:
- ≤50 items to process
- Need immediate results
- Real-time user interactions
- Form submissions
- API integrations with small payloads
- Want to handle errors immediately

### Use **Async Operations** (`/operations`) when:
- >50 items to process  
- Can wait for results
- Large data imports
- Batch processing jobs
- CSV file uploads
- Background data synchronization

## Usage

### Adding Operations to a ViewSet

```python
from django_drf_extensions.mixins import AsyncOperationsMixin, SyncUpsertMixin

# For async operations only
class FinancialTransactionViewSet(AsyncOperationsMixin, viewsets.ModelViewSet):
    queryset = FinancialTransaction.objects.all()
    serializer_class = FinancialTransactionSerializer

# For sync upsert operations only  
class FinancialTransactionViewSet(SyncUpsertMixin, viewsets.ModelViewSet):
    queryset = FinancialTransaction.objects.all()
    serializer_class = FinancialTransactionSerializer

# For both sync and async operations (recommended)
class FinancialTransactionViewSet(SyncUpsertMixin, AsyncOperationsMixin, viewsets.ModelViewSet):
    queryset = FinancialTransaction.objects.all()
    serializer_class = FinancialTransactionSerializer
```

### OpenAPI/Swagger Documentation

The operations now include comprehensive OpenAPI schema definitions for Swagger documentation. To enable this:

1. **Install drf-spectacular** (optional dependency):
```bash
pip install drf-spectacular
```

2. **Add to INSTALLED_APPS**:
```python
INSTALLED_APPS = [
    # ... your other apps
    'drf_spectacular',
]
```

3. **Configure DRF settings**:
```python
REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Your API',
    'DESCRIPTION': 'Your API description',
    'VERSION': '1.0.0',
}
```

4. **Add URL patterns**:
```python
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    # ... your other URLs
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]
```

The endpoints will now show proper OpenAPI documentation with:
- ✅ **Query parameters** for async GET operations (e.g., `?ids=1,2,3`)
- ✅ **Request body schemas** for complex queries and operations
- ✅ **Array payloads** correctly specified for all operations
- ✅ **Request/response examples** for each operation type
- ✅ **Proper schema references** for your model fields
- ✅ **CSV upload support** documented for file operations
- ✅ **Multiple content types** (JSON and CSV) properly documented

**Note**: If `drf-spectacular` is not installed, the mixins will work normally but without enhanced OpenAPI documentation.

### Example API Calls

#### Sync Upsert (Single Item)
```bash
# Small dataset - returns data immediately
curl -X POST "http://localhost:8000/api/financial-transactions/upsert/?unique_fields=financial_account,datetime" \
  -H "Content-Type: application/json" \
  -d '{"financial_account": 1, "datetime": "2025-01-01T10:00:00Z", "amount": "100.50"}'
```

#### Async Retrieve (Large Dataset)
```bash
# Large result set - returns task ID
curl "http://localhost:8000/api/financial-transactions/operations/?ids=1,2,3,4,5,6,7,8,...,150"
```

#### Async Complex Query
```bash
# Complex filtering via request body
curl -X GET http://localhost:8000/api/financial-transactions/operations/ \\
  -H "Content-Type: application/json" \\
  -d '{
    "filters": {
      "amount": {"gte": 100, "lte": 1000},
      "datetime": {"gte": "2025-01-01"},
      "financial_account": 1
    }
  }'
```

#### Async Create
```bash
curl -X POST http://localhost:8000/api/financial-transactions/operations/ \\
  -H "Content-Type: application/json" \\
  -d '[
    {
      "amount": "100.50",
      "description": "Transaction 1",
      "datetime": "2025-01-01T10:00:00Z",
      "financial_account": 1,
      "classification_status": 1
    },
    {
      "amount": "-25.75", 
      "description": "Transaction 2",
      "datetime": "2025-01-01T11:00:00Z",
      "financial_account": 1,
      "classification_status": 1
    }
  ]'
```

**Response:**
```json
{
  "message": "Create task started for 2 items",
  "task_id": "abc123-def456-ghi789",
  "total_items": 2,
  "status_url": "/api/operations/abc123-def456-ghi789/status/"
}
```

#### Async Update (Partial)
```bash
curl -X PATCH http://localhost:8000/api/financial-transactions/operations/ \\
  -H "Content-Type: application/json" \\
  -d '[
    {"id": 1, "amount": "150.00"},
    {"id": 2, "description": "Updated description"}
  ]'
```

#### Async Upsert (Salesforce-style)
```bash
curl -X PATCH "http://localhost:8000/api/financial-transactions/operations/?unique_fields=financial_account,datetime" \\
  -H "Content-Type: application/json" \\
  -d '[
    {"financial_account": 1, "datetime": "2025-01-01T12:00:00Z", "amount": "300.00"},
    {"financial_account": 1, "datetime": "2025-01-01T13:00:00Z", "amount": "400.00"}
  ]'
```

#### CSV Upload
```bash
curl -X POST http://localhost:8000/api/financial-transactions/operations/ \\
  -F "file=@transactions.csv"
```

#### Check Task Status
```bash
curl http://localhost:8000/api/operations/abc123-def456-ghi789/status/
```

**Response:**
```json
{
  "task_id": "abc123-def456-ghi789",
  "state": "SUCCESS",
  "status": "completed",
  "message": "Task completed successfully",
  "result": {
    "operation_type": "async_create",
    "total_items": 2,
    "success_count": 2,
    "error_count": 0,
    "created_ids": [123, 124],
    "errors": []
  },
  "progress": {
    "current": 2,
    "total": 2,
    "percentage": 100
  }
}
```

## Configuration

### Custom Settings

You can customize the behavior by adding these settings to your Django settings:

```python
# Operation Settings
DRF_EXT_CHUNK_SIZE = 100                    # Items per processing chunk
DRF_EXT_MAX_RECORDS = 10000                 # Maximum records per operation
DRF_EXT_BATCH_SIZE = 1000                   # Database batch size
DRF_EXT_CACHE_TIMEOUT = 86400               # Cache timeout (24 hours)
DRF_EXT_PROGRESS_UPDATE_INTERVAL = 10       # Progress update frequency
DRF_EXT_QUERY_TIMEOUT = 300                 # Query timeout (5 minutes)

# Sync Upsert Settings
DRF_EXT_SYNC_UPSERT_MAX_ITEMS = 50          # Max items for sync upsert
DRF_EXT_SYNC_UPSERT_BATCH_SIZE = 1000       # Sync upsert batch size
DRF_EXT_SYNC_UPSERT_TIMEOUT = 30            # Sync upsert timeout (30 seconds)

# Feature Flags
DRF_EXT_USE_OPTIMIZED_TASKS = True          # Use optimized task execution
DRF_EXT_AUTO_OPTIMIZE_QUERIES = True        # Auto-optimize database queries
DRF_EXT_ENABLE_METRICS = False              # Enable operation metrics
```

## Error Handling

The system provides comprehensive error handling:

- **Validation Errors**: Field-level validation using DRF serializers
- **Database Errors**: Transaction rollback on failures
- **Task Failures**: Detailed error reporting in task status
- **Timeout Handling**: Configurable timeouts for long-running operations

## Performance Considerations

- **Database Efficiency**: Uses `bulk_create`, `bulk_update`, and `bulk_delete`
- **Memory Management**: Processes large datasets in configurable chunks
- **Caching**: Redis-based progress tracking and result caching
- **Async Processing**: Non-blocking operations via Celery
- **Query Optimization**: Automatic query optimization where possible

## Security Considerations

- **Authentication**: Respects DRF authentication classes
- **Permissions**: Honors ViewSet permission classes
- **Validation**: Full serializer validation for all input data
- **File Upload**: Secure CSV file processing with validation

## Monitoring

### Task Status Monitoring

```python
from django_drf_extensions.cache import OperationCache

# Get task progress
progress = OperationCache.get_task_progress(task_id)

# Get task result
result = OperationCache.get_task_result(task_id)

# Get combined summary
summary = OperationCache.get_task_summary(task_id)
```

### Celery Monitoring

For production deployments, consider using Flower for Celery monitoring:

```bash
pip install flower
celery -A your_project flower
```

## Migration from django-bulk-drf

If you're migrating from the old `django-bulk-drf` package:

1. **Update package name**:
```bash
pip uninstall django-bulk-drf
pip install django-drf-extensions
```

2. **Update INSTALLED_APPS**:
```python
INSTALLED_APPS = [
    # ... your other apps
    'rest_framework',
    'django_drf_extensions',  # Changed from 'django_bulk_drf'
]
```

3. **Update imports**:
```python
# Old
from django_bulk_drf.bulk_mixins import BulkOperationsMixin

# New
from django_drf_extensions.mixins import AsyncOperationsMixin
```

4. **Update endpoint URLs**:
```bash
# Old
/api/model/bulk/

# New
/api/model/operations/  # For async operations
/api/model/upsert/      # For sync upsert
```

5. **Update settings** (optional):
```python
# Old setting names (still supported for backward compatibility)
BULK_DRF_CHUNK_SIZE = 100

# New setting names (recommended)
DRF_EXT_CHUNK_SIZE = 100
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License.
