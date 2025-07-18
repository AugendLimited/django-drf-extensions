"""
Operation mixins for DRF ViewSets.

Provides a unified mixin that enhances standard ViewSet endpoints with intelligent 
sync/async routing and adds /bulk/ endpoints for background processing.
"""

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.core.exceptions import ValidationError

# Optional OpenAPI schema support
try:
    from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
    from drf_spectacular.types import OpenApiTypes
    SPECTACULAR_AVAILABLE = True
except ImportError:
    SPECTACULAR_AVAILABLE = False
    # Create dummy decorator if drf-spectacular is not available
    def extend_schema(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
    
    # Create dummy classes for OpenAPI types
    class OpenApiParameter:
        QUERY = "query"
        def __init__(self, name, type, location, description, examples=None):
            pass
    
    class OpenApiExample:
        def __init__(self, name, value, description=None):
            pass
    
    class OpenApiTypes:
        STR = "string"

from django_drf_extensions.processing import (
    async_create_task,
    async_delete_task,
    async_get_task,
    async_replace_task,
    async_update_task,
    async_upsert_task,
)


class OperationsMixin:
    """
    Unified mixin providing intelligent sync/async operation routing.
    
    Enhances standard ViewSet endpoints:
    - GET    /api/model/?ids=1,2,3                    # Sync multi-get
    - POST   /api/model/?unique_fields=field1,field2  # Sync upsert
    - PATCH  /api/model/?unique_fields=field1,field2  # Sync upsert  
    - PUT    /api/model/?unique_fields=field1,field2  # Sync upsert
    
    Adds /bulk/ endpoints for async processing:
    - GET    /api/model/bulk/?ids=1,2,3               # Async multi-get
    - POST   /api/model/bulk/                         # Async create
    - PATCH  /api/model/bulk/                         # Async update/upsert
    - PUT    /api/model/bulk/                         # Async replace/upsert
    - DELETE /api/model/bulk/                         # Async delete
    """
    
    # Enable PATCH and PUT on list endpoint
    http_method_names = ['get', 'post', 'patch', 'put', 'delete', 'head', 'options', 'trace']

    def dispatch(self, request, *args, **kwargs):
        """Override dispatch to handle PATCH/PUT on list endpoint for upsert."""
        # If it's a PATCH or PUT request on list endpoint (no pk in kwargs)
        if request.method in ['PATCH', 'PUT'] and 'pk' not in kwargs:
            # Check if this has unique_fields parameter (indicates upsert intent)
            # Use request.GET since query_params isn't available yet (pre-DRF processing)
            unique_fields_param = request.GET.get("unique_fields")
            if unique_fields_param:
                # Route to our upsert handler
                if request.method == 'PATCH':
                    return self.patch(request, *args, **kwargs)
                elif request.method == 'PUT':
                    return self.put(request, *args, **kwargs)
        
        # Default DRF routing
        return super().dispatch(request, *args, **kwargs)

    def get_serializer(self, *args, **kwargs):
        """Handle array data for serializers."""
        data = kwargs.get("data", None)
        if data is not None and isinstance(data, list):
            kwargs["many"] = True
        return super().get_serializer(*args, **kwargs)

    # =============================================================================
    # Enhanced Standard ViewSet Methods (Sync Operations)
    # =============================================================================

    def list(self, request, *args, **kwargs):
        """
        Enhanced list endpoint that supports multi-get via ?ids= parameter.
        
        - GET /api/model/                    # Standard list
        - GET /api/model/?ids=1,2,3          # Sync multi-get (small datasets)
        """
        ids_param = request.query_params.get("ids")
        if ids_param:
            return self._sync_multi_get(request, ids_param)
        
        # Standard list behavior
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        """
        Enhanced create endpoint that supports sync upsert via query params.
        
        - POST /api/model/                                    # Standard single create
        - POST /api/model/?unique_fields=field1,field2       # Sync upsert (array data)
        """
        unique_fields_param = request.query_params.get("unique_fields")
        if unique_fields_param and isinstance(request.data, list):
            return self._sync_upsert(request, unique_fields_param)
        
        # Standard single create behavior
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        """
        Enhanced update endpoint that supports sync upsert via query params.
        
        - PATCH /api/model/{id}/                              # Standard single update
        - PATCH /api/model/?unique_fields=field1,field2      # Sync upsert (array data)
        """
        unique_fields_param = request.query_params.get("unique_fields")
        if unique_fields_param and isinstance(request.data, list):
            return self._sync_upsert(request, unique_fields_param)
        
        # Standard single update behavior  
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        """
        Enhanced partial update endpoint that supports sync upsert via query params.
        
        - PATCH /api/model/{id}/                              # Standard single partial update
        - PATCH /api/model/?unique_fields=field1,field2      # Sync upsert (array data)
        """
        unique_fields_param = request.query_params.get("unique_fields")
        if unique_fields_param and isinstance(request.data, list):
            return self._sync_upsert(request, unique_fields_param)
        
        # Standard single partial update behavior  
        return super().partial_update(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        """
        Handle PATCH requests on list endpoint for sync upsert.
        
        - PATCH /api/model/?unique_fields=field1,field2      # Sync upsert (array data)
        """
        unique_fields_param = request.query_params.get("unique_fields")
        if unique_fields_param and isinstance(request.data, list):
            return self._sync_upsert(request, unique_fields_param)
        
        # If no unique_fields or not array data, this is an invalid PATCH on list endpoint
        return Response(
            {"error": "PATCH on list endpoint requires 'unique_fields' parameter and array data"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def put(self, request, *args, **kwargs):
        """
        Handle PUT requests on list endpoint for sync upsert.
        
        - PUT /api/model/?unique_fields=field1,field2      # Sync upsert (array data)
        """
        unique_fields_param = request.query_params.get("unique_fields")
        if unique_fields_param and isinstance(request.data, list):
            return self._sync_upsert(request, unique_fields_param)
        
        # If no unique_fields or not array data, this is an invalid PUT on list endpoint
        return Response(
            {"error": "PUT on list endpoint requires 'unique_fields' parameter and array data"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # =============================================================================
    # Sync Operation Implementations
    # =============================================================================

    def _sync_multi_get(self, request, ids_param):
        """Handle sync multi-get for small datasets."""
        try:
            ids_list = [int(id_str.strip()) for id_str in ids_param.split(",")]
        except ValueError:
            return Response(
                {"error": "Invalid ID format. Use comma-separated integers."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Limit for sync processing
        max_sync_items = 100
        if len(ids_list) > max_sync_items:
            return Response(
                {
                    "error": f"Too many items for sync processing. Use /bulk/ endpoint for >{max_sync_items} items.",
                    "provided_items": len(ids_list),
                    "max_sync_items": max_sync_items,
                    "suggestion": "Use GET /bulk/?ids=... for async processing"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Process sync multi-get
        queryset = self.get_queryset().filter(id__in=ids_list)
        serializer = self.get_serializer(queryset, many=True)

        return Response({
            "count": len(serializer.data),
            "results": serializer.data,
            "is_sync": True,
        })

    def _sync_upsert(self, request, unique_fields_param):
        """Handle sync upsert operations for small datasets."""
        # Parse parameters
        unique_fields = [f.strip() for f in unique_fields_param.split(",") if f.strip()]
        update_fields_param = request.query_params.get("update_fields")
        update_fields = None
        if update_fields_param:
            update_fields = [f.strip() for f in update_fields_param.split(",") if f.strip()]

        data_list = request.data
        if not isinstance(data_list, list):
            return Response(
                {"error": "Expected array data for upsert operations."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Limit for sync processing
        max_sync_items = int(request.query_params.get("max_items", 50))
        if len(data_list) > max_sync_items:
            return Response(
                {
                    "error": f"Too many items for sync processing. Use /bulk/ endpoint for >{max_sync_items} items.",
                    "provided_items": len(data_list),
                    "max_sync_items": max_sync_items,
                    "suggestion": "Use PATCH /bulk/?unique_fields=... for async processing"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not unique_fields:
            return Response(
                {"error": "unique_fields parameter is required for upsert operations"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Auto-infer update_fields if not provided
        if not update_fields:
            update_fields = self._infer_update_fields(data_list, unique_fields)

        # Perform sync upsert
        try:
            result = self._perform_sync_upsert(data_list, unique_fields, update_fields)
            return Response(result, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {"error": f"Upsert operation failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _perform_sync_upsert(self, data_list, unique_fields, update_fields):
        """Perform the actual sync upsert operation."""
        serializer_class = self.get_serializer_class()
        model_class = serializer_class.Meta.model
        
        created_ids = []
        updated_ids = []
        errors = []
        
        instances_to_create = []
        instances_to_update = []
        
        # Process and validate all items
        for index, item_data in enumerate(data_list):
            try:
                serializer = serializer_class(data=item_data)
                if serializer.is_valid():
                    validated_data = serializer.validated_data
                    
                    # Build unique constraint filter
                    unique_filter = {}
                    missing_fields = []
                    for field in unique_fields:
                        if field in validated_data:
                            unique_filter[field] = validated_data[field]
                        else:
                            missing_fields.append(field)
                    
                    if missing_fields:
                        errors.append({
                            "index": index,
                            "error": f"Missing required unique fields: {missing_fields}",
                            "data": item_data
                        })
                        continue
                    
                    # Check if record exists
                    existing_instance = model_class.objects.filter(**unique_filter).first()
                    
                    if existing_instance:
                        # Prepare for update
                        if update_fields:
                            update_data = {k: v for k, v in validated_data.items() if k in update_fields}
                        else:
                            update_data = {k: v for k, v in validated_data.items() if k not in unique_fields}
                        
                        # Apply updates
                        for field, value in update_data.items():
                            setattr(existing_instance, field, value)
                        
                        instances_to_update.append((index, existing_instance, existing_instance.id))
                    else:
                        # Prepare for creation
                        instance = model_class(**validated_data)
                        instances_to_create.append((index, instance))
                
                else:
                    errors.append({
                        "index": index,
                        "error": str(serializer.errors),
                        "data": item_data
                    })
            
            except (ValidationError, ValueError) as e:
                errors.append({
                    "index": index,
                    "error": str(e),
                    "data": item_data
                })
        
        # Perform database operations
        with transaction.atomic():
            # Create new instances
            if instances_to_create:
                new_instances = [instance for _, instance in instances_to_create]
                created_instances = model_class.objects.bulk_create(new_instances)
                created_ids = [instance.id for instance in created_instances]
            
            # Update existing instances
            if instances_to_update:
                update_instances = [instance for _, instance, _ in instances_to_update]
                updated_ids = [instance_id for _, _, instance_id in instances_to_update]
                
                if update_fields:
                    fields_to_update = update_fields
                else:
                    # Get all non-unique, non-primary-key fields
                    if update_instances:
                        first_instance = update_instances[0]
                        fields_to_update = [field.name for field in first_instance._meta.fields 
                                          if field.name not in unique_fields and not field.primary_key]
                    else:
                        fields_to_update = []
                
                if fields_to_update:
                    model_class.objects.bulk_update(update_instances, fields_to_update, batch_size=1000)
        
        return {
            "message": "Upsert completed successfully",
            "total_items": len(data_list),
            "created_count": len(created_ids),
            "updated_count": len(updated_ids),
            "error_count": len(errors),
            "created_ids": created_ids,
            "updated_ids": updated_ids,
            "errors": errors,
            "unique_fields": unique_fields,
            "update_fields": update_fields,
            "is_sync": True
        }

    def _infer_update_fields(self, data_list, unique_fields):
        """Auto-infer update fields from data payload."""
        if not data_list:
            return []
        
        all_fields = set()
        for item in data_list:
            if isinstance(item, dict):
                all_fields.update(item.keys())
        
        update_fields = list(all_fields - set(unique_fields))
        update_fields.sort()
        return update_fields

    # =============================================================================
    # Bulk Endpoints (Async Operations)
    # =============================================================================

    @action(detail=False, methods=["get"], url_path="bulk")
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="ids",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Comma-separated list of IDs to retrieve",
                examples=[OpenApiExample("IDs", value="1,2,3,4,5")]
            )
        ],
        description="Retrieve multiple instances asynchronously via background processing.",
        summary="Async bulk retrieve"
    )
    def bulk_get(self, request):
        """Async bulk retrieve for large datasets."""
        ids_param = request.query_params.get("ids")
        if not ids_param:
            return Response(
                {"error": "ids parameter is required for bulk get operations"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        try:
            ids_list = [int(id_str.strip()) for id_str in ids_param.split(",")]
        except ValueError:
            return Response(
                {"error": "Invalid ID format. Use comma-separated integers."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Start async task
        model_class = self.get_queryset().model
        model_class_path = f"{model_class.__module__}.{model_class.__name__}"
        serializer_class = self.get_serializer_class()
        serializer_class_path = f"{serializer_class.__module__}.{serializer_class.__name__}"

        query_data = {"ids": ids_list}
        user_id = request.user.id if request.user.is_authenticated else None
        task = async_get_task.delay(model_class_path, serializer_class_path, query_data, user_id)

        return Response({
            "message": f"Bulk get task started for {len(ids_list)} items",
            "task_id": task.id,
            "total_items": len(ids_list),
            "status_url": f"/api/operations/{task.id}/status/",
            "is_async": True,
        }, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["post"], url_path="bulk")
    @extend_schema(
        request={
            "application/json": {
                "type": "array",
                "description": "Array of objects to create",
            }
        },
        description="Create multiple instances asynchronously via background processing.",
        summary="Async bulk create"
    )
    def bulk_create(self, request):
        """Async bulk create for large datasets."""
        data_list = request.data
        if not isinstance(data_list, list):
            return Response(
                {"error": "Expected array data for bulk operations."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not data_list:
            return Response(
                {"error": "Empty array provided"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Start async task
        serializer_class = self.get_serializer_class()
        serializer_class_path = f"{serializer_class.__module__}.{serializer_class.__name__}"
        user_id = request.user.id if request.user.is_authenticated else None
        task = async_create_task.delay(serializer_class_path, data_list, user_id)

        return Response({
            "message": f"Bulk create task started for {len(data_list)} items",
            "task_id": task.id,
            "total_items": len(data_list),
            "status_url": f"/api/operations/{task.id}/status/",
        }, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["patch"], url_path="bulk")
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="unique_fields",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Comma-separated unique field names for upsert mode",
                examples=[OpenApiExample("Fields", value="account,date")]
            )
        ],
        request={
            "application/json": {
                "type": "array",
                "description": "Array of objects to update or upsert",
            }
        },
        description="Update multiple instances asynchronously. Supports both standard update (with id fields) and upsert mode (with unique_fields parameter).",
        summary="Async bulk update/upsert"
    )
    def bulk_update(self, request):
        """Async bulk update/upsert for large datasets."""
        data_list = request.data
        if not isinstance(data_list, list):
            return Response(
                {"error": "Expected array data for bulk operations."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not data_list:
            return Response(
                {"error": "Empty array provided"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if this is upsert mode
        unique_fields_param = request.query_params.get("unique_fields")
        if unique_fields_param:
            return self._bulk_upsert(request, data_list, unique_fields_param)

        # Standard bulk update mode - validate ID fields
        for i, item in enumerate(data_list):
            if not isinstance(item, dict) or "id" not in item:
                return Response(
                    {"error": f"Item at index {i} is missing 'id' field"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Start async update task
        serializer_class = self.get_serializer_class()
        serializer_class_path = f"{serializer_class.__module__}.{serializer_class.__name__}"
        user_id = request.user.id if request.user.is_authenticated else None
        task = async_update_task.delay(serializer_class_path, data_list, user_id)

        return Response({
            "message": f"Bulk update task started for {len(data_list)} items",
            "task_id": task.id,
            "total_items": len(data_list),
            "status_url": f"/api/operations/{task.id}/status/",
        }, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["put"], url_path="bulk")
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="unique_fields",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Comma-separated unique field names for upsert mode",
                examples=[OpenApiExample("Fields", value="account,date")]
            )
        ],
        request={
            "application/json": {
                "type": "array",
                "description": "Array of complete objects to replace or upsert",
            }
        },
        description="Replace multiple instances asynchronously. Supports both standard replace (with id fields) and upsert mode (with unique_fields parameter).",
        summary="Async bulk replace/upsert"
    )
    def bulk_replace(self, request):
        """Async bulk replace/upsert for large datasets."""
        data_list = request.data
        if not isinstance(data_list, list):
            return Response(
                {"error": "Expected array data for bulk operations."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not data_list:
            return Response(
                {"error": "Empty array provided"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if this is upsert mode
        unique_fields_param = request.query_params.get("unique_fields")
        if unique_fields_param:
            return self._bulk_upsert(request, data_list, unique_fields_param)

        # Standard bulk replace mode - validate ID fields
        for i, item in enumerate(data_list):
            if not isinstance(item, dict) or "id" not in item:
                return Response(
                    {"error": f"Item at index {i} is missing 'id' field"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Start async replace task
        serializer_class = self.get_serializer_class()
        serializer_class_path = f"{serializer_class.__module__}.{serializer_class.__name__}"
        user_id = request.user.id if request.user.is_authenticated else None
        task = async_replace_task.delay(serializer_class_path, data_list, user_id)

        return Response({
            "message": f"Bulk replace task started for {len(data_list)} items",
            "task_id": task.id,
            "total_items": len(data_list),
            "status_url": f"/api/operations/{task.id}/status/",
        }, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["delete"], url_path="bulk")
    @extend_schema(
        request={
            "application/json": {
                "type": "array",
                "description": "Array of IDs to delete",
                "items": {"type": "integer"},
            }
        },
        description="Delete multiple instances asynchronously via background processing.",
        summary="Async bulk delete"
    )
    def bulk_delete(self, request):
        """Async bulk delete for large datasets."""
        ids_list = request.data
        if not isinstance(ids_list, list):
            return Response(
                {"error": "Expected array of IDs for bulk delete."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not ids_list:
            return Response(
                {"error": "Empty array provided"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate IDs
        for i, item_id in enumerate(ids_list):
            if not isinstance(item_id, int):
                return Response(
                    {"error": f"Item at index {i} is not a valid ID"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Start async delete task
        model_class = self.get_queryset().model
        model_class_path = f"{model_class.__module__}.{model_class.__name__}"
        user_id = request.user.id if request.user.is_authenticated else None
        task = async_delete_task.delay(model_class_path, ids_list, user_id)

        return Response({
            "message": f"Bulk delete task started for {len(ids_list)} items",
            "task_id": task.id,
            "total_items": len(ids_list),
            "status_url": f"/api/operations/{task.id}/status/",
        }, status=status.HTTP_202_ACCEPTED)

    def _bulk_upsert(self, request, data_list, unique_fields_param):
        """Handle async bulk upsert operations."""
        unique_fields = [f.strip() for f in unique_fields_param.split(",") if f.strip()]
        update_fields_param = request.query_params.get("update_fields")
        update_fields = None
        if update_fields_param:
            update_fields = [f.strip() for f in update_fields_param.split(",") if f.strip()]

        if not unique_fields:
            return Response(
                {"error": "unique_fields parameter is required for upsert operations"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Auto-infer update_fields if not provided
        if not update_fields:
            update_fields = self._infer_update_fields(data_list, unique_fields)

        # Start async upsert task
        serializer_class = self.get_serializer_class()
        serializer_class_path = f"{serializer_class.__module__}.{serializer_class.__name__}"
        user_id = request.user.id if request.user.is_authenticated else None
        task = async_upsert_task.delay(serializer_class_path, data_list, unique_fields, update_fields, user_id)

        return Response({
            "message": f"Bulk upsert task started for {len(data_list)} items",
            "task_id": task.id,
            "total_items": len(data_list),
            "unique_fields": unique_fields,
            "update_fields": update_fields,
            "status_url": f"/api/operations/{task.id}/status/",
        }, status=status.HTTP_202_ACCEPTED)


# Legacy alias for backwards compatibility during migration
AsyncOperationsMixin = OperationsMixin
SyncUpsertMixin = OperationsMixin 