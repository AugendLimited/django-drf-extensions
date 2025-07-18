# Django DRF Extensions

Advanced operation extensions for Django REST Framework providing both asynchronous processing via Celery/Redis and synchronous operations with intelligent routing based on dataset size.

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

This implementation extends Django REST Framework with powerful operation mixins that automatically choose between synchronous and asynchronous processing based on your data size and requirements.

## Overview

The extension system consists of:

1. **Processing Engine** (`django_drf_extensions.processing`) - Celery tasks for scalable async operations
2. **Operation Mixins** (`django_drf_extensions.mixins`) - DRF ViewSet mixins that add intelligent operation endpoints
3. **Sync Operations** (`django_drf_extensions.mixins.SyncUpsertMixin`) - Immediate processing for small datasets
4. **Progress Tracking** (`django_drf_extensions.cache`) - Redis-based progress monitoring and result caching
5. **Status Management** (`django_drf_extensions.views`) - API endpoints for operation status and results

## Features

- ✅ **Intelligent Processing**: Automatically routes between sync and async based on dataset size
- ✅ **Immediate Results**: Synchronous operations for small datasets (≤50 items) with instant feedback
- ✅ **Scalable Processing**: Asynchronous operations for large datasets without blocking the API
- ✅ **Real-time Monitoring**: Live progress tracking and detailed status reporting via Redis
- ✅ **Comprehensive Error Handling**: Detailed validation and error reporting for individual items
- ✅ **Result Persistence**: Automatic caching of results for 24 hours with fast retrieval
- ✅ **Full Validation**: Complete DRF serializer validation ensuring data integrity
- ✅ **Transaction Safety**: Atomic database operations with automatic rollback on failures
- ✅ **Unified API**: Single endpoint supporting JSON and CSV via intelligent Content-Type detection
- ✅ **RESTful Operations**: Standard HTTP methods (GET, POST, PATCH, PUT, DELETE) for different actions
- ✅ **Format Flexibility**: Support for both structured JSON payloads and CSV file uploads

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
- **Description**: Intelligent upsert operation that creates new records or updates existing ones based on unique constraints. Integrated into existing PATCH/PUT endpoints.

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
- **Description**: Intelligent upsert operation that creates new records or updates existing ones based on unique constraints. Integrated into existing PATCH/PUT endpoints.

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

### Adding Extensions to a ViewSet

```python
from rest_framework import viewsets
from django_drf_extensions.mixins import AsyncOperationsMixin, SyncUpsertMixin

# Recommended: Full extension support
class ProductViewSet(SyncUpsertMixin, AsyncOperationsMixin, viewsets.ModelViewSet):
    """
    Enhanced ViewSet with intelligent operation routing.
    
    Provides:
    - Standard CRUD via ModelViewSet
    - Sync operations via /upsert/ (≤50 items, immediate results)
    - Async operations via /operations/ (>50 items, background processing)
    """
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

# Async-only: For large dataset processing
class DataImportViewSet(AsyncOperationsMixin, viewsets.ModelViewSet):
    """ViewSet optimized for large dataset operations."""
    queryset = ImportRecord.objects.all()
    serializer_class = ImportRecordSerializer

# Sync-only: For real-time operations
class UserPreferenceViewSet(SyncUpsertMixin, viewsets.ModelViewSet):
    """ViewSet optimized for immediate user interactions."""
    queryset = UserPreference.objects.all()
    serializer_class = UserPreferenceSerializer
```

Your ViewSet now provides these endpoints automatically:

```bash
# Standard ModelViewSet endpoints (unchanged)
GET    /api/products/              # List
POST   /api/products/              # Create single
GET    /api/products/{id}/         # Retrieve single
PATCH  /api/products/{id}/         # Update single
DELETE /api/products/{id}/         # Delete single

# Extension endpoints (new)
GET    /api/products/operations/   # Async retrieve multiple
POST   /api/products/operations/   # Async create multiple  
PATCH  /api/products/operations/   # Async update multiple
PUT    /api/products/operations/   # Async replace multiple
DELETE /api/products/operations/   # Async delete multiple

POST   /api/products/upsert/       # Sync upsert (immediate)
PATCH  /api/products/upsert/       # Sync upsert (immediate)
PUT    /api/products/upsert/       # Sync upsert (immediate)

GET    /api/operations/{task_id}/status/  # Check async status
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

## Package Philosophy

This package provides a modern approach to scalable operations by offering:

1. **Smart Operation Routing**: Automatically determines the best processing method based on your data size
2. **Unified API Design**: Single endpoints that handle both small immediate operations and large async processing
3. **Extensible Architecture**: Clean mixins that extend your existing ViewSets without disrupting current functionality
4. **Production-Ready**: Built-in monitoring, error handling, and progress tracking for enterprise use

## Migration Guide

If you're coming from `django-bulk-drf` or similar packages, here's how to update:

### **Before** (django-bulk-drf)
```python
from django_bulk_drf.bulk_mixins import BulkOperationsMixin

