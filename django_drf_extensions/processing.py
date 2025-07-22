"""
Common async processing utilities for handling array operations with Celery.
"""
import logging
from typing import Any

from celery import shared_task
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.module_loading import import_string

from django_drf_extensions.cache import OperationCache

logger = logging.getLogger(__name__)


class OperationResult:
    """Result container for async operations."""

    def __init__(self, task_id: str, total_items: int, operation_type: str):
        self.task_id = task_id
        self.total_items = total_items
        self.operation_type = operation_type
        self.success_count = 0
        self.error_count = 0
        self.errors: list[dict[str, Any]] = []
        self.created_ids: list[int] = []
        self.updated_ids: list[int] = []
        self.deleted_ids: list[int] = []

    def add_success(self, item_id: int | None = None, operation: str = "created"):
        self.success_count += 1
        if item_id:
            if operation == "created":
                self.created_ids.append(item_id)
            elif operation == "updated":
                self.updated_ids.append(item_id)
            elif operation == "deleted":
                self.deleted_ids.append(item_id)

    def add_error(self, index: int, error_message: str, item_data: Any = None):
        self.error_count += 1
        self.errors.append({
            "index": index,
            "error": error_message,
            "data": item_data,
        })

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "operation_type": self.operation_type,
            "total_items": self.total_items,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "errors": self.errors,
            "created_ids": self.created_ids,
            "updated_ids": self.updated_ids,
            "deleted_ids": self.deleted_ids,
        }


@shared_task(bind=True)
def async_create_task(self, serializer_class_path: str, data_list: list[dict], user_id: int | None = None):
    """
    Celery task for async creation of model instances.

    Args:
        serializer_class_path: Full path to the serializer class
            (e.g., 'augend.financial_transactions.api.serializers.FinancialTransactionSerializer')
        data_list: List of dictionaries containing data for each instance
        user_id: Optional user ID for audit purposes
    """
    task_id = self.request.id
    result = OperationResult(task_id, len(data_list), "async_create")

    # Initialize progress tracking in Redis
    OperationCache.set_task_progress(task_id, 0, len(data_list), "Starting async create...")

    try:
        serializer_class = import_string(serializer_class_path)
        instances_to_create = []

        # Validate all items first
        OperationCache.set_task_progress(task_id, 0, len(data_list), "Validating data...")
        
        for index, item_data in enumerate(data_list):
            try:
                serializer = serializer_class(data=item_data)
                if serializer.is_valid():
                    instances_to_create.append((index, serializer.validated_data))
                else:
                    result.add_error(index, str(serializer.errors), item_data)
            except (ValidationError, ValueError) as e:
                result.add_error(index, str(e), item_data)
            
            # Update progress every 10 items or at the end
            if (index + 1) % 10 == 0 or index == len(data_list) - 1:
                OperationCache.set_task_progress(
                    task_id, index + 1, len(data_list), f"Validated {index + 1}/{len(data_list)} items",
                )

        # Create instances
        if instances_to_create:
            OperationCache.set_task_progress(
                task_id, len(data_list), len(data_list), "Creating instances...",
            )
            
            model_class = serializer_class.Meta.model
            new_instances = [model_class(**validated_data) for _, validated_data in instances_to_create]
            
            with transaction.atomic():
                created_instances = model_class.objects.bulk_create(new_instances)

                for instance in created_instances:
                    result.add_success(instance.id, "created")

        # Store final result in cache
        OperationCache.set_task_result(task_id, result.to_dict())

        logger.info(
            "Async create task %s completed: %s created, %s errors",
            task_id,
            result.success_count,
            result.error_count,
        )

    except (ImportError, AttributeError) as e:
        logger.exception("Async create task %s failed", task_id)
        result.add_error(0, f"Task failed: {e!s}")
        OperationCache.set_task_result(task_id, result.to_dict())

    return result.to_dict()


