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

        - PUT /api/model/{id}/                               # Standard single update
        - PUT /api/model/?unique_fields=field1,field2       # Sync upsert (array data)
        """
        unique_fields_param = request.query_params.get("unique_fields")
        if unique_fields_param and isinstance(request.data, list):
            return self._sync_upsert(request, unique_fields_param)

        # Standard single update behavior
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        """
        Enhanced partial update endpoint that supports sync upsert via query params.

        - PATCH /api/model/{id}/                             # Standard single partial update
        - PATCH /api/model/?unique_fields=field1,field2     # Sync upsert (array data)
        """
        try:
            unique_fields_param = request.query_params.get("unique_fields")

            if unique_fields_param and isinstance(request.data, list):
                return self._sync_upsert(request, unique_fields_param)

            # Standard single partial update behavior
            return super().partial_update(request, *args, **kwargs)
        except Exception as e:
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
        print(f"=== DEBUG: PATCH method called ===", file=sys.stderr)
        print(f"DEBUG: request.query_params = {request.query_params}", file=sys.stderr)
        print(f"DEBUG: request.data = {request.data}", file=sys.stderr)
        print(f"DEBUG: isinstance(request.data, list) = {isinstance(request.data, list)}", file=sys.stderr)
        
        unique_fields_param = request.query_params.get("unique_fields")
        print(f"DEBUG: unique_fields_param = {unique_fields_param}", file=sys.stderr)
        
        if unique_fields_param and isinstance(request.data, list):
            print(f"DEBUG: Calling _sync_upsert", file=sys.stderr)
            return self._sync_upsert(request, unique_fields_param)

        # If no unique_fields or not array data, this is invalid
        print(f"DEBUG: Invalid PATCH request - no unique_fields or not array data", file=sys.stderr)
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
        unique_fields_param = request.query_params.get("unique_fields")
        if unique_fields_param and isinstance(request.data, list):
            return self._sync_upsert(request, unique_fields_param)

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
                    "suggestion": "Use GET /bulk/?ids=... for async processing",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Process sync multi-get
        queryset = self.get_queryset().filter(id__in=ids_list)
        serializer = self.get_serializer(queryset, many=True)

        return Response(
            {
                "count": len(serializer.data),
                "results": serializer.data,
                "is_sync": True,
            }
        )

    def _sync_upsert(self, request, unique_fields_param):
        """Handle sync upsert operations for small datasets."""
        print(f"=== DEBUG: Starting _sync_upsert ===", file=sys.stderr)
        print(f"DEBUG: unique_fields_param = {unique_fields_param}", file=sys.stderr)
        print(f"DEBUG: request.data = {request.data}", file=sys.stderr)
        print(f"DEBUG: request.query_params = {request.query_params}", file=sys.stderr)
        
        # Parse parameters
        unique_fields = [f.strip() for f in unique_fields_param.split(",") if f.strip()]
        print(f"DEBUG: parsed unique_fields = {unique_fields}", file=sys.stderr)
        
        update_fields_param = request.query_params.get("update_fields")
        update_fields = None
        if update_fields_param:
            update_fields = [
                f.strip() for f in update_fields_param.split(",") if f.strip()
            ]
        print(f"DEBUG: update_fields = {update_fields}", file=sys.stderr)

        # Check if partial success is enabled
        partial_success = (
            request.query_params.get("partial_success", "false").lower() == "true"
        )
        print(f"DEBUG: partial_success = {partial_success}", file=sys.stderr)

        data_list = request.data
        if not isinstance(data_list, list):
            print(f"DEBUG: data_list is not a list: {type(data_list)}", file=sys.stderr)
            return Response(
                {"error": "Expected array data for upsert operations."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Limit for sync processing
        max_sync_items = int(request.query_params.get("max_items", 50))
        if len(data_list) > max_sync_items:
            print(f"DEBUG: Too many items: {len(data_list)} > {max_sync_items}", file=sys.stderr)
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
            print(f"DEBUG: No unique fields provided", file=sys.stderr)
            return Response(
                {"error": "unique_fields parameter is required for upsert operations"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Auto-infer update_fields if not provided
        if not update_fields:
            update_fields = self._infer_update_fields(data_list, unique_fields)
            print(f"DEBUG: Auto-inferred update_fields = {update_fields}", file=sys.stderr)

        # Perform sync upsert
        try:
            print(f"DEBUG: Calling _perform_sync_upsert", file=sys.stderr)
            result = self._perform_sync_upsert(
                data_list, unique_fields, update_fields, partial_success, request
            )
            print(f"DEBUG: _perform_sync_upsert returned: {result}", file=sys.stderr)
            return result
        except Exception as e:
            print(f"DEBUG: Exception in _sync_upsert: {e}", file=sys.stderr)
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
    ):
        """Perform the actual sync upsert operation using bulk_create for new records."""
        from django.db import transaction
        from rest_framework import status

        print(f"=== DEBUG: Starting _perform_sync_upsert ===", file=sys.stderr)
        print(f"DEBUG: data_list = {data_list}", file=sys.stderr)
        print(f"DEBUG: unique_fields = {unique_fields}", file=sys.stderr)
        print(f"DEBUG: update_fields = {update_fields}", file=sys.stderr)
        print(f"DEBUG: partial_success = {partial_success}", file=sys.stderr)

        serializer_class = self.get_serializer_class()
        model_class = serializer_class.Meta.model

        print(f"DEBUG: serializer_class = {serializer_class}", file=sys.stderr)
        print(f"DEBUG: model_class = {model_class}", file=sys.stderr)

        created_ids = []
        updated_ids = []
        errors = []
        instances = []
        success_data = []

        # First pass: check for missing unique fields only
        validation_errors = []
        for index, item_data in enumerate(data_list):
            print(f"DEBUG: Processing item {index}: {item_data}", file=sys.stderr)
            try:
                # Check if this is a create or update scenario
                unique_filter = {}
                missing_fields = []
                for field in unique_fields:
                    if field in item_data:
                        unique_filter[field] = item_data[field]
                        print(f"DEBUG: Found unique field '{field}' = {item_data[field]}", file=sys.stderr)
                    else:
                        missing_fields.append(field)
                        print(f"DEBUG: Missing unique field '{field}'", file=sys.stderr)

                if missing_fields:
                    validation_error = {
                        "index": index,
                        "error": f"Missing required unique fields: {missing_fields}",
                        "data": item_data,
                    }
                    validation_errors.append(validation_error)
                    print(f"DEBUG: Validation error for item {index}: {validation_error}", file=sys.stderr)
                    continue

                # Skip full validation here - will validate during actual operation
                # This prevents SlugRelatedField validation issues during initial check

            except (ValidationError, ValueError) as e:
                validation_error = {"index": index, "error": str(e), "data": item_data}

                # Add debugging info for SlugRelatedField issues
                if "expected a number but got" in str(e):
                    validation_error["debug_info"] = {
                        "error_type": "SlugRelatedField_validation",
                        "issue": "SlugRelatedField failed to convert slug to object",
                        "suggestion": "Check if the slug values exist in the related queryset",
                    }

                validation_errors.append(validation_error)
                print(f"DEBUG: Validation error for item {index}: {validation_error}", file=sys.stderr)

        # If not allowing partial success and there are validation errors, fail immediately
        if not partial_success and validation_errors:
            print(f"DEBUG: Failing due to validation errors: {validation_errors}", file=sys.stderr)
            return Response(
                {
                    "error": "Validation failed for one or more records",
                    "errors": validation_errors,
                    "total_items": len(data_list),
                    "failed_items": len(validation_errors),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Second pass: separate creates and updates for bulk operations
        to_create = []
        to_update = []
        create_indices = []
        update_indices = []

        for index, item_data in enumerate(data_list):
            print(f"DEBUG: Second pass - Processing item {index}: {item_data}", file=sys.stderr)
            try:
                # Check if this item already failed validation
                failed_validation = any(
                    error["index"] == index for error in validation_errors
                )
                if failed_validation:
                    print(f"DEBUG: Item {index} failed validation, skipping", file=sys.stderr)
                    if partial_success:
                        error_to_add = next(
                            error
                            for error in validation_errors
                            if error["index"] == index
                        )
                        errors.append(error_to_add)
                    continue

                # Check if this is a create or update scenario
                lookup_filter = {}

                # Create a temporary serializer to check field types
                temp_serializer = serializer_class()
                serializer_fields = temp_serializer.get_fields()

                print(f"DEBUG: Serializer fields: {list(serializer_fields.keys())}", file=sys.stderr)

                for field in unique_fields:
                    print(f"DEBUG: Processing unique field '{field}'", file=sys.stderr)
                    # Check if this field is a SlugRelatedField in the serializer
                    serializer_field = serializer_fields.get(field)
                    print(f"DEBUG: Serializer field for '{field}': {serializer_field}", file=sys.stderr)
                    print(f"DEBUG: Field type: {type(serializer_field)}", file=sys.stderr)
                    
                    if serializer_field and isinstance(
                        serializer_field, serializers.SlugRelatedField
                    ):
                        print(f"DEBUG: '{field}' is a SlugRelatedField", file=sys.stderr)
                        # For SlugRelatedField, we need to convert the slug to the actual object
                        # and then use the object's ID for the lookup
                        try:
                            # Get the related object using the slug
                            print(f"DEBUG: Looking up {field} with value: {item_data[field]}", file=sys.stderr)
                            print(f"DEBUG: SlugRelatedField queryset: {serializer_field.queryset}", file=sys.stderr)
                            print(f"DEBUG: SlugRelatedField slug_field: {serializer_field.slug_field}", file=sys.stderr)
                            
                            related_obj = serializer_field.queryset.get(
                                **{serializer_field.slug_field: item_data[field]}
                            )
                            print(f"DEBUG: Found related object: {related_obj}", file=sys.stderr)
                            lookup_filter[f"{field}_id"] = related_obj.id
                            print(f"DEBUG: Added to lookup_filter: {field}_id = {related_obj.id}", file=sys.stderr)
                        except Exception as e:
                            print(f"DEBUG: Error looking up {field}: {e}", file=sys.stderr)
                            # If we can't convert, skip this field for now
                            continue
                    else:
                        print(f"DEBUG: '{field}' is not a SlugRelatedField", file=sys.stderr)
                        # For regular fields, use the original logic
                        if hasattr(model_class, field) and hasattr(
                            getattr(model_class, field), "field"
                        ):
                            field_obj = getattr(model_class, field).field
                            print(f"DEBUG: Field object for '{field}': {field_obj}", file=sys.stderr)
                            if (
                                hasattr(field_obj, "related_model")
                                and field_obj.related_model
                            ):
                                # This is a foreign key, use _id suffix for lookup
                                print(f"DEBUG: '{field}' is a foreign key, using {field}_id", file=sys.stderr)
                                lookup_filter[f"{field}_id"] = item_data[field]
                            else:
                                print(f"DEBUG: '{field}' is not a foreign key", file=sys.stderr)
                                lookup_filter[field] = item_data[field]
                        else:
                            print(f"DEBUG: '{field}' is a regular field", file=sys.stderr)
                            lookup_filter[field] = item_data[field]

                print(f"DEBUG: Final lookup_filter: {lookup_filter}", file=sys.stderr)

                # Check if record exists using raw data first
                existing_instance = self.get_queryset().filter(**lookup_filter).first()
                print(f"DEBUG: Existing instance found: {existing_instance}", file=sys.stderr)

                if existing_instance:
                    # Update existing record
                    to_update.append((index, item_data, existing_instance))
                    update_indices.append(index)
                    print(f"DEBUG: Added to update list: index {index}", file=sys.stderr)
                else:
                    # Create new record
                    to_create.append((index, item_data))
                    create_indices.append(index)
                    print(f"DEBUG: Added to create list: index {index}", file=sys.stderr)

            except (ValidationError, ValueError) as e:
                error_info = {"index": index, "error": str(e), "data": item_data}
                errors.append(error_info)
                print(f"DEBUG: Error processing item {index}: {error_info}", file=sys.stderr)

                if not partial_success:
                    return Response(
                        {
                            "error": "Processing failed",
                            "errors": [error_info],
                            "total_items": len(data_list),
                            "failed_items": 1,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        print(f"DEBUG: To create: {len(to_create)} items", file=sys.stderr)
        print(f"DEBUG: To update: {len(to_update)} items", file=sys.stderr)

        # Process creates using bulk_create
        if to_create:
            print(f"DEBUG: Processing {len(to_create)} items to create", file=sys.stderr)
            try:
                # Validate all create data first
                create_objects = []
                create_serializers = []

                for index, item_data in to_create:
                    print(f"DEBUG: Validating create data for index {index}: {item_data}", file=sys.stderr)
                    serializer = serializer_class(data=item_data)
                    if serializer.is_valid():
                        validated_data = serializer.validated_data
                        print(f"DEBUG: Validated data for index {index}: {validated_data}", file=sys.stderr)
                        # Create model instance without saving
                        instance = model_class(**validated_data)
                        create_objects.append(instance)
                        create_serializers.append((index, serializer))
                        print(f"DEBUG: Added to create_objects: {instance}", file=sys.stderr)
                    else:
                        error_info = {
                            "index": index,
                            "error": str(serializer.errors),
                            "data": item_data,
                        }
                        print(f"DEBUG: Validation failed for create index {index}: {serializer.errors}", file=sys.stderr)
                        errors.append(error_info)

                        if not partial_success:
                            return Response(
                                {
                                    "error": "Validation failed during processing",
                                    "errors": [error_info],
                                    "total_items": len(data_list),
                                    "failed_items": 1,
                                },
                                status=status.HTTP_400_BAD_REQUEST,
                            )

                # Use bulk_create for new records
                if create_objects:
                    print(f"DEBUG: Performing bulk_create with {len(create_objects)} objects", file=sys.stderr)
                    created_instances = model_class.objects.bulk_create(
                        create_objects,
                        batch_size=1000,  # Adjust batch size as needed
                        ignore_conflicts=False,
                    )
                    print(f"DEBUG: Created {len(created_instances)} instances", file=sys.stderr)

                    # Collect created IDs and serialize for response
                    for i, instance in enumerate(created_instances):
                        index, serializer = create_serializers[i]
                        created_ids.append(instance.id)
                        instances.append(instance)
                        print(f"DEBUG: Created instance {instance.id} for index {index}", file=sys.stderr)

                        # Serialize for response
                        instance_serializer = serializer_class(instance)
                        success_data.append(instance_serializer.data)

            except Exception as e:
                print(f"DEBUG: Exception during bulk_create: {e}", file=sys.stderr)
                if not partial_success:
                    return Response(
                        {
                            "error": "Bulk create failed",
                            "errors": [{"error": str(e)}],
                            "total_items": len(data_list),
                            "failed_items": len(to_create),
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                else:
                    # Add all create items to errors for partial success
                    for index, item_data in to_create:
                        errors.append(
                            {
                                "index": index,
                                "error": f"Bulk create failed: {str(e)}",
                                "data": item_data,
                            }
                        )

        # Process updates using bulk_update for better performance
        if to_update:
            print(f"DEBUG: Processing {len(to_update)} items to update", file=sys.stderr)
            try:
                # Validate all update data first
                update_objects = []
                update_serializers = []
                update_indices = []

                for index, item_data, existing_instance in to_update:
                    print(f"DEBUG: Validating update data for index {index}: {item_data}", file=sys.stderr)
                    serializer = serializer_class(
                        existing_instance, data=item_data, partial=True
                    )

                    if serializer.is_valid():
                        validated_data = serializer.validated_data
                        print(f"DEBUG: Validated update data for index {index}: {validated_data}", file=sys.stderr)
                        
                        # Debug the business field specifically
                        if 'business' in validated_data:
                            business_obj = validated_data['business']
                            print(f"DEBUG: Business object from serializer: {business_obj}", file=sys.stderr)
                            print(f"DEBUG: Business object type: {type(business_obj)}", file=sys.stderr)
                            print(f"DEBUG: Business object ID: {getattr(business_obj, 'id', 'NO_ID')}", file=sys.stderr)
                            print(f"DEBUG: Business object __dict__: {getattr(business_obj, '__dict__', 'NO_DICT')}", file=sys.stderr)
                            
                            # Check if we can query this business object directly
                            try:
                                from django.db import connection
                                business_model = business_obj._meta.model
                                exists = business_model.objects.filter(id=business_obj.id).exists()
                                print(f"DEBUG: Can query business object directly: {exists}", file=sys.stderr)
                                if exists:
                                    db_obj = business_model.objects.get(id=business_obj.id)
                                    print(f"DEBUG: Database business object: {db_obj}", file=sys.stderr)
                            except Exception as e:
                                print(f"DEBUG: Error querying business object: {e}", file=sys.stderr)

                        # Prepare update data
                        if update_fields:
                            update_data = {
                                k: v
                                for k, v in validated_data.items()
                                if k in update_fields
                            }
                        else:
                            update_data = {
                                k: v
                                for k, v in validated_data.items()
                                if k not in unique_fields
                            }

                        print(f"DEBUG: Update data for index {index}: {update_data}", file=sys.stderr)

                        # Apply updates to the existing instance
                        for field, value in update_data.items():
                            setattr(existing_instance, field, value)
                            print(f"DEBUG: Set {field} = {value} on instance {existing_instance.id}", file=sys.stderr)
                            
                            # Add detailed debugging for foreign key fields
                            if hasattr(existing_instance._meta.get_field(field), 'related_model') and existing_instance._meta.get_field(field).related_model:
                                print(f"DEBUG: Foreign key field '{field}' assigned object: {value}", file=sys.stderr)
                                print(f"DEBUG: Foreign key object ID: {getattr(value, 'id', 'NO_ID')}", file=sys.stderr)
                                print(f"DEBUG: Foreign key object type: {type(value)}", file=sys.stderr)
                                # Check if the object exists in database
                                try:
                                    from django.db import connection
                                    related_model = existing_instance._meta.get_field(field).related_model
                                    exists = related_model.objects.filter(id=value.id).exists()
                                    print(f"DEBUG: Foreign key object exists in DB: {exists}", file=sys.stderr)
                                except Exception as e:
                                    print(f"DEBUG: Error checking foreign key existence: {e}", file=sys.stderr)

                        update_objects.append(existing_instance)
                        update_serializers.append((index, serializer))
                        update_indices.append(index)
                        print(f"DEBUG: Added to update_objects: {existing_instance}", file=sys.stderr)
                    else:
                        # Enhanced error handling for SlugRelatedField issues
                        error_info = {
                            "index": index,
                            "error": str(serializer.errors),
                            "data": item_data,
                        }
                        print(f"DEBUG: Validation failed for update index {index}: {serializer.errors}", file=sys.stderr)

                        # Add debugging information for SlugRelatedField issues
                        if serializer.errors:
                            for field_name, field_errors in serializer.errors.items():
                                if any(
                                    "expected a number but got" in str(error)
                                    for error in field_errors
                                ):
                                    error_info["debug_info"] = {
                                        "field": field_name,
                                        "provided_value": item_data.get(field_name),
                                        "field_type": "SlugRelatedField",
                                        "issue": "SlugRelatedField validation failed - check if slug exists in queryset",
                                    }

                        errors.append(error_info)

                        if not partial_success:
                            return Response(
                                {
                                    "error": "Validation failed during processing",
                                    "errors": [error_info],
                                    "total_items": len(data_list),
                                    "failed_items": 1,
                                },
                                status=status.HTTP_400_BAD_REQUEST,
                            )

                # Use bulk_update for existing records
                if update_objects:
                    print(f"DEBUG: Performing bulk_update with {len(update_objects)} objects", file=sys.stderr)
                    # Determine which fields to update
                    if update_fields:
                        # Convert foreign key field names to use _id suffix for bulk_update
                        fields_to_update = []
                        for field_name in update_fields:
                            field = model_class._meta.get_field(field_name)
                            if hasattr(field, 'related_model') and field.related_model:
                                # Foreign key field - use _id suffix for bulk_update
                                fields_to_update.append(f"{field_name}_id")
                            else:
                                # Regular field
                                fields_to_update.append(field_name)
                    else:
                        # Get all fields that were updated (excluding unique fields)
                        fields_to_update = []
                        for obj in update_objects:
                            for field in obj._meta.fields:
                                if field.name not in unique_fields and hasattr(
                                    obj, field.name
                                ):
                                    if hasattr(field, 'related_model') and field.related_model:
                                        # Foreign key field - use _id suffix for bulk_update
                                        fields_to_update.append(f"{field.name}_id")
                                    else:
                                        # Regular field
                                        fields_to_update.append(field.name)
                        fields_to_update = list(
                            set(fields_to_update)
                        )  # Remove duplicates

                    print(f"DEBUG: Fields to update: {fields_to_update}", file=sys.stderr)

                    # Debug the objects before bulk_update
                    print(f"DEBUG: Objects to update:", file=sys.stderr)
                    for i, obj in enumerate(update_objects):
                        print(f"DEBUG: Object {i}: ID={obj.id}, business_id={getattr(obj, 'business_id', 'NOT_SET')}", file=sys.stderr)
                        if hasattr(obj, 'business') and obj.business:
                            print(f"DEBUG: Object {i}: business object ID={obj.business.id}, business object={obj.business}", file=sys.stderr)

                    # Check if we have foreign key fields to update
                    has_foreign_keys = any('_id' in field for field in fields_to_update)
                    
                    if has_foreign_keys:
                        # For objects with foreign key updates, use individual save() calls
                        print(f"DEBUG: Using individual save() calls due to foreign key fields", file=sys.stderr)
                        for obj in update_objects:
                            obj.save()
                        print(f"DEBUG: Individual saves completed", file=sys.stderr)
                    else:
                        # For regular fields only, use bulk_update
                        print(f"DEBUG: Using bulk_update for regular fields only", file=sys.stderr)
                        model_class.objects.bulk_update(
                            update_objects,
                            fields=fields_to_update,
                            batch_size=1000,  # Adjust batch size as needed
                        )
                        print(f"DEBUG: Bulk update completed", file=sys.stderr)

                    # Collect updated IDs and serialize for response
                    for i, instance in enumerate(update_objects):
                        index, serializer = update_serializers[i]
                        updated_ids.append(instance.id)
                        instances.append(instance)
                        print(f"DEBUG: Updated instance {instance.id} for index {index}", file=sys.stderr)

                        # Serialize for response
                        instance_serializer = serializer_class(instance)
                        success_data.append(instance_serializer.data)

            except Exception as e:
                print(f"DEBUG: Exception during bulk_update: {e}", file=sys.stderr)
                if not partial_success:
                    return Response(
                        {
                            "error": "Bulk update failed",
                            "errors": [{"error": str(e)}],
                            "total_items": len(data_list),
                            "failed_items": len(to_update),
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                else:
                    # Add all update items to errors for partial success
                    for index, item_data, existing_instance in to_update:
                        errors.append(
                            {
                                "index": index,
                                "error": f"Bulk update failed: {str(e)}",
                                "data": item_data,
                            }
                        )

        print(f"DEBUG: Final results - created_ids: {created_ids}, updated_ids: {updated_ids}", file=sys.stderr)
        print(f"DEBUG: Final results - errors: {errors}", file=sys.stderr)
        print(f"DEBUG: Final results - success_data: {len(success_data)} items", file=sys.stderr)

        # Handle response based on mode
        if partial_success:
            # Return partial success response with detailed information
            summary = {
                "total_items": len(data_list),
                "successful_items": len(success_data),
                "failed_items": len(errors),
                "created_count": len(created_ids),
                "updated_count": len(updated_ids),
            }

            return Response(
                {"success": success_data, "errors": errors, "summary": summary},
                status=status.HTTP_207_MULTI_STATUS,
            )
        else:
            # Return standard DRF response for all-or-nothing
            if len(instances) == 1:
                # Single object response (like PATCH /api/model/{id}/)
                return Response(success_data[0], status=status.HTTP_200_OK)
            else:
                # Multiple objects response (like PATCH with array)
                return Response(success_data, status=status.HTTP_200_OK)

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
