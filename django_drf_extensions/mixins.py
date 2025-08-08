"""
Operation mixins for DRF ViewSets.

Provides a unified mixin that enhances standard ViewSet endpoints with intelligent
sync/async routing and adds /bulk/ endpoints for background processing.
"""

import sys

from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.response import Response

# Optional OpenAPI schema support
try:
    from drf_spectacular.types import OpenApiTypes
    from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema

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
        INT = "integer"


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_serializer(self, *args, **kwargs):
        """Handle array data for serializers."""
        try:
            data = kwargs.get("data", None)
            if data is not None and isinstance(data, list):
                kwargs["many"] = True

            return super().get_serializer(*args, **kwargs)
        except Exception as e:
            raise

    # =============================================================================
    # Enhanced Standard ViewSet Methods (Sync Operations)
    # =============================================================================

    def list(self, request, *args, **kwargs):
        """
        Enhanced list endpoint that supports multi-get via ?ids= parameter.

        - GET /api/model/                    # Standard list
        - GET /api/model/?ids=1,2,3          # Sync multi-get (small datasets)
        """
        print(f"OperationsMixin.list() called with query_params: {request.query_params}", file=sys.stderr)
        ids_param = request.query_params.get("ids")
        if ids_param:
            print(f"OperationsMixin.list() - Found ids parameter: {ids_param}", file=sys.stderr)
            return self._sync_multi_get(request, ids_param)

        print(f"OperationsMixin.list() - No ids parameter, calling super().list()", file=sys.stderr)
        # Standard list behavior
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        """
        Enhanced create endpoint that supports sync upsert via query params.

        - POST /api/model/                                    # Standard single create
        - POST /api/model/?unique_fields=field1,field2       # Sync upsert (array data)
        """
        print(f"OperationsMixin.create() called with query_params: {request.query_params}, data type: {type(request.data)}", file=sys.stderr)
        unique_fields_param = request.query_params.get("unique_fields")
        if unique_fields_param and isinstance(request.data, list):
            print(f"OperationsMixin.create() - Found unique_fields parameter: {unique_fields_param}, data is list with {len(request.data)} items", file=sys.stderr)
            return self._sync_upsert(request, unique_fields_param)

        print(f"OperationsMixin.create() - No unique_fields or not array data, calling super().create()", file=sys.stderr)
        # Standard single create behavior
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        """
        Enhanced update endpoint that supports sync upsert via query params.

        - PUT /api/model/{id}/                               # Standard single update
        - PUT /api/model/?unique_fields=field1,field2       # Sync upsert (array data)
        """
        print(f"OperationsMixin.update() called with query_params: {request.query_params}, data type: {type(request.data)}", file=sys.stderr)
        unique_fields_param = request.query_params.get("unique_fields")
        if unique_fields_param and isinstance(request.data, list):
            print(f"OperationsMixin.update() - Found unique_fields parameter: {unique_fields_param}, data is list with {len(request.data)} items", file=sys.stderr)
            return self._sync_upsert(request, unique_fields_param)

        print(f"OperationsMixin.update() - No unique_fields or not array data, calling super().update()", file=sys.stderr)
        # Standard single update behavior
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        """
        Enhanced partial update endpoint that supports sync upsert via query params.

        - PATCH /api/model/{id}/                             # Standard single partial update
        - PATCH /api/model/?unique_fields=field1,field2     # Sync upsert (array data)
        """
        try:
            print(f"OperationsMixin.partial_update() called with query_params: {request.query_params}, data type: {type(request.data)}", file=sys.stderr)
            unique_fields_param = request.query_params.get("unique_fields")

            if unique_fields_param and isinstance(request.data, list):
                print(f"OperationsMixin.partial_update() - Found unique_fields parameter: {unique_fields_param}, data is list with {len(request.data)} items", file=sys.stderr)
                return self._sync_upsert(request, unique_fields_param)

            print(f"OperationsMixin.partial_update() - No unique_fields or not array data, calling super().partial_update()", file=sys.stderr)
            # Standard single partial update behavior
            return super().partial_update(request, *args, **kwargs)
        except Exception as e:
            print(f"OperationsMixin.partial_update() - Exception occurred: {e}", file=sys.stderr)
            raise

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="unique_fields",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Comma-separated unique field names for upsert mode",
                examples=[OpenApiExample("Fields", value="account_number,email")],
            ),
            OpenApiParameter(
                name="update_fields",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Comma-separated field names to update (optional, auto-inferred if not provided)",
                examples=[OpenApiExample("Fields", value="business,status")],
            ),
            OpenApiParameter(
                name="max_items",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Maximum items for sync processing (default: 50)",
                examples=[OpenApiExample("Max Items", value=50)],
            ),
            OpenApiParameter(
                name="partial_success",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Allow partial success (default: false). Set to 'true' to allow some records to succeed while others fail.",
                examples=[OpenApiExample("Partial Success", value="true")],
            ),
            OpenApiParameter(
                name="include_results",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="If 'false', skips serializing response results to improve performance (default: true)",
                examples=[OpenApiExample("Include Results", value="false")],
            ),
            OpenApiParameter(
                name="db_batch_size",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Optional database batch_size for bulk_create (default: ORM default)",
                examples=[OpenApiExample("DB Batch Size", value=2000)],
            ),
        ],
        request={
            "application/json": {
                "type": "array",
                "description": "Array of objects to upsert",
            }
        },
        responses={
            200: {
                "description": "Upsert completed successfully - returns updated/created objects",
                "oneOf": [
                    {"type": "object", "description": "Single object response"},
                    {"type": "array", "description": "Multiple objects response"},
                ],
            },
            207: {
                "description": "Partial success - some records succeeded, others failed",
                "type": "object",
                "properties": {
                    "success": {
                        "type": "array",
                        "description": "Successfully processed records",
                    },
                    "errors": {
                        "type": "array",
                        "description": "Failed records with error details",
                    },
                    "summary": {"type": "object", "description": "Operation summary"},
                },
            },
            400: {"description": "Bad request - missing parameters or invalid data"},
        },
        description="Upsert multiple instances synchronously. Creates new records or updates existing ones based on unique fields. Defaults to all-or-nothing behavior unless partial_success=true.",
        summary="Sync upsert (PATCH)",
    )
    def patch(self, request, *args, **kwargs):
        """
        Handle PATCH requests on list endpoint for sync upsert.

        DRF doesn't handle PATCH on list endpoints by default, so we add this method
        to support: PATCH /api/model/?unique_fields=field1,field2
        """
        print(f"OperationsMixin.patch() called with query_params: {request.query_params}, data type: {type(request.data)}", file=sys.stderr)
        unique_fields_param = request.query_params.get("unique_fields")
        
        if unique_fields_param and isinstance(request.data, list):
            print(f"OperationsMixin.patch() - Found unique_fields parameter: {unique_fields_param}, data is list with {len(request.data)} items", file=sys.stderr)
            return self._sync_upsert(request, unique_fields_param)

        print(f"OperationsMixin.patch() - No unique_fields or not array data, returning 400 error", file=sys.stderr)
        # If no unique_fields or not array data, this is invalid
        return Response(
            {
                "error": "PATCH on list endpoint requires 'unique_fields' parameter and array data"
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="unique_fields",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Comma-separated unique field names for upsert mode",
                examples=[OpenApiExample("Fields", value="account_number,email")],
            ),
            OpenApiParameter(
                name="update_fields",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Comma-separated field names to update (optional, auto-inferred if not provided)",
                examples=[OpenApiExample("Fields", value="business,status")],
            ),
            OpenApiParameter(
                name="max_items",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Maximum items for sync processing (default: 50)",
                examples=[OpenApiExample("Max Items", value=50)],
            ),
            OpenApiParameter(
                name="partial_success",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Allow partial success (default: false). Set to 'true' to allow some records to succeed while others fail.",
                examples=[OpenApiExample("Partial Success", value="true")],
            ),
            OpenApiParameter(
                name="include_results",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="If 'false', skips serializing response results to improve performance (default: true)",
                examples=[OpenApiExample("Include Results", value="false")],
            ),
            OpenApiParameter(
                name="db_batch_size",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Optional database batch_size for bulk_create (default: ORM default)",
                examples=[OpenApiExample("DB Batch Size", value=2000)],
            ),
        ],
        request={
            "application/json": {
                "type": "array",
                "description": "Array of objects to upsert",
            }
        },
        responses={
            200: {
                "description": "Upsert completed successfully - returns updated/created objects",
                "oneOf": [
                    {"type": "object", "description": "Single object response"},
                    {"type": "array", "description": "Multiple objects response"},
                ],
            },
            207: {
                "description": "Partial success - some records succeeded, others failed",
                "type": "object",
                "properties": {
                    "success": {
                        "type": "array",
                        "description": "Successfully processed records",
                    },
                    "errors": {
                        "type": "array",
                        "description": "Failed records with error details",
                    },
                    "summary": {"type": "object", "description": "Operation summary"},
                },
            },
            400: {"description": "Bad request - missing parameters or invalid data"},
        },
        description="Upsert multiple instances synchronously. Creates new records or updates existing ones based on unique fields. Defaults to all-or-nothing behavior unless partial_success=true.",
        summary="Sync upsert (PUT)",
    )
    def put(self, request, *args, **kwargs):
        """
        Handle PUT requests on list endpoint for sync upsert.

        DRF doesn't handle PUT on list endpoints by default, so we add this method
        to support: PUT /api/model/?unique_fields=field1,field2
        """
        print(f"OperationsMixin.put() called with query_params: {request.query_params}, data type: {type(request.data)}", file=sys.stderr)
        unique_fields_param = request.query_params.get("unique_fields")
        if unique_fields_param and isinstance(request.data, list):
            print(f"OperationsMixin.put() - Found unique_fields parameter: {unique_fields_param}, data is list with {len(request.data)} items", file=sys.stderr)
            return self._sync_upsert(request, unique_fields_param)

        print(f"OperationsMixin.put() - No unique_fields or not array data, returning 400 error", file=sys.stderr)
        # If no unique_fields or not array data, this is invalid
        return Response(
            {
                "error": "PUT on list endpoint requires 'unique_fields' parameter and array data"
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # =============================================================================
    # Sync Operation Implementations
    # =============================================================================

    def _sync_multi_get(self, request, ids_param):
        """Handle sync multi-get for small datasets."""
        print(f"OperationsMixin._sync_multi_get() called with ids_param: {ids_param}", file=sys.stderr)
        try:
            ids_list = [int(id_str.strip()) for id_str in ids_param.split(",")]
            print(f"OperationsMixin._sync_multi_get() - Parsed ids_list: {ids_list}", file=sys.stderr)
        except ValueError:
            print(f"OperationsMixin._sync_multi_get() - Invalid ID format: {ids_param}", file=sys.stderr)
            return Response(
                {"error": "Invalid ID format. Use comma-separated integers."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Limit for sync processing
        max_sync_items = 100
        if len(ids_list) > max_sync_items:
            print(f"OperationsMixin._sync_multi_get() - Too many items: {len(ids_list)} > {max_sync_items}", file=sys.stderr)
            return Response(
                {
                    "error": f"Too many items for sync processing. Use /bulk/ endpoint for >{max_sync_items} items.",
                    "provided_items": len(ids_list),
                    "max_sync_items": max_sync_items,
                    "suggestion": "Use GET /bulk/?ids=... for async processing",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Process sync multi-get
        print(f"OperationsMixin._sync_multi_get() - Processing {len(ids_list)} items", file=sys.stderr)
        queryset = self.get_queryset().filter(id__in=ids_list)
        serializer = self.get_serializer(queryset, many=True)

        print(f"OperationsMixin._sync_multi_get() - Returning {len(serializer.data)} results", file=sys.stderr)
        return Response(
            {
                "count": len(serializer.data),
                "results": serializer.data,
                "is_sync": True,
            }
        )

    def _sync_upsert(self, request, unique_fields_param):
        """Handle sync upsert operations for small datasets."""
        print(f"OperationsMixin._sync_upsert() called with unique_fields_param: {unique_fields_param}", file=sys.stderr)
        # Parse parameters
        unique_fields = [f.strip() for f in unique_fields_param.split(",") if f.strip()]
        print(f"OperationsMixin._sync_upsert() - Parsed unique_fields: {unique_fields}", file=sys.stderr)
        
        update_fields_param = request.query_params.get("update_fields")
        update_fields = None
        if update_fields_param:
            update_fields = [
                f.strip() for f in update_fields_param.split(",") if f.strip()
            ]
            print(f"OperationsMixin._sync_upsert() - Parsed update_fields: {update_fields}", file=sys.stderr)

        # Check if partial success is enabled
        partial_success = (
            request.query_params.get("partial_success", "false").lower() == "true"
        )
        print(f"OperationsMixin._sync_upsert() - partial_success: {partial_success}", file=sys.stderr)

        # Check if response results should be included (default: true)
        include_results = request.query_params.get("include_results", "true").lower() == "true"
        print(f"OperationsMixin._sync_upsert() - include_results: {include_results}", file=sys.stderr)

        # Optional DB batch size for bulk_create
        db_batch_size_param = request.query_params.get("db_batch_size")
        db_batch_size = None
        if db_batch_size_param is not None:
            try:
                db_batch_size = int(db_batch_size_param)
                if db_batch_size <= 0:
                    db_batch_size = None
            except ValueError:
                db_batch_size = None
        print(f"OperationsMixin._sync_upsert() - db_batch_size: {db_batch_size}", file=sys.stderr)

        data_list = request.data
        if not isinstance(data_list, list):
            print(f"OperationsMixin._sync_upsert() - Expected array data, got: {type(data_list)}", file=sys.stderr)
            return Response(
                {"error": "Expected array data for upsert operations."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        print(f"OperationsMixin._sync_upsert() - Processing {len(data_list)} items", file=sys.stderr)
        # Limit for sync processing
        max_sync_items = int(request.query_params.get("max_items", 50))
        if len(data_list) > max_sync_items:
            print(f"OperationsMixin._sync_upsert() - Too many items: {len(data_list)} > {max_sync_items}", file=sys.stderr)
            return Response(
                {
                    "error": f"Too many items for sync processing. Use /bulk/ endpoint for >{max_sync_items} items.",
                    "provided_items": len(data_list),
                    "max_sync_items": max_sync_items,
                    "suggestion": "Use PATCH /bulk/?unique_fields=... for async processing",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not unique_fields:
            print(f"OperationsMixin._sync_upsert() - No unique_fields provided", file=sys.stderr)
            return Response(
                {"error": "unique_fields parameter is required for upsert operations"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Auto-infer update_fields if not provided
        if not update_fields:
            update_fields = self._infer_update_fields(data_list, unique_fields)
            print(f"OperationsMixin._sync_upsert() - Auto-inferred update_fields: {update_fields}", file=sys.stderr)

        # Perform sync upsert
        try:
            print(f"OperationsMixin._sync_upsert() - Starting sync upsert operation", file=sys.stderr)
            result = self._perform_sync_upsert(
                data_list, unique_fields, update_fields, partial_success, request, include_results, db_batch_size
            )
            print(f"OperationsMixin._sync_upsert() - Sync upsert completed successfully", file=sys.stderr)
            return result
        except Exception as e:
            print(f"OperationsMixin._sync_upsert() - Exception occurred: {e}", file=sys.stderr)
            return Response(
                {"error": f"Upsert operation failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _perform_sync_upsert(
        self,
        data_list,
        unique_fields,
        update_fields,
        partial_success=False,
        request=None,
        include_results=True,
        db_batch_size=None,
    ):
        """Perform the actual sync upsert operation using bulk_create with update_conflicts."""
        from django.db import transaction
        from rest_framework import status

        print(f"OperationsMixin._perform_sync_upsert() called with {len(data_list)} items, unique_fields: {unique_fields}, update_fields: {update_fields}, partial_success: {partial_success}, include_results: {include_results}, db_batch_size: {db_batch_size}", file=sys.stderr)

        serializer_class = self.get_serializer_class()
        model_class = serializer_class.Meta.model
        print(f"OperationsMixin._perform_sync_upsert() - Model class: {model_class.__name__}", file=sys.stderr)

        created_ids = []
        updated_ids = []
        errors = []
        instances = []
        success_data = []
        validated_data = []

        # Use bulk_create with update_conflicts for upsert - no loops!
        try:
            # Determine which fields to update (exclude unique fields)
            # Map attname (e.g., field_id) to model field names to ensure DB accepts field list
            attname_to_name = {f.attname: f.name for f in model_class._meta.fields}
            # Normalize unique_fields to model field names
            normalized_unique_fields = [attname_to_name.get(f, f) for f in unique_fields]

            if update_fields:
                normalized_update_fields = [attname_to_name.get(f, f) for f in update_fields]
                fields_to_update = [f for f in normalized_update_fields if f not in normalized_unique_fields]
            else:
                # Auto-infer update fields (all fields except unique fields)
                fields_to_update = []
                for field in model_class._meta.fields:
                    if field.name not in normalized_unique_fields:
                        fields_to_update.append(field.name)

            print(f"OperationsMixin._perform_sync_upsert() - Fields to update: {fields_to_update}", file=sys.stderr)

            # Validate and deserialize data using serializer first
            print(f"OperationsMixin._perform_sync_upsert() - Validating data with serializer", file=sys.stderr)
            is_partial = bool(getattr(request, "method", "").upper() == "PATCH")
            serializer = serializer_class(data=data_list, many=True, partial=is_partial)
            if not serializer.is_valid():
                print(f"OperationsMixin._perform_sync_upsert() - Serializer validation failed: {serializer.errors}", file=sys.stderr)
                if not partial_success:
                    return Response(
                        {
                            "error": "Data validation failed",
                            "errors": serializer.errors,
                            "total_items": len(data_list),
                            "failed_items": len(data_list),
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                else:
                    # Add validation errors for partial success
                    for index, item_errors in enumerate(serializer.errors):
                        if item_errors:
                            errors.append(
                                {
                                    "index": index,
                                    "error": f"Validation failed: {item_errors}",
                                    "data": data_list[index],
                                }
                            )
                    # Continue with valid data only
                    valid_data = [item for i, item in enumerate(data_list) if not serializer.errors[i]]
                    if not valid_data:
                        return Response(
                            {
                                "error": "All items failed validation",
                                "errors": errors,
                                "total_items": len(data_list),
                                "failed_items": len(data_list),
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    # Re-validate the valid data
                    serializer = serializer_class(data=valid_data, many=True, partial=is_partial)
                    serializer.is_valid()  # Should be valid now
                    data_list = valid_data

            # Get validated data from serializer (this ensures proper field type conversion)
            validated_data = serializer.validated_data
            print(f"OperationsMixin._perform_sync_upsert() - Using validated data with {len(validated_data)} items", file=sys.stderr)

            # Single bulk_create call with update_conflicts for upsert
            print(f"OperationsMixin._perform_sync_upsert() - Starting bulk_create with update_conflicts", file=sys.stderr)
            created_instances = model_class.objects.bulk_create(
                [model_class(**item_data) for item_data in validated_data],  # Use validated data
                batch_size=db_batch_size,
                ignore_conflicts=False,
                update_conflicts=True,
                update_fields=fields_to_update,
                unique_fields=normalized_unique_fields,
            )
            print(f"OperationsMixin._perform_sync_upsert() - bulk_create completed, created {len(created_instances)} instances", file=sys.stderr)

            if include_results:
                # Single bulk serialization
                serializer = serializer_class(created_instances, many=True)
                success_data = serializer.data
                print(f"OperationsMixin._perform_sync_upsert() - Serialized {len(success_data)} items", file=sys.stderr)
            else:
                success_data = []
                print(f"OperationsMixin._perform_sync_upsert() - Skipping serialization due to include_results=False", file=sys.stderr)

        except Exception as e:
            print(f"OperationsMixin._perform_sync_upsert() - Exception during bulk_create: {e}", file=sys.stderr)
            if not partial_success:
                return Response(
                    {
                        "error": "Bulk upsert failed",
                        "errors": [{"error": str(e)}],
                        "total_items": len(data_list),
                        "failed_items": len(data_list),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            else:
                # Add all items to errors for partial success
                for index, item_data in enumerate(data_list):
                    errors.append(
                        {
                            "index": index,
                            "error": f"Bulk upsert failed: {str(e)}",
                            "data": item_data,
                        }
                    )

        # Handle response based on mode
        if partial_success:
            # Return partial success response with detailed information
            summary = {
                "total_items": len(data_list),
                "successful_items": len(success_data) if include_results else len(validated_data),
                "failed_items": len(errors),
                "created_count": len(created_ids),
                "updated_count": len(updated_ids),
            }

            print(f"OperationsMixin._perform_sync_upsert() - Returning partial success response: {summary}", file=sys.stderr)
            return Response(
                {"success": success_data if include_results else None, "errors": errors, "summary": summary},
                status=status.HTTP_207_MULTI_STATUS,
            )
        else:
            # Return standard DRF response for all-or-nothing
            if include_results:
                if len(instances) == 1:
                    print(f"OperationsMixin._perform_sync_upsert() - Returning single object response", file=sys.stderr)
                    return Response(success_data[0], status=status.HTTP_200_OK)
                else:
                    print(f"OperationsMixin._perform_sync_upsert() - Returning multiple objects response with {len(success_data)} items", file=sys.stderr)
                    return Response(success_data, status=status.HTTP_200_OK)
            else:
                print(f"OperationsMixin._perform_sync_upsert() - Returning 200 OK with no results (include_results=False)", file=sys.stderr)
                return Response(status=status.HTTP_200_OK)

    def _infer_update_fields(self, data_list, unique_fields):
        """Auto-infer update fields from data payload."""
        print(f"OperationsMixin._infer_update_fields() called with {len(data_list)} items, unique_fields: {unique_fields}", file=sys.stderr)
        if not data_list:
            print(f"OperationsMixin._infer_update_fields() - No data_list, returning empty list", file=sys.stderr)
            return []

        all_fields = set()
        for item in data_list:
            if isinstance(item, dict):
                all_fields.update(item.keys())

        update_fields = list(all_fields - set(unique_fields))
        update_fields.sort()
        print(f"OperationsMixin._infer_update_fields() - Inferred update_fields: {update_fields}", file=sys.stderr)
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
                examples=[OpenApiExample("IDs", value="1,2,3,4,5")],
            )
        ],
        description="Retrieve multiple instances asynchronously via background processing.",
        summary="Async bulk retrieve",
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
        serializer_class_path = (
            f"{serializer_class.__module__}.{serializer_class.__name__}"
        )

        query_data = {"ids": ids_list}
        user_id = request.user.id if request.user.is_authenticated else None
        task = async_get_task.delay(
            model_class_path, serializer_class_path, query_data, user_id
        )

        return Response(
            {
                "message": f"Bulk get task started for {len(ids_list)} items",
                "task_id": task.id,
                "total_items": len(ids_list),
                "status_url": f"/api/operations/{task.id}/status/",
                "is_async": True,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=False, methods=["post"], url_path="bulk")
    @extend_schema(
        request={
            "application/json": {
                "type": "array",
                "description": "Array of objects to create",
            }
        },
        description="Create multiple instances asynchronously via background processing.",
        summary="Async bulk create",
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
        serializer_class_path = (
            f"{serializer_class.__module__}.{serializer_class.__name__}"
        )
        user_id = request.user.id if request.user.is_authenticated else None
        task = async_create_task.delay(serializer_class_path, data_list, user_id)

        return Response(
            {
                "message": f"Bulk create task started for {len(data_list)} items",
                "task_id": task.id,
                "total_items": len(data_list),
                "status_url": f"/api/operations/{task.id}/status/",
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=False, methods=["patch"], url_path="bulk")
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="unique_fields",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Comma-separated unique field names for upsert mode",
                examples=[OpenApiExample("Fields", value="account,date")],
            )
        ],
        request={
            "application/json": {
                "type": "array",
                "description": "Array of objects to update or upsert",
            }
        },
        description="Update multiple instances asynchronously. Supports both standard update (with id fields) and upsert mode (with unique_fields parameter).",
        summary="Async bulk update/upsert",
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
        serializer_class_path = (
            f"{serializer_class.__module__}.{serializer_class.__name__}"
        )
        user_id = request.user.id if request.user.is_authenticated else None
        task = async_update_task.delay(serializer_class_path, data_list, user_id)

        return Response(
            {
                "message": f"Bulk update task started for {len(data_list)} items",
                "task_id": task.id,
                "total_items": len(data_list),
                "status_url": f"/api/operations/{task.id}/status/",
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=False, methods=["put"], url_path="bulk")
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="unique_fields",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Comma-separated unique field names for upsert mode",
                examples=[OpenApiExample("Fields", value="account,date")],
            )
        ],
        request={
            "application/json": {
                "type": "array",
                "description": "Array of complete objects to replace or upsert",
            }
        },
        description="Replace multiple instances asynchronously. Supports both standard replace (with id fields) and upsert mode (with unique_fields parameter).",
        summary="Async bulk replace/upsert",
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
        serializer_class_path = (
            f"{serializer_class.__module__}.{serializer_class.__name__}"
        )
        user_id = request.user.id if request.user.is_authenticated else None
        task = async_replace_task.delay(serializer_class_path, data_list, user_id)

        return Response(
            {
                "message": f"Bulk replace task started for {len(data_list)} items",
                "task_id": task.id,
                "total_items": len(data_list),
                "status_url": f"/api/operations/{task.id}/status/",
            },
            status=status.HTTP_202_ACCEPTED,
        )

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
        summary="Async bulk delete",
    )
    def bulk_delete(self, request):
        """Async bulk delete for large datasets using efficient bulk operations."""
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

        # Start async delete task with optimized bulk delete
        model_class = self.get_queryset().model
        model_class_path = f"{model_class.__module__}.{model_class.__name__}"
        user_id = request.user.id if request.user.is_authenticated else None
        task = async_delete_task.delay(model_class_path, ids_list, user_id)

        return Response(
            {
                "message": f"Bulk delete task started for {len(ids_list)} items",
                "task_id": task.id,
                "total_items": len(ids_list),
                "status_url": f"/api/operations/{task.id}/status/",
            },
            status=status.HTTP_202_ACCEPTED,
        )

    def _bulk_upsert(self, request, data_list, unique_fields_param):
        """Handle async bulk upsert operations."""
        unique_fields = [f.strip() for f in unique_fields_param.split(",") if f.strip()]
        update_fields_param = request.query_params.get("update_fields")
        update_fields = None
        if update_fields_param:
            update_fields = [
                f.strip() for f in update_fields_param.split(",") if f.strip()
            ]

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
        serializer_class_path = (
            f"{serializer_class.__module__}.{serializer_class.__name__}"
        )
        user_id = request.user.id if request.user.is_authenticated else None
        task = async_upsert_task.delay(
            serializer_class_path, data_list, unique_fields, update_fields, user_id
        )

        return Response(
            {
                "message": f"Bulk upsert task started for {len(data_list)} items",
                "task_id": task.id,
                "total_items": len(data_list),
                "unique_fields": unique_fields,
                "update_fields": update_fields,
                "status_url": f"/api/operations/{task.id}/status/",
            },
            status=status.HTTP_202_ACCEPTED,
        )


# Legacy alias for backwards compatibility during migration
AsyncOperationsMixin = OperationsMixin
SyncUpsertMixin = OperationsMixin