@shared_task(bind=True)
def async_update_task(self, serializer_class_path: str, updates_list: list[dict], user_id: int | None = None):
    """
    Celery task for async updating of model instances.
    
    Efficiently updates multiple instances using optimized database operations
    to reduce queries from N+1 to just 2 queries.

    Args:
        serializer_class_path: Full path to the serializer class
        updates_list: List of dictionaries containing id and update data for each instance
        user_id: Optional user ID for audit purposes
    """
    task_id = self.request.id
    result = OperationResult(task_id, len(updates_list), "async_update")

    # Initialize progress tracking in Redis
    OperationCache.set_task_progress(task_id, 0, len(updates_list), "Starting async update...")

    try:
        serializer_class = import_string(serializer_class_path)
        model_class = serializer_class.Meta.model

        # Extract all IDs for retrieval
        ids_to_update = [update_data.get("id") for update_data in updates_list if update_data.get("id")]
        
        if not ids_to_update:
            result.add_error(0, "No valid IDs found in update data")
            OperationCache.set_task_result(task_id, result.to_dict())
            return result.to_dict()

        # Single query to fetch all instances
        OperationCache.set_task_progress(task_id, 0, len(updates_list), "Fetching instances...")
        instances_dict = {
            instance.id: instance 
            for instance in model_class.objects.filter(id__in=ids_to_update)
        }

        # Validate and prepare updates
        OperationCache.set_task_progress(task_id, 0, len(updates_list), "Validating updates...")
        valid_updates = []
        fields_to_update = set()

        for index, update_data in enumerate(updates_list):
            try:
                instance_id = update_data.get("id")
                if not instance_id:
                    result.add_error(index, "Missing 'id' field", update_data)
                    continue

                instance = instances_dict.get(instance_id)
                if not instance:
                    result.add_error(index, f"Instance with id {instance_id} not found", update_data)
                    continue

                serializer = serializer_class(instance, data=update_data, partial=True)
                if serializer.is_valid():
                    # Update instance with validated data
                    for field, value in serializer.validated_data.items():
                        setattr(instance, field, value)
                        fields_to_update.add(field)
                    
                    valid_updates.append((index, instance, instance_id))
                else:
                    result.add_error(index, str(serializer.errors), update_data)

            except (ValidationError, ValueError) as e:
                result.add_error(index, str(e), update_data)

            # Update progress every 10 items
            if (index + 1) % 10 == 0 or index == len(updates_list) - 1:
                OperationCache.set_task_progress(
                    task_id, index + 1, len(updates_list), f"Validated {index + 1}/{len(updates_list)} items",
                )

        # Single bulk_update query for all valid instances
        if valid_updates:
            OperationCache.set_task_progress(
                task_id, len(updates_list), len(updates_list), "Performing async update..."
            )
            
            instances_to_update = [instance for _, instance, _ in valid_updates]
            fields_list = list(fields_to_update)
            
            with transaction.atomic():
                # Single query to update all instances
                updated_count = model_class.objects.bulk_update(
                    instances_to_update, 
                    fields_list,
                    batch_size=1000  # Process in batches for very large updates
                )
                
                # Mark successful updates
                for _, instance, instance_id in valid_updates:
                    result.add_success(instance_id, "updated")

        # Store final result in cache
        OperationCache.set_task_result(task_id, result.to_dict())

        logger.info(
            "Async update task %s completed: %s updated, %s errors",
            task_id,
            result.success_count,
            result.error_count,
        )

    except (ImportError, AttributeError) as e:
        logger.exception("Async update task %s failed", task_id)
        result.add_error(0, f"Task failed: {e!s}")
        OperationCache.set_task_result(task_id, result.to_dict())

    return result.to_dict()