class ContractViewSet(BulkOperationsMixin, viewsets.ModelViewSet):
    queryset = Contract.objects.all()
    serializer_class = ContractSerializer
```

### **After** (django-drf-extensions)

**Option 1: Full Extension Support (Recommended)**
```python
from django_drf_extensions.mixins import AsyncOperationsMixin, SyncUpsertMixin

class ContractViewSet(SyncUpsertMixin, AsyncOperationsMixin, viewsets.ModelViewSet):
    """
    Enhanced ViewSet with intelligent operation routing.
    
    Provides:
    - Standard CRUD operations
    - Immediate sync operations for small datasets (≤50 items)
    - Background async operations for large datasets (>50 items)
    """
    queryset = Contract.objects.all()
    serializer_class = ContractSerializer
```

**Option 2: Async-Only (Similar to old bulk behavior)**
```python
from django_drf_extensions.mixins import AsyncOperationsMixin

class ContractViewSet(AsyncOperationsMixin, viewsets.ModelViewSet):
    """ViewSet with async operations for large datasets."""
    queryset = Contract.objects.all()
    serializer_class = ContractSerializer
```

**Option 3: Sync-Only (For immediate results)**
```python
from django_drf_extensions.mixins import SyncUpsertMixin

class ContractViewSet(SyncUpsertMixin, viewsets.ModelViewSet):
    """ViewSet with sync operations for immediate results."""
    queryset = Contract.objects.all()
    serializer_class = ContractSerializer
```

### **Key Changes**

| Old Package | New Package | Benefit |
|-------------|-------------|---------|
| `BulkOperationsMixin` | `AsyncOperationsMixin` | Same async functionality, better naming |
| Single mixin | `SyncUpsertMixin + AsyncOperationsMixin` | Choose sync/async based on dataset size |
| `/bulk/` endpoints | `/operations/` and `/upsert/` | RESTful design with intelligent routing |
| Only async | Both sync and async | Immediate results for small datasets |

### **Endpoint Changes**

| Old Endpoints | New Endpoints | Purpose |
|---------------|---------------|---------|
| `POST /api/contracts/bulk/` | `POST /api/contracts/operations/` | Async create (large datasets) |
| | `POST /api/contracts/upsert/` | Sync upsert (small datasets) |
| `PATCH /api/contracts/bulk/` | `PATCH /api/contracts/operations/` | Async update (large datasets) |
| | `PATCH /api/contracts/upsert/` | Sync upsert (small datasets) |
| `DELETE /api/contracts/bulk/` | `DELETE /api/contracts/operations/` | Async delete |
| `/status/{task_id}/` | `/api/operations/{task_id}/status/` | Task status monitoring |

### **Usage Examples**

**Small dataset (immediate results):**
```bash
# Sync upsert - immediate response
curl -X POST "/api/contracts/upsert/?unique_fields=contract_number" \
  -H "Content-Type: application/json" \
  -d '[{"contract_number": "C001", "amount": 1000}]'
```

**Large dataset (background processing):**
```bash
# Async operations - returns task ID
curl -X POST "/api/contracts/operations/" \
  -H "Content-Type: application/json" \
  -d '[{"contract_number": "C001", "amount": 1000}, ...]'
```

### Import Structure

```python
# Core async operations for large datasets
from django_drf_extensions.mixins import AsyncOperationsMixin

# Immediate sync operations for small datasets  
from django_drf_extensions.mixins import SyncUpsertMixin

# Combined approach (recommended)
from django_drf_extensions.mixins import AsyncOperationsMixin, SyncUpsertMixin

# Individual mixins for specific needs
from django_drf_extensions.mixins import (
    AsyncCreateMixin,
    AsyncUpdateMixin,
    AsyncDeleteMixin,
    AsyncGetMixin,
    AsyncReplaceMixin,
)

# Status monitoring
from django_drf_extensions.views import OperationStatusView
```

### Endpoint Structure

```bash
# Async operations (large datasets)
/api/model/operations/     # GET, POST, PATCH, PUT, DELETE

# Sync operations (small datasets, immediate results)  
/api/model/upsert/         # POST, PATCH, PUT

# Operation monitoring
/api/operations/{task_id}/status/  # GET, DELETE
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License.
