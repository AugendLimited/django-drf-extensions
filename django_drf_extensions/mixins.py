"""
Operation mixins for DRF ViewSets.

Provides a unified mixin that enhances standard ViewSet endpoints with intelligent
sync/async routing and adds /bulk/ endpoints for background processing.
"""

import sys

# Test logging immediately
print("DEBUG: django_drf_extensions.mixins module loaded", file=sys.stderr)
print("INFO: django_drf_extensions.mixins module loaded", file=sys.stderr)
print("WARNING: django_drf_extensions.mixins module loaded", file=sys.stderr)

from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework import status
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
        print("DEBUG: OperationsMixin __init__ called", file=sys.stderr)
        super().__init__(*args, **kwargs)

    def get_serializer(self, *args, **kwargs):
        """Handle array data for serializers."""
        try:
            print(f"DEBUG: get_serializer called with args: {args}", file=sys.stderr)
            print(
                f"DEBUG: get_serializer called with kwargs: {kwargs}", file=sys.stderr
            )

            data = kwargs.get("data", None)
            if data is not None and isinstance(data, list):
                print(f"DEBUG: Setting many=True for list data", file=sys.stderr)
                kwargs["many"] = True

            print(f"DEBUG: Calling super().get_serializer", file=sys.stderr)
            return super().get_serializer(*args, **kwargs)
        except Exception as e:
            print(f"DEBUG: Exception in get_serializer: {str(e)}", file=sys.stderr)
            print(f"DEBUG: Exception type: {type(e)}", file=sys.stderr)
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
            print("DEBUG: partial_update method called", file=sys.stderr)
            print(f"DEBUG: Request data type: {type(request.data)}", file=sys.stderr)
            print(f"DEBUG: Request data: {request.data}", file=sys.stderr)
            print(f"DEBUG: Query params: {request.query_params}", file=sys.stderr)

            unique_fields_param = request.query_params.get("unique_fields")
            print(f"DEBUG: unique_fields_param: {unique_fields_param}", file=sys.stderr)

            if unique_fields_param and isinstance(request.data, list):
                print(f"DEBUG: Calling _sync_upsert", file=sys.stderr)
                return self._sync_upsert(request, unique_fields_param)

            print(f"DEBUG: Calling standard partial_update", file=sys.stderr)
            # Standard single partial update behavior
            return super().partial_update(request, *args, **kwargs)
        except Exception as e:
            print(f"DEBUG: Exception in partial_update: {str(e)}", file=sys.stderr)
            print(f"DEBUG: Exception type: {type(e)}", file=sys.stderr)
            import traceback

            print(f"DEBUG: Traceback: {traceback.format_exc()}", file=sys.stderr)
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
        unique_fields_param = request.query_params.get("unique_fields")
        if unique_fields_param and isinstance(request.data, list):
            return self._sync_upsert(request, unique_fields_param)

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
        print(
            f"DEBUG: Starting _sync_upsert with unique_fields_param: {unique_fields_param}",
            file=sys.stderr,
        )

        # Parse parameters
        unique_fields = [f.strip() for f in unique_fields_param.split(",") if f.strip()]
        print(f"DEBUG: Parsed unique_fields: {unique_fields}", file=sys.stderr)
        update_fields_param = request.query_params.get("update_fields")
        update_fields = None
        if update_fields_param:
            update_fields = [
                f.strip() for f in update_fields_param.split(",") if f.strip()
            ]

        # Check if partial success is enabled
        partial_success = (
            request.query_params.get("partial_success", "false").lower() == "true"
        )

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
                    "suggestion": "Use PATCH /bulk/?unique_fields=... for async processing",
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

        print(f"DEBUG: About to call _perform_sync_upsert", file=sys.stderr)
        # Perform sync upsert
        try:
            result = self._perform_sync_upsert(
                data_list, unique_fields, update_fields, partial_success, request
            )
            return result
        except Exception as e:
            print(f"DEBUG: Exception in _sync_upsert: {str(e)}", file=sys.stderr)
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
        """Perform the actual sync upsert operation using Django's update_or_create."""
        from django.db import transaction
        from rest_framework import status

        print(
            f"DEBUG: Starting _perform_sync_upsert with {len(data_list)} items",
            file=sys.stderr,
        )
        print(f"DEBUG: Unique fields: {unique_fields}", file=sys.stderr)
        print(
            f"DEBUG: First item data: {data_list[0] if data_list else 'No data'}",
            file=sys.stderr,
        )

        serializer_class = self.get_serializer_class()
        model_class = serializer_class.Meta.model

        created_ids = []
        updated_ids = []
        errors = []
        instances = []
        success_data = []

        # First pass: check for missing unique fields only
        validation_errors = []
        print(f"DEBUG: Starting first validation pass", file=sys.stderr)
        for index, item_data in enumerate(data_list):
            print(f"DEBUG: Processing item {index}: {item_data}", file=sys.stderr)
            try:
                # Check if this is a create or update scenario
                unique_filter = {}
                missing_fields = []
                for field in unique_fields:
                    if field in item_data:
                        unique_filter[field] = item_data[field]
                    else:
                        missing_fields.append(field)

                if missing_fields:
                    validation_error = {
                        "index": index,
                        "error": f"Missing required unique fields: {missing_fields}",
                        "data": item_data,
                    }
                    validation_errors.append(validation_error)
                    continue

                # Skip full validation here - will validate during actual operation
                # This prevents SlugRelatedField validation issues during initial check

            except (ValidationError, ValueError) as e:
                print(
                    f"DEBUG: Caught exception for item {index}: {str(e)}",
                    file=sys.stderr,
                )
                validation_error = {"index": index, "error": str(e), "data": item_data}

                # Add debugging info for SlugRelatedField issues
                if "expected a number but got" in str(e):
                    print(f"DEBUG: This is a SlugRelatedField error!", file=sys.stderr)
                    validation_error["debug_info"] = {
                        "error_type": "SlugRelatedField_validation",
                        "issue": "SlugRelatedField failed to convert slug to object",
                        "suggestion": "Check if the slug values exist in the related queryset",
                    }

                validation_errors.append(validation_error)

        # If not allowing partial success and there are validation errors, fail immediately
        if not partial_success and validation_errors:
            print(f"DEBUG: Validation errors found, returning 400", file=sys.stderr)
            return Response(
                {
                    "error": "Validation failed for one or more records",
                    "errors": validation_errors,
                    "total_items": len(data_list),
                    "failed_items": len(validation_errors),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        print(
            f"DEBUG: Starting second pass - processing {len(data_list)} items",
            file=sys.stderr,
        )
        # Second pass: process items (with partial success if enabled)
        for index, item_data in enumerate(data_list):
            print(f"DEBUG: Second pass - processing item {index}", file=sys.stderr)
            try:
                # Check if this item already failed validation
                failed_validation = any(
                    error["index"] == index for error in validation_errors
                )
                if failed_validation:
                    print(
                        f"DEBUG: Item {index} failed validation, skipping",
                        file=sys.stderr,
                    )
                    if partial_success:
                        error_to_add = next(
                            error
                            for error in validation_errors
                            if error["index"] == index
                        )
                        errors.append(error_to_add)
                    continue

                print(
                    f"DEBUG: Building lookup filter for item {index}", file=sys.stderr
                )
                # Check if this is a create or update scenario
                unique_filter = {}
                lookup_filter = {}
                
                # Create a temporary serializer to check field types
                temp_serializer = serializer_class()
                serializer_fields = temp_serializer.get_fields()
                
                for field in unique_fields:
                    unique_filter[field] = item_data[field]
                    
                    # Check if this field is a SlugRelatedField in the serializer
                    serializer_field = serializer_fields.get(field)
                    if serializer_field and isinstance(serializer_field, serializers.SlugRelatedField):
                        # For SlugRelatedField, we need to convert the slug to the actual object
                        # and then use the object's ID for the lookup
                        print(f"DEBUG: Field '{field}' is a SlugRelatedField", file=sys.stderr)
                        try:
                            # Get the related object using the slug
                            related_obj = serializer_field.queryset.get(**{serializer_field.slug_field: item_data[field]})
                            lookup_filter[f"{field}_id"] = related_obj.id
                            print(f"DEBUG: Converted '{field}' slug '{item_data[field]}' to ID {related_obj.id}", file=sys.stderr)
                        except Exception as e:
                            print(f"DEBUG: Failed to convert '{field}' slug '{item_data[field]}' to object: {e}", file=sys.stderr)
                            # If we can't convert, skip this field for now
                            continue
                    else:
                        # For regular fields, use the original logic
                        if hasattr(model_class, field) and hasattr(
                            getattr(model_class, field), "field"
                        ):
                            field_obj = getattr(model_class, field).field
                            if (
                                hasattr(field_obj, "related_model")
                                and field_obj.related_model
                            ):
                                # This is a foreign key, use _id suffix for lookup
                                lookup_filter[f"{field}_id"] = item_data[field]
                            else:
                                lookup_filter[field] = item_data[field]
                        else:
                            lookup_filter[field] = item_data[field]

                print(
                    f"DEBUG: Lookup filter for item {index}: {lookup_filter}",
                    file=sys.stderr,
                )
                # Check if record exists using raw data first
                print(
                    f"DEBUG: About to query database for existing instance",
                    file=sys.stderr,
                )
                existing_instance = self.get_queryset().filter(**lookup_filter).first()
                print(
                    f"DEBUG: Database query completed, existing_instance: {existing_instance}",
                    file=sys.stderr,
                )

                if existing_instance:
                    # Update existing record - validate with instance context
                    print(
                        f"DEBUG: Creating serializer for UPDATE with instance {existing_instance.id}",
                        file=sys.stderr,
                    )
                    serializer = serializer_class(
                        existing_instance, data=item_data, partial=True
                    )
                else:
                    # Create new record - validate normally
                    print(f"DEBUG: Creating serializer for CREATE", file=sys.stderr)
                    serializer = serializer_class(data=item_data)

                print(
                    f"DEBUG: About to validate serializer for index {index}",
                    file=sys.stderr,
                )
                # Add debugging for SlugRelatedField issues
                if not serializer.is_valid():
                    print(
                        f"DEBUG: Serializer validation failed for index {index}",
                        file=sys.stderr,
                    )
                    print(f"DEBUG: Errors: {serializer.errors}", file=sys.stderr)
                    # Check if this is a SlugRelatedField error
                    for field_name, field_errors in serializer.errors.items():
                        if any(
                            "expected a number but got" in str(error)
                            for error in field_errors
                        ):
                            # This is a SlugRelatedField issue - add debugging info
                            print(
                                f"DEBUG: SlugRelatedField error for field '{field_name}'",
                                file=sys.stderr,
                            )
                            print(
                                f"DEBUG: Provided value: {item_data.get(field_name)}",
                                file=sys.stderr,
                            )
                            print(
                                f"DEBUG: Serializer context: {getattr(serializer, 'context', 'No context')}",
                                file=sys.stderr,
                            )
                            print(
                                f"DEBUG: Serializer instance: {getattr(serializer, 'instance', 'No instance')}",
                                file=sys.stderr,
                            )

                print(f"DEBUG: About to check if serializer is valid", file=sys.stderr)
                if serializer.is_valid():
                    print(
                        f"DEBUG: Serializer is valid, getting validated_data",
                        file=sys.stderr,
                    )
                    validated_data = serializer.validated_data

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

                    # Use Django's update_or_create for atomic upsert
                    # For SlugRelatedField, we need to use the validated data for the lookup
                    final_lookup_filter = {}
                    for field in unique_fields:
                        if field in validated_data:
                            field_value = validated_data[field]
                            # Handle foreign key fields and SlugRelatedField instances
                            if hasattr(field_value, "id"):
                                # This is an object instance (from SlugRelatedField or ForeignKey)
                                final_lookup_filter[f"{field}_id"] = field_value.id
                            elif hasattr(model_class, field) and hasattr(
                                getattr(model_class, field), "field"
                            ):
                                field_obj = getattr(model_class, field).field
                                if (
                                    hasattr(field_obj, "related_model")
                                    and field_obj.related_model
                                ):
                                    # This is a foreign key, use _id suffix for lookup
                                    final_lookup_filter[f"{field}_id"] = field_value
                                else:
                                    final_lookup_filter[field] = field_value
                            else:
                                final_lookup_filter[field] = field_value

                    instance, created = self.get_queryset().update_or_create(
                        defaults=update_data, **final_lookup_filter
                    )

                    if created:
                        created_ids.append(instance.id)
                    else:
                        updated_ids.append(instance.id)

                    # Add instance to results
                    instances.append(instance)

                    # Serialize for response
                    instance_serializer = serializer_class(instance)
                    success_data.append(instance_serializer.data)
                else:
                    # Enhanced error handling for SlugRelatedField issues
                    error_info = {
                        "index": index,
                        "error": str(serializer.errors),
                        "data": item_data,
                    }

                    # Add debugging information for SlugRelatedField issues (without changing core logic)
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
                        # Rollback any successful operations
                        return Response(
                            {
                                "error": "Validation failed during processing",
                                "errors": [error_info],
                                "total_items": len(data_list),
                                "failed_items": 1,
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )

            except (ValidationError, ValueError) as e:
                error_info = {"index": index, "error": str(e), "data": item_data}
                errors.append(error_info)

                if not partial_success:
                    # Rollback any successful operations
                    return Response(
                        {
                            "error": "Processing failed",
                            "errors": [error_info],
                            "total_items": len(data_list),
                            "failed_items": 1,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

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