@shared_task(bind=True)
def async_replace_task(self, serializer_class_path: str, replacements_list: list[dict], user_id: int | None = None):
    """
    Celery task for async replacement (full update) of model instances.

    Args:
        serializer_class_path: Full path to the serializer class
        replacements_list: List of dictionaries containing complete object data
        user_id: Optional user ID for audit purposes
    """
    task_id = self.request.id
    result = OperationResult(task_id, len(replacements_list), "async_replace")

    # Initialize progress tracking in Redis
    OperationCache.set_task_progress(task_id, 0, len(replacements_list), "Starting async replace...")

    try:
        serializer_class = import_string(serializer_class_path)
        model_class = serializer_class.Meta.model

        # Extract all IDs for retrieval
        ids_to_replace = [replacement_data.get("id") for replacement_data in replacements_list if replacement_data.get("id")]
        
        if not ids_to_replace:
            result.add_error(0, "No valid IDs found in replacement data")
            OperationCache.set_task_result(task_id, result.to_dict())
            return result.to_dict()

        # Single query to fetch all instances
        OperationCache.set_task_progress(task_id, 0, len(replacements_list), "Fetching instances...")
        instances_dict = {
            instance.id: instance 
            for instance in model_class.objects.filter(id__in=ids_to_replace)
        }

        # Validate and prepare replacements
        OperationCache.set_task_progress(task_id, 0, len(replacements_list), "Validating replacements...")
        valid_replacements = []
        all_fields = set()

        for index, replacement_data in enumerate(replacements_list):
            try:
                instance_id = replacement_data.get("id")
                if not instance_id:
                    result.add_error(index, "Missing 'id' field", replacement_data)
                    continue

                instance = instances_dict.get(instance_id)
                if not instance:
                    result.add_error(index, f"Instance with id {instance_id} not found", replacement_data)
                    continue

                serializer = serializer_class(instance, data=replacement_data)
                if serializer.is_valid():
                    # Replace instance with validated data
                    for field, value in serializer.validated_data.items():
                        setattr(instance, field, value)
                        all_fields.add(field)
                    
                    valid_replacements.append((index, instance, instance_id))
                else:
                    result.add_error(index, str(serializer.errors), replacement_data)

            except (ValidationError, ValueError) as e:
                result.add_error(index, str(e), replacement_data)

            # Update progress every 10 items
            if (index + 1) % 10 == 0 or index == len(replacements_list) - 1:
                OperationCache.set_task_progress(
                    task_id, index + 1, len(replacements_list), f"Validated {index + 1}/{len(replacements_list)} items",
                )

        # Single bulk_update query for all valid instances
        if valid_replacements:
            OperationCache.set_task_progress(
                task_id, len(replacements_list), len(replacements_list), "Performing async replace..."
            )
            
            instances_to_replace = [instance for _, instance, _ in valid_replacements]
            fields_list = list(all_fields)
            
            with transaction.atomic():
                # Single query to replace all instances
                replaced_count = model_class.objects.bulk_update(
                    instances_to_replace, 
                    fields_list,
                    batch_size=1000
                )
                
                # Mark successful replacements
                for _, instance, instance_id in valid_replacements:
                    result.add_success(instance_id, "updated")

        # Store final result in cache
        OperationCache.set_task_result(task_id, result.to_dict())

        logger.info(
            "Async replace task %s completed: %s replaced, %s errors",
            task_id,
            result.success_count,
            result.error_count,
        )

    except (ImportError, AttributeError) as e:
        logger.exception("Async replace task %s failed", task_id)
        result.add_error(0, f"Task failed: {e!s}")
        OperationCache.set_task_result(task_id, result.to_dict())

    return result.to_dict()


@shared_task(bind=True)
def async_delete_task(self, model_class_path: str, ids_list: list[int], user_id: int | None = None):
    """
    Celery task for async deletion of model instances.

    Args:
        model_class_path: Full path to the model class
        ids_list: List of IDs to delete
        user_id: Optional user ID for audit purposes
    """
    task_id = self.request.id
    result = OperationResult(task_id, len(ids_list), "async_delete")

    # Initialize progress tracking in Redis
    OperationCache.set_task_progress(task_id, 0, len(ids_list), "Starting async delete...")

    try:
        model_class = import_string(model_class_path)

        OperationCache.set_task_progress(task_id, 0, len(ids_list), "Deleting instances...")
        
        with transaction.atomic():
            # Use optimized delete operation for efficiency
            deleted_count, _ = model_class.objects.filter(id__in=ids_list).delete()

            # Mark successful deletions
            for item_id in ids_list:
                result.add_success(item_id, "deleted")

        # Store final result in cache
        OperationCache.set_task_result(task_id, result.to_dict())

        logger.info(
            "Async delete task %s completed: %s deleted",
            task_id,
            deleted_count,
        )

    except (ImportError, AttributeError) as e:
        logger.exception("Async delete task %s failed", task_id)
        result.add_error(0, f"Task failed: {e!s}")
        OperationCache.set_task_result(task_id, result.to_dict())

    return result.to_dict()


