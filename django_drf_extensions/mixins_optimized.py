"""
Optimized Operation mixins for DRF ViewSets.

This optimized version fixes the individual database query issue by implementing
bulk lookups for existing records instead of querying one by one.
"""

import sys
from collections import defaultdict
from itertools import groupby

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


class OptimizedOperationsMixin:
    """
    Optimized unified mixin providing intelligent sync/async operation routing.
    
    Key optimizations:
    - Bulk database lookups instead of individual queries
    - Reduced database round trips
    - Improved performance for large datasets
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

    def _build_lookup_key(self, item_data, unique_fields, serializer_fields, model_class):
        """
        Build a lookup key for a record based on unique fields.
        Returns a tuple that can be used as a dictionary key.
        """
        lookup_values = []
        
        for field in unique_fields:
            serializer_field = serializer_fields.get(field)
            
            if serializer_field and isinstance(serializer_field, serializers.SlugRelatedField):
                # For SlugRelatedField, we need to convert the slug to the actual object
                try:
                    related_obj = serializer_field.queryset.get(
                        **{serializer_field.slug_field: item_data[field]}
                    )
                    lookup_values.append(related_obj.id)
                except Exception:
                    # If we can't convert, use the original value
                    lookup_values.append(item_data.get(field))
            else:
                # For regular fields, use the original logic
                if hasattr(model_class, field) and hasattr(getattr(model_class, field), "field"):
                    field_obj = getattr(model_class, field).field
                    if hasattr(field_obj, "related_model") and field_obj.related_model:
                        # This is a foreign key, use _id suffix for lookup
                        lookup_values.append(item_data.get(f"{field}_id", item_data.get(field)))
                    else:
                        lookup_values.append(item_data.get(field))
                else:
                    lookup_values.append(item_data.get(field))
        
        return tuple(lookup_values)

    def _build_bulk_lookup_filter(self, data_list, unique_fields, serializer_fields, model_class):
        """
        Build a bulk lookup filter to find all existing records in one query.
        Returns a Q object that can be used to filter the queryset.
        """
        from django.db.models import Q
        
        # Group records by unique field values to build OR conditions
        lookup_conditions = []
        
        for item_data in data_list:
            # Check if all required unique fields are present
            missing_fields = [field for field in unique_fields if field not in item_data]
            if missing_fields:
                continue  # Skip records with missing unique fields
                
            # Build individual lookup filter
            lookup_filter = {}
            for field in unique_fields:
                serializer_field = serializer_fields.get(field)
                
                if serializer_field and isinstance(serializer_field, serializers.SlugRelatedField):
                    try:
                        related_obj = serializer_field.queryset.get(
                            **{serializer_field.slug_field: item_data[field]}
                        )
                        lookup_filter[f"{field}_id"] = related_obj.id
                    except Exception:
                        lookup_filter[field] = item_data[field]
                else:
                    if hasattr(model_class, field) and hasattr(getattr(model_class, field), "field"):
                        field_obj = getattr(model_class, field).field
                        if hasattr(field_obj, "related_model") and field_obj.related_model:
                            lookup_filter[f"{field}_id"] = item_data.get(f"{field}_id", item_data.get(field))
                        else:
                            lookup_filter[field] = item_data[field]
                    else:
                        lookup_filter[field] = item_data[field]
            
            # Add this condition to the OR list
            if lookup_filter:
                condition = Q(**lookup_filter)
                lookup_conditions.append(condition)
        
        # Combine all conditions with OR
        if lookup_conditions:
            combined_condition = lookup_conditions[0]
            for condition in lookup_conditions[1:]:
                combined_condition |= condition
            return combined_condition
        
        return Q()

    def _perform_optimized_sync_upsert(
        self,
        data_list,
        unique_fields,
        update_fields,
        partial_success=False,
        request=None,
    ):
        """
        Optimized sync upsert operation using bulk lookups instead of individual queries.
        """
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

            except (ValidationError, ValueError) as e:
                validation_error = {"index": index, "error": str(e), "data": item_data}
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

        # Create a temporary serializer to check field types
        temp_serializer = serializer_class()
        serializer_fields = temp_serializer.get_fields()

        # OPTIMIZATION: Bulk lookup all existing records in one query
        bulk_lookup_filter = self._build_bulk_lookup_filter(
            data_list, unique_fields, serializer_fields, model_class
        )
        
        # Get all existing records that match any of our unique field combinations
        existing_records = {}
        if bulk_lookup_filter:
            existing_instances = self.get_queryset().filter(bulk_lookup_filter)
            
            # Create a lookup dictionary for fast access
            for instance in existing_instances:
                lookup_key = self._build_lookup_key(
                    {field: getattr(instance, field) for field in unique_fields},
                    unique_fields, serializer_fields, model_class
                )
                existing_records[lookup_key] = instance

        # Second pass: separate creates and updates using the bulk lookup results
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

                # Build lookup key for this record
                lookup_key = self._build_lookup_key(
                    item_data, unique_fields, serializer_fields, model_class
                )
                
                # Check if record exists using the bulk lookup results
                existing_instance = existing_records.get(lookup_key)

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
                        batch_size=1000,
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
                        error_info = {
                            "index": index,
                            "error": str(serializer.errors),
                            "data": item_data,
                        }
                        errors.append(error_info)

                        if not partial_success:
                            return Response(
                                {
                                    "error": "Update validation failed",
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
                        fields_to_update = update_fields
                    else:
                        # Auto-infer update fields
                        fields_to_update = self._infer_update_fields(data_list, unique_fields)

                    model_class.objects.bulk_update(
                        update_objects,
                        fields=fields_to_update,
                        batch_size=1000,
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

        # Prepare response
        if errors and not partial_success:
            return Response(
                {
                    "error": "Operation failed",
                    "errors": errors,
                    "total_items": len(data_list),
                    "failed_items": len(errors),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Success response
        response_data = {
            "message": "Upsert completed successfully",
            "total_items": len(data_list),
            "created_count": len(created_ids),
            "updated_count": len(updated_ids),
            "created_ids": created_ids,
            "updated_ids": updated_ids,
            "is_sync": True,
        }

        if partial_success and errors:
            response_data.update({
                "success": success_data,
                "errors": errors,
                "summary": {
                    "total": len(data_list),
                    "successful": len(success_data),
                    "failed": len(errors),
                }
            })
            return Response(response_data, status=status.HTTP_207_MULTI_STATUS)
        else:
            response_data["results"] = success_data
            return Response(response_data, status=status.HTTP_200_OK)

    def _infer_update_fields(self, data_list, unique_fields):
        """Infer which fields should be updated based on the data."""
        if not data_list:
            return []
        
        # Get all fields from the first record that are not unique fields
        all_fields = set()
        for item_data in data_list:
            all_fields.update(item_data.keys())
        
        # Remove unique fields from the update fields
        update_fields = list(all_fields - set(unique_fields))
        return update_fields

    # Include all the other methods from the original OperationsMixin
    # (list, create, update, partial_update, patch, put, bulk_* methods, etc.)
    # For brevity, I'm not including them all here, but they would be copied
    # from the original mixins.py file
