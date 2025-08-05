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


# Import enhanced functionality for bulk operations
from django_drf_extensions.enhanced_processing import (
    enhanced_create_task,
    enhanced_delete_task,
    enhanced_upsert_task,
    run_aggregates_task,
)
from django_drf_extensions.event_notifications import (
    ServerSentEventsView,
    WebhookRegistrationView,
)
from django_drf_extensions.job_state import JobStateManager, JobType

# Keep legacy imports for backward compatibility
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
        # Parse parameters
        unique_fields = [f.strip() for f in unique_fields_param.split(",") if f.strip()]

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

        # Perform sync upsert
        try:
            result = self._perform_sync_upsert(
                data_list, unique_fields, update_fields, partial_success, request
            )
            return result
        except Exception as e:
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

        serializer_class = self.get_serializer_class()
        model_class = serializer_class.Meta.model

        created_ids = []
        updated_ids = []
        errors = []
        instances = []
        success_data = []

        # First pass: check for missing unique fields only
        validation_errors = []
        for index, item_data in enumerate(data_list):
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
                validation_error = {"index": index, "error": str(e), "data": item_data}

                # Add debugging info for SlugRelatedField issues
                if "expected a number but got" in str(e):
                    validation_error["debug_info"] = {
                        "error_type": "SlugRelatedField_validation",
                        "issue": "SlugRelatedField failed to convert slug to object",
                        "suggestion": "Check if the slug values exist in the related queryset",
                    }

                validation_errors.append(validation_error)

        # If not allowing partial success and there are validation errors, fail immediately
        if not partial_success and validation_errors:
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
            try:
                # Check if this item already failed validation
                failed_validation = any(
                    error["index"] == index for error in validation_errors
                )
                if failed_validation:
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

                for field in unique_fields:
                    # Check if this field is a SlugRelatedField in the serializer
                    serializer_field = serializer_fields.get(field)

                    if serializer_field and isinstance(
                        serializer_field, serializers.SlugRelatedField
                    ):
                        # For SlugRelatedField, we need to convert the slug to the actual object
                        # and then use the object's ID for the lookup
                        try:
                            # Get the related object using the slug
                            related_obj = serializer_field.queryset.get(
                                **{serializer_field.slug_field: item_data[field]}
                            )
                            lookup_filter[f"{field}_id"] = related_obj.id
                        except Exception as e:
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

                # Check if record exists using raw data first
                existing_instance = self.get_queryset().filter(**lookup_filter).first()

                if existing_instance:
                    # Update existing record
                    to_update.append((index, item_data, existing_instance))
                    update_indices.append(index)
                else:
                    # Create new record
                    to_create.append((index, item_data))
                    create_indices.append(index)

            except (ValidationError, ValueError) as e:
                error_info = {"index": index, "error": str(e), "data": item_data}
                errors.append(error_info)

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

        # Process creates using bulk_create
        if to_create:
            try:
                # Validate all create data first
                create_objects = []
                create_serializers = []

                for index, item_data in to_create:
                    serializer = serializer_class(data=item_data)
                    if serializer.is_valid():
                        validated_data = serializer.validated_data
                        # Create model instance without saving
                        instance = model_class(**validated_data)
                        create_objects.append(instance)
                        create_serializers.append((index, serializer))
                    else:
                        error_info = {
                            "index": index,
                            "error": str(serializer.errors),
                            "data": item_data,
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

                # Use bulk_create for new records
                if create_objects:
                    created_instances = model_class.objects.bulk_create(
                        create_objects,
                        batch_size=1000,  # Adjust batch size as needed
                        ignore_conflicts=False,
                    )

                    # Collect created IDs and serialize for response
                    for i, instance in enumerate(created_instances):
                        index, serializer = create_serializers[i]
                        created_ids.append(instance.id)
                        instances.append(instance)

                        # Serialize for response
                        instance_serializer = serializer_class(instance)
                        success_data.append(instance_serializer.data)

            except Exception as e:
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
            try:
                # Validate all update data first
                update_objects = []
                update_serializers = []
                update_indices = []

                for index, item_data, existing_instance in to_update:
                    serializer = serializer_class(
                        existing_instance, data=item_data, partial=True
                    )

                    if serializer.is_valid():
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

                        # Apply updates to the existing instance
                        for field, value in update_data.items():
                            setattr(existing_instance, field, value)

                        update_objects.append(existing_instance)
                        update_serializers.append((index, serializer))
                        update_indices.append(index)
                    else:
                        # Enhanced error handling for SlugRelatedField issues
                        error_info = {
                            "index": index,
                            "error": str(serializer.errors),
                            "data": item_data,
                        }

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
                    # Determine which fields to update
                    if update_fields:
                        # Convert foreign key field names to use _id suffix for bulk_update
                        fields_to_update = []
                        for field_name in update_fields:
                            field = model_class._meta.get_field(field_name)
                            if hasattr(field, "related_model") and field.related_model:
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
                                    if (
                                        hasattr(field, "related_model")
                                        and field.related_model
                                    ):
                                        # Foreign key field - use _id suffix for bulk_update
                                        fields_to_update.append(f"{field.name}_id")
                                    else:
                                        # Regular field
                                        fields_to_update.append(field.name)
                        fields_to_update = list(
                            set(fields_to_update)
                        )  # Remove duplicates

                    # Check if we have foreign key fields to update
                    has_foreign_keys = any("_id" in field for field in fields_to_update)

                    if has_foreign_keys:
                        # For objects with foreign key updates, use individual save() calls
                        for obj in update_objects:
                            obj.save()
                    else:
                        # For regular fields only, use bulk_update
                        model_class.objects.bulk_update(
                            update_objects,
                            fields=fields_to_update,
                            batch_size=1000,  # Adjust batch size as needed
                        )

                    # Collect updated IDs and serialize for response
                    for i, instance in enumerate(update_objects):
                        index, serializer = update_serializers[i]
                        updated_ids.append(instance.id)
                        instances.append(instance)

                        # Serialize for response
                        instance_serializer = serializer_class(instance)
                        success_data.append(instance_serializer.data)

            except Exception as e:
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
        description="Create multiple instances asynchronously via background processing with job state tracking.",
        summary="Enhanced async bulk create",
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

        # Create job
        serializer_class = self.get_serializer_class()
        serializer_class_path = (
            f"{serializer_class.__module__}.{serializer_class.__name__}"
        )
        model_class = self.get_queryset().model
        model_class_path = f"{model_class.__module__}.{model_class.__name__}"
        user_id = request.user.id if request.user.is_authenticated else None

        job = JobStateManager.create_job(
            job_type=JobType.INSERT,
            model_class_path=model_class_path,
            serializer_class_path=serializer_class_path,
            user_id=user_id,
            total_items=len(data_list),
        )

        # Start async task
        task = enhanced_create_task.delay(
            job.job_id, serializer_class_path, data_list, user_id
        )

        return Response(
            {
                "message": f"Enhanced bulk create job started for {len(data_list)} items",
                "job_id": job.job_id,
                "task_id": task.id,
                "total_items": len(data_list),
                "status_url": f"/api/jobs/{job.job_id}/status/",
                "aggregates_url": f"/api/jobs/{job.job_id}/aggregates/",
                "estimated_duration": f"{max(1, len(data_list) // 1000)}-{max(2, len(data_list) // 500)} minutes",
                "next_steps": [
                    "Poll status_url every 10 seconds for progress updates",
                    "Check aggregates_url when status shows 'Job Complete'",
                    "Review any errors in the status response",
                ],
                "tips": [
                    "Large batches (>10k items) may take several minutes",
                    "You can safely poll status_url frequently",
                    "Aggregates are automatically calculated when job completes",
                ],
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
        description="Update multiple instances asynchronously with job state tracking. Supports both standard update (with id fields) and upsert mode (with unique_fields parameter).",
        summary="Enhanced async bulk update/upsert",
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

        # Create job for bulk update
        serializer_class = self.get_serializer_class()
        serializer_class_path = (
            f"{serializer_class.__module__}.{serializer_class.__name__}"
        )
        model_class = self.get_queryset().model
        model_class_path = f"{model_class.__module__}.{model_class.__name__}"
        user_id = request.user.id if request.user.is_authenticated else None

        job = JobStateManager.create_job(
            job_type=JobType.UPDATE,
            model_class_path=model_class_path,
            serializer_class_path=serializer_class_path,
            user_id=user_id,
            total_items=len(data_list),
        )

        # Start async task
        task = enhanced_upsert_task.delay(
            job.job_id, serializer_class_path, data_list, None, None, user_id
        )

        return Response(
            {
                "message": f"Enhanced bulk update job started for {len(data_list)} items",
                "job_id": job.job_id,
                "task_id": task.id,
                "total_items": len(data_list),
                "status_url": f"/api/jobs/{job.job_id}/status/",
                "aggregates_url": f"/api/jobs/{job.job_id}/aggregates/",
                "estimated_duration": f"{max(1, len(data_list) // 1000)}-{max(2, len(data_list) // 500)} minutes",
                "next_steps": [
                    "Poll status_url every 10 seconds for progress updates",
                    "Check aggregates_url when status shows 'Job Complete'",
                    "Review any errors in the status response",
                ],
                "tips": [
                    "Large batches (>10k items) may take several minutes",
                    "You can safely poll status_url frequently",
                    "Aggregates are automatically calculated when job completes",
                ],
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
        description="Replace multiple instances asynchronously with job state tracking. Supports both standard replace (with id fields) and upsert mode (with unique_fields parameter).",
        summary="Enhanced async bulk replace/upsert",
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

        # Create job for bulk replace
        serializer_class = self.get_serializer_class()
        serializer_class_path = (
            f"{serializer_class.__module__}.{serializer_class.__name__}"
        )
        model_class = self.get_queryset().model
        model_class_path = f"{model_class.__module__}.{model_class.__name__}"
        user_id = request.user.id if request.user.is_authenticated else None

        job = JobStateManager.create_job(
            job_type=JobType.REPLACE,
            model_class_path=model_class_path,
            serializer_class_path=serializer_class_path,
            user_id=user_id,
            total_items=len(data_list),
        )

        # Start async task
        task = enhanced_upsert_task.delay(
            job.job_id, serializer_class_path, data_list, None, None, user_id
        )

        return Response(
            {
                "message": f"Enhanced bulk replace job started for {len(data_list)} items",
                "job_id": job.job_id,
                "task_id": task.id,
                "total_items": len(data_list),
                "status_url": f"/api/jobs/{job.job_id}/status/",
                "aggregates_url": f"/api/jobs/{job.job_id}/aggregates/",
                "estimated_duration": f"{max(1, len(data_list) // 1000)}-{max(2, len(data_list) // 500)} minutes",
                "next_steps": [
                    "Poll status_url every 10 seconds for progress updates",
                    "Check aggregates_url when status shows 'Job Complete'",
                    "Review any errors in the status response",
                ],
                "tips": [
                    "Large batches (>10k items) may take several minutes",
                    "You can safely poll status_url frequently",
                    "Aggregates are automatically calculated when job completes",
                ],
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
        description="Delete multiple instances asynchronously via background processing with job state tracking.",
        summary="Enhanced async bulk delete",
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

        # Create job for bulk delete
        model_class = self.get_queryset().model
        model_class_path = f"{model_class.__module__}.{model_class.__name__}"
        user_id = request.user.id if request.user.is_authenticated else None

        job = JobStateManager.create_job(
            job_type=JobType.DELETE,
            model_class_path=model_class_path,
            serializer_class_path=None,  # Not needed for delete
            user_id=user_id,
            total_items=len(ids_list),
        )

        # Start async task
        task = enhanced_delete_task.delay(
            job.job_id, model_class_path, ids_list, user_id
        )

        return Response(
            {
                "message": f"Enhanced bulk delete job started for {len(ids_list)} items",
                "job_id": job.job_id,
                "task_id": task.id,
                "total_items": len(ids_list),
                "status_url": f"/api/jobs/{job.job_id}/status/",
                "aggregates_url": f"/api/jobs/{job.job_id}/aggregates/",
                "estimated_duration": f"{max(1, len(ids_list) // 1000)}-{max(2, len(ids_list) // 500)} minutes",
                "next_steps": [
                    "Poll status_url every 10 seconds for progress updates",
                    "Check aggregates_url when status shows 'Job Complete'",
                    "Review any errors in the status response",
                ],
                "tips": [
                    "Large batches (>10k items) may take several minutes",
                    "You can safely poll status_url frequently",
                    "Aggregates are automatically calculated when job completes",
                ],
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

        # Create job for bulk upsert
        serializer_class = self.get_serializer_class()
        serializer_class_path = (
            f"{serializer_class.__module__}.{serializer_class.__name__}"
        )
        model_class = self.get_queryset().model
        model_class_path = f"{model_class.__module__}.{model_class.__name__}"
        user_id = request.user.id if request.user.is_authenticated else None

        job = JobStateManager.create_job(
            job_type=JobType.UPSERT,
            model_class_path=model_class_path,
            serializer_class_path=serializer_class_path,
            user_id=user_id,
            total_items=len(data_list),
            unique_fields=unique_fields,
            update_fields=update_fields,
        )

        # Start async task
        task = enhanced_upsert_task.delay(
            job.job_id,
            serializer_class_path,
            data_list,
            unique_fields,
            update_fields,
            user_id,
        )

        return Response(
            {
                "message": f"Enhanced bulk upsert job started for {len(data_list)} items",
                "job_id": job.job_id,
                "task_id": task.id,
                "total_items": len(data_list),
                "unique_fields": unique_fields,
                "update_fields": update_fields,
                "status_url": f"/api/jobs/{job.job_id}/status/",
                "aggregates_url": f"/api/jobs/{job.job_id}/aggregates/",
                "estimated_duration": f"{max(1, len(data_list) // 1000)}-{max(2, len(data_list) // 500)} minutes",
                "next_steps": [
                    "Poll status_url every 10 seconds for progress updates",
                    "Check aggregates_url when status shows 'Job Complete'",
                    "Review any errors in the status response",
                ],
                "tips": [
                    "Large batches (>10k items) may take several minutes",
                    "You can safely poll status_url frequently",
                    "Aggregates are automatically calculated when job completes",
                ],
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=False, methods=["get"], url_path="jobs/(?P<job_id>[^/.]+)/status")
    def get_job_status(self, request, job_id):
        """Get the status of a bulk job."""
        try:
            job_summary = JobStateManager.get_job_summary(job_id)
            return Response(job_summary, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {"error": f"Failed to get job status: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(
        detail=False, methods=["get"], url_path="jobs/(?P<job_id>[^/.]+)/aggregates"
    )
    def get_job_aggregates(self, request, job_id):
        """Get aggregate results for a completed bulk job."""
        try:
            job = JobStateManager.get_job(job_id)
            if not job:
                return Response(
                    {"error": "Job not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if not job.aggregates_completed:
                return Response(
                    {"error": "Aggregates not yet completed for this job"},
                    status=status.HTTP_202_ACCEPTED,
                )

            return Response(
                {
                    "job_id": job_id,
                    "aggregate_results": job.aggregate_results,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {"error": f"Failed to get job aggregates: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=False, methods=["post"], url_path="jobs/aggregates")
    def run_job_aggregates(self, request):
        """Run aggregates on a completed bulk job."""
        job_id = request.data.get("job_id")
        aggregate_config = request.data.get("aggregate_config", {})

        if not job_id:
            return Response(
                {"error": "job_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            job = JobStateManager.get_job(job_id)
            if not job:
                return Response(
                    {"error": "Job not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if not job.aggregates_ready:
                return Response(
                    {"error": "Job is not ready for aggregates yet"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Start aggregate task
            task = run_aggregates_task.delay(job_id, aggregate_config)

            return Response(
                {
                    "message": "Aggregate task started",
                    "job_id": job_id,
                    "task_id": task.id,
                },
                status=status.HTTP_202_ACCEPTED,
            )
        except Exception as e:
            return Response(
                {"error": f"Failed to start aggregate task: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    # =============================================================================
    # Event Notification Endpoints (Alternatives to Polling)
    # =============================================================================

    @action(detail=False, methods=["get"], url_path="jobs/(?P<job_id>[^/.]+)/events")
    def get_job_events_sse(self, request, job_id):
        """
        Server-Sent Events endpoint for real-time job status updates.

        GET /api/jobs/{job_id}/events/
        Accept: text/event-stream

        Usage:
            const eventSource = new EventSource('/api/jobs/abc123/events/');
            eventSource.onmessage = (event) => {
                console.log('Job update:', JSON.parse(event.data));
            };
        """
        return ServerSentEventsView.as_view()(request, job_id=job_id)

    @action(detail=False, methods=["post"], url_path="jobs/webhooks/register")
    def register_webhook(self, request):
        """
        Register a webhook for job notifications.

        POST /api/jobs/webhooks/register/

        Request body:
        {
            "webhook_url": "https://your-app.com/webhooks/job-updates",
            "event_types": ["job_completed", "job_failed"],
            "headers": {"Authorization": "Bearer token"}
        }
        """
        return WebhookRegistrationView.as_view()(request)

    @action(detail=False, methods=["get"], url_path="jobs/webhooks/list")
    def list_webhooks(self, request):
        """
        List registered webhooks.

        GET /api/jobs/webhooks/list/
        """
        return WebhookRegistrationView.as_view()(request)

    @extend_schema(
        summary="Process transactions with full pipeline",
        description="Import transactions, aggregate, run credit model, and return offers in a single operation",
        request=serializers.ListField(
            child=serializers.DictField(),
            help_text="List of transaction data to process",
        ),
        responses={
            202: serializers.DictField(
                fields={
                    "job_id": serializers.CharField(help_text="Unique job identifier"),
                    "status_url": serializers.CharField(
                        help_text="URL to check job status"
                    ),
                    "offers_url": serializers.CharField(
                        help_text="URL to retrieve offers when complete"
                    ),
                    "estimated_duration": serializers.CharField(
                        help_text="Estimated time to completion"
                    ),
                    "next_steps": serializers.CharField(help_text="What happens next"),
                    "tips": serializers.CharField(help_text="Usage tips"),
                }
            )
        },
    )
    @action(detail=False, methods=["post"], url_path="process-transactions")
    def process_transactions_pipeline(self, request):
        """
        Single endpoint to process transactions through the complete pipeline:
        1. Import transactions
        2. Aggregate data
        3. Run credit model
        4. Generate offers
        """
        data = request.data.get("data", [])
        credit_model_config = request.data.get("credit_model_config", {})
        aggregate_config = request.data.get("aggregate_config", {})

        if not data:
            return Response(
                {"error": "No transaction data provided"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create pipeline job
        job_id = JobStateManager.create_job(
            job_type=JobType.PIPELINE,
            description=f"Process {len(data)} transactions through complete pipeline",
            metadata={
                "transaction_count": len(data),
                "credit_model_config": credit_model_config,
                "aggregate_config": aggregate_config,
                "pipeline_steps": ["import", "aggregate", "credit_model", "offers"],
            },
        )

        # Start the pipeline task
        from .enhanced_processing import process_transactions_pipeline_task

        process_transactions_pipeline_task.delay(
            job_id=job_id,
            transaction_data=data,
            credit_model_config=credit_model_config,
            aggregate_config=aggregate_config,
        )

        return Response(
            {
                "job_id": job_id,
                "status_url": f"/api/jobs/{job_id}/status/",
                "offers_url": f"/api/jobs/{job_id}/offers/",
                "estimated_duration": "5-10 minutes",
                "next_steps": "Monitor job status. Offers will be available when pipeline completes.",
                "tips": "Use the offers_url endpoint to retrieve results when job is complete",
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @extend_schema(
        summary="Get pipeline offers",
        description="Retrieve offers generated by the transaction processing pipeline",
        responses={
            200: serializers.DictField(
                fields={
                    "offers": serializers.ListField(
                        child=serializers.DictField(), help_text="Generated offers"
                    ),
                    "pipeline_summary": serializers.DictField(
                        help_text="Summary of pipeline execution"
                    ),
                    "credit_model_results": serializers.DictField(
                        help_text="Results from credit model processing"
                    ),
                }
            ),
            404: serializers.DictField(
                fields={
                    "error": serializers.CharField(help_text="Error message"),
                    "job_status": serializers.CharField(help_text="Current job status"),
                }
            ),
        },
    )
    @action(detail=False, methods=["get"], url_path="jobs/(?P<job_id>[^/.]+)/offers")
    def get_pipeline_offers(self, request, job_id=None):
        """Retrieve offers from a completed pipeline job"""
        try:
            job = JobStateManager.get_job(job_id)

            if job.state != JobState.JOB_COMPLETE:
                return Response(
                    {"error": "Pipeline not complete", "job_status": job.state.value},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Retrieve offers from job metadata
            offers = job.metadata.get("offers", [])
            pipeline_summary = job.metadata.get("pipeline_summary", {})
            credit_model_results = job.metadata.get("credit_model_results", {})

            return Response(
                {
                    "offers": offers,
                    "pipeline_summary": pipeline_summary,
                    "credit_model_results": credit_model_results,
                }
            )

        except Exception as e:
            return Response(
                {"error": f"Failed to retrieve offers: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# Legacy alias for backwards compatibility during migration
AsyncOperationsMixin = OperationsMixin
SyncUpsertMixin = OperationsMixin