@shared_task(bind=True)
def async_get_task(
    self, 
    model_class_path: str, 
    serializer_class_path: str, 
    query_data: dict, 
    user_id: int | None = None
):
    """
    Celery task for async retrieval of model instances.

    Args:
        model_class_path: Full path to the model class
        serializer_class_path: Full path to the serializer class
        query_data: Dictionary containing query parameters
        user_id: Optional user ID for audit purposes
    """
    task_id = self.request.id

    # Initialize progress tracking in Redis
    OperationCache.set_task_progress(task_id, 0, 1, "Starting async get...")

    try:
        model_class = import_string(model_class_path)
        serializer_class = import_string(serializer_class_path)

        OperationCache.set_task_progress(task_id, 0, 1, "Executing query...")

        # Handle different query types
        if "ids" in query_data:
            # ID-based retrieval
            ids_list = query_data["ids"]
            queryset = model_class.objects.filter(id__in=ids_list)
        elif "filters" in query_data:
            # Complex filter-based retrieval
            filters = query_data["filters"]
            queryset = model_class.objects.filter(**filters)
        else:
            # Default queryset
            queryset = model_class.objects.all()

        # Serialize the results
        OperationCache.set_task_progress(task_id, 1, 1, "Serializing results...")
        serializer = serializer_class(queryset, many=True)
        serialized_data = serializer.data

        # Store final result in cache
        result = {
            "task_id": task_id,
            "operation_type": "async_get",
            "count": len(serialized_data),
            "results": serialized_data,
            "success": True,
        }
        OperationCache.set_task_result(task_id, result)

        logger.info(
            "Async get task %s completed: %s records retrieved",
            task_id,
            len(serialized_data),
        )

        return result

    except (ImportError, AttributeError) as e:
        logger.exception("Async get task %s failed", task_id)
        error_result = {
            "task_id": task_id,
            "operation_type": "async_get",
            "error": f"Task failed: {e!s}",
            "success": False,
        }
        OperationCache.set_task_result(task_id, error_result)
        return error_result


@shared_task(bind=True)
def async_upsert_task(
    self, 
    serializer_class_path: str, 
    data_list: list[dict], 
    unique_fields: list[str],
    update_fields: list[str] | None = None,
    user_id: int | None = None
):
    """
    Celery task for async upsert (insert or update) of model instances.
    
    Intelligent upsert operation that creates new records or updates existing ones
    based on unique field constraints.

    Args:
        serializer_class_path: Full path to the serializer class
        data_list: List of dictionaries containing data for each instance
        unique_fields: List of field names that form the unique constraint
        update_fields: List of field names to update on conflict (if None, updates all fields)
        user_id: Optional user ID for audit purposes
    """
    task_id = self.request.id
    result = OperationResult(task_id, len(data_list), "async_upsert")

    # Initialize progress tracking in Redis
    OperationCache.set_task_progress(task_id, 0, len(data_list), "Starting async upsert...")

    try:
        serializer_class = import_string(serializer_class_path)
        model_class = serializer_class.Meta.model
        instances_to_create = []
        instances_to_update = []

        # Validate all items first
        OperationCache.set_task_progress(task_id, 0, len(data_list), "Validating data...")
        
        for index, item_data in enumerate(data_list):
            try:
                # Pre-process foreign key fields before serializer validation
                processed_data = item_data.copy()
                for field_name, field_value in item_data.items():
                    if hasattr(model_class, field_name) and hasattr(getattr(model_class, field_name), 'field'):
                        field_obj = getattr(model_class, field_name).field
                        if hasattr(field_obj, 'related_model') and field_obj.related_model:
                            # This is a foreign key field, try to get the related object
                            try:
                                related_obj = field_obj.related_model.objects.get(pk=field_value)
                                processed_data[field_name] = related_obj
                            except field_obj.related_model.DoesNotExist:
                                result.add_error(index, f"Related object with id {field_value} does not exist for field {field_name}", item_data)
                                continue

                serializer = serializer_class(data=processed_data)
                if serializer.is_valid():
                    validated_data = serializer.validated_data
                    
                    # Check if record exists based on unique fields
                    unique_filter = {}
                    for field in unique_fields:
                        if field in validated_data:
                            unique_filter[field] = validated_data[field]
                        else:
                            result.add_error(index, f"Missing required unique field: {field}", item_data)
                            continue
                    
                    if unique_filter:
                        # Try to find existing instance - handle foreign key fields properly
                        db_filter = {}
                        for field, value in unique_filter.items():
                            # Check if this is a foreign key field
                            if hasattr(model_class, field) and hasattr(getattr(model_class, field), 'field'):
                                field_obj = getattr(model_class, field).field
                                if hasattr(field_obj, 'related_model') and field_obj.related_model:
                                    # This is a foreign key, try to get the related object
                                    try:
                                        related_obj = field_obj.related_model.objects.get(pk=value)
                                        db_filter[field] = related_obj
                                    except field_obj.related_model.DoesNotExist:
                                        result.add_error(index, f"Related object with id {value} does not exist for field {field}", item_data)
                                        continue
                                else:
                                    db_filter[field] = value
                            else:
                                db_filter[field] = value

                        existing_instance = model_class.objects.filter(**db_filter).first()
                        
                        if existing_instance:
                            # Update existing instance
                            if update_fields:
                                # Only update specified fields
                                update_data = {k: v for k, v in validated_data.items() 
                                             if k in update_fields}
                            else:
                                # Update all fields except unique fields
                                update_data = {k: v for k, v in validated_data.items() 
                                             if k not in unique_fields}
                            
                            # Update the instance
                            for field, value in update_data.items():
                                setattr(existing_instance, field, value)
                            
                            instances_to_update.append((index, existing_instance, existing_instance.id))
                        else:
                            # Create new instance
                            instance = model_class(**validated_data)
                            instances_to_create.append((index, instance))
                    else:
                        result.add_error(index, "No valid unique fields found", item_data)
                else:
                    result.add_error(index, str(serializer.errors), item_data)
            except (ValidationError, ValueError) as e:
                result.add_error(index, str(e), item_data)
            
            # Update progress every 10 items or at the end
            if (index + 1) % 10 == 0 or index == len(data_list) - 1:
                OperationCache.set_task_progress(
                    task_id, index + 1, len(data_list), f"Validated {index + 1}/{len(data_list)} items",
                )

        # Create new instances
        if instances_to_create:
            OperationCache.set_task_progress(
                task_id, len(data_list), len(data_list), "Creating new instances...",
            )
            
            with transaction.atomic():
                new_instances = [instance for _, instance in instances_to_create]
                created_instances = model_class.objects.bulk_create(new_instances)

                for instance in created_instances:
                    result.add_success(instance.id, "created")

        # Update existing instances
        if instances_to_update:
            OperationCache.set_task_progress(
                task_id, len(data_list), len(data_list), "Updating existing instances...",
            )
            
            with transaction.atomic():
                update_instances = [instance for _, instance, _ in instances_to_update]
                
                # Determine fields to update
                if update_fields:
                    fields_to_update = [field for field in update_fields 
                                      if any(hasattr(instance, field) for instance in update_instances)]
                else:
                    # Get all non-unique fields from the first instance
                    if update_instances:
                        first_instance = update_instances[0]
                        fields_to_update = [field.name for field in first_instance._meta.fields 
                                          if field.name not in unique_fields and not field.primary_key]
                    else:
                        fields_to_update = []
                
                if fields_to_update:
                    updated_count = model_class.objects.bulk_update(
                        update_instances, 
                        fields_to_update,
                        batch_size=1000
                    )
                    
                    # Mark successful updates
                    for _, instance, instance_id in instances_to_update:
                        result.add_success(instance_id, "updated")

        # Store final result in cache
        OperationCache.set_task_result(task_id, result.to_dict())

        logger.info(
            "Async upsert task %s completed: %s created, %s updated, %s errors",
            task_id,
            len([op for op in result.created_ids]),
            len([op for op in result.updated_ids]),
            result.error_count,
        )

    except (ImportError, AttributeError) as e:
        logger.exception("Async upsert task %s failed", task_id)
        result.add_error(0, f"Task failed: {e!s}")
        OperationCache.set_task_result(task_id, result.to_dict())

    return result.to_dict() 