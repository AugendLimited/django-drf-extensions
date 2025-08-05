"""
Enhanced processing utilities with job state tracking.

Provides controlled concurrency and explicit job state management
for bulk operations with aggregate support.
"""

import logging
from typing import Any, Dict, List, Optional

from celery import shared_task
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Avg, Sum
from django.utils.module_loading import import_string

from django_drf_extensions.cache import OperationCache
from django_drf_extensions.job_state import (
    BulkJob,
    JobState,
    JobStateManager,
    JobType,
)

logger = logging.getLogger(__name__)


class EnhancedOperationResult:
    """Enhanced result container with job state integration."""

    def __init__(self, job_id: str, total_items: int, operation_type: str):
        self.job_id = job_id
        self.total_items = total_items
        self.operation_type = operation_type
        self.success_count = 0
        self.error_count = 0
        self.errors: List[Dict[str, Any]] = []
        self.created_ids: List[int] = []
        self.updated_ids: List[int] = []
        self.deleted_ids: List[int] = []

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
        self.errors.append(
            {
                "index": index,
                "error": error_message,
                "data": item_data,
            }
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
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
def enhanced_create_task(
    self,
    job_id: str,
    serializer_class_path: str,
    data_list: List[Dict],
    user_id: Optional[int] = None,
):
    """
    Enhanced Celery task for async creation with job state tracking.

    Args:
        job_id: Job ID for state tracking
        serializer_class_path: Full path to the serializer class
        data_list: List of dictionaries containing data for each instance
        user_id: Optional user ID for audit purposes
    """
    result = EnhancedOperationResult(job_id, len(data_list), "enhanced_create")

    # Update job state to in progress
    JobStateManager.update_job_state(
        job_id, JobState.IN_PROGRESS, processed_items=0, total_items=len(data_list)
    )

    try:
        serializer_class = import_string(serializer_class_path)
        instances_to_create = []

        # Validate all items first
        JobStateManager.update_job_state(
            job_id, JobState.IN_PROGRESS, processed_items=0
        )

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
                JobStateManager.update_job_state(
                    job_id,
                    JobState.IN_PROGRESS,
                    processed_items=index + 1,
                    success_count=result.success_count,
                    error_count=result.error_count,
                )

        # Create instances
        if instances_to_create:
            JobStateManager.update_job_state(
                job_id, JobState.IN_PROGRESS, processed_items=len(data_list)
            )

            model_class = serializer_class.Meta.model
            new_instances = [
                model_class(**validated_data)
                for _, validated_data in instances_to_create
            ]

            with transaction.atomic():
                created_instances = model_class.objects.bulk_create(new_instances)

                for instance in created_instances:
                    result.add_success(instance.id, "created")

        # Update final state
        JobStateManager.update_job_state(
            job_id,
            JobState.JOB_COMPLETE,
            processed_items=len(data_list),
            success_count=result.success_count,
            error_count=result.error_count,
            created_ids=result.created_ids,
            updated_ids=result.updated_ids,
            deleted_ids=result.deleted_ids,
            errors=result.errors,
        )

        logger.info(
            "Enhanced create task %s completed: %s created, %s errors",
            job_id,
            result.success_count,
            result.error_count,
        )

    except Exception as e:
        logger.exception("Enhanced create task %s failed", job_id)
        result.add_error(0, f"Task failed: {e!s}")

        JobStateManager.update_job_state(
            job_id,
            JobState.FAILED,
            processed_items=len(data_list),
            success_count=result.success_count,
            error_count=result.error_count,
            errors=result.errors,
        )

    return result.to_dict()


@shared_task(bind=True)
def enhanced_upsert_task(
    self,
    job_id: str,
    serializer_class_path: str,
    data_list: List[Dict],
    unique_fields: List[str],
    update_fields: Optional[List[str]] = None,
    user_id: Optional[int] = None,
):
    """
    Enhanced Celery task for async upsert with job state tracking.

    Args:
        job_id: Job ID for state tracking
        serializer_class_path: Full path to the serializer class
        data_list: List of dictionaries containing data for each instance
        unique_fields: List of field names that form the unique constraint
        update_fields: List of field names to update on conflict (if None, updates all fields)
        user_id: Optional user ID for audit purposes
    """
    result = EnhancedOperationResult(job_id, len(data_list), "enhanced_upsert")

    # Update job state to in progress
    JobStateManager.update_job_state(
        job_id, JobState.IN_PROGRESS, processed_items=0, total_items=len(data_list)
    )

    try:
        serializer_class = import_string(serializer_class_path)
        model_class = serializer_class.Meta.model
        instances_to_create = []
        instances_to_update = []

        # Validate all items first
        JobStateManager.update_job_state(
            job_id, JobState.IN_PROGRESS, processed_items=0
        )

        for index, item_data in enumerate(data_list):
            try:
                serializer = serializer_class(data=item_data)
                if serializer.is_valid():
                    validated_data = serializer.validated_data

                    # Check if record exists based on unique fields
                    unique_filter = {}
                    lookup_filter = {}
                    for field in unique_fields:
                        if field in validated_data:
                            unique_filter[field] = validated_data[field]
                            # For foreign key fields, use _id suffix in lookup filter
                            if hasattr(model_class, field) and hasattr(
                                getattr(model_class, field), "field"
                            ):
                                field_obj = getattr(model_class, field).field
                                if (
                                    hasattr(field_obj, "related_model")
                                    and field_obj.related_model
                                ):
                                    # This is a foreign key, use _id suffix for lookup
                                    lookup_filter[f"{field}_id"] = validated_data[field]
                                else:
                                    lookup_filter[field] = validated_data[field]
                            else:
                                lookup_filter[field] = validated_data[field]
                        else:
                            result.add_error(
                                index,
                                f"Missing required unique field: {field}",
                                item_data,
                            )
                            continue

                    if unique_filter:
                        # Try to find existing instance
                        existing_instance = model_class.objects.filter(
                            **lookup_filter
                        ).first()

                        if existing_instance:
                            # Update existing instance
                            if update_fields:
                                # Only update specified fields
                                update_data = {
                                    k: v
                                    for k, v in validated_data.items()
                                    if k in update_fields
                                }
                            else:
                                # Update all fields except unique fields
                                update_data = {
                                    k: v
                                    for k, v in validated_data.items()
                                    if k not in unique_fields
                                }

                            # Update the instance
                            for field, value in update_data.items():
                                setattr(existing_instance, field, value)

                            instances_to_update.append(
                                (index, existing_instance, existing_instance.id)
                            )
                        else:
                            # Create new instance
                            instance = model_class(**validated_data)
                            instances_to_create.append((index, instance))
                    else:
                        result.add_error(
                            index, "No valid unique fields found", item_data
                        )
                else:
                    result.add_error(index, str(serializer.errors), item_data)
            except (ValidationError, ValueError) as e:
                result.add_error(index, str(e), item_data)

            # Update progress every 10 items or at the end
            if (index + 1) % 10 == 0 or index == len(data_list) - 1:
                JobStateManager.update_job_state(
                    job_id,
                    JobState.IN_PROGRESS,
                    processed_items=index + 1,
                    success_count=result.success_count,
                    error_count=result.error_count,
                )

        # Create new instances
        if instances_to_create:
            JobStateManager.update_job_state(
                job_id, JobState.IN_PROGRESS, processed_items=len(data_list)
            )

            with transaction.atomic():
                new_instances = [instance for _, instance in instances_to_create]
                created_instances = model_class.objects.bulk_create(new_instances)

                for instance in created_instances:
                    result.add_success(instance.id, "created")

        # Update existing instances
        if instances_to_update:
            JobStateManager.update_job_state(
                job_id, JobState.IN_PROGRESS, processed_items=len(data_list)
            )

            with transaction.atomic():
                update_instances = [instance for _, instance, _ in instances_to_update]

                # Determine fields to update
                if update_fields:
                    fields_to_update = [
                        field
                        for field in update_fields
                        if any(
                            hasattr(instance, field) for instance in update_instances
                        )
                    ]
                else:
                    # Get all non-unique fields from the first instance
                    if update_instances:
                        first_instance = update_instances[0]
                        fields_to_update = [
                            field.name
                            for field in first_instance._meta.fields
                            if field.name not in unique_fields and not field.primary_key
                        ]
                    else:
                        fields_to_update = []

                if fields_to_update:
                    updated_count = model_class.objects.bulk_update(
                        update_instances, fields_to_update, batch_size=1000
                    )

                    # Mark successful updates
                    for _, instance, instance_id in instances_to_update:
                        result.add_success(instance_id, "updated")

        # Update final state
        JobStateManager.update_job_state(
            job_id,
            JobState.JOB_COMPLETE,
            processed_items=len(data_list),
            success_count=result.success_count,
            error_count=result.error_count,
            created_ids=result.created_ids,
            updated_ids=result.updated_ids,
            deleted_ids=result.deleted_ids,
            errors=result.errors,
        )

        logger.info(
            "Enhanced upsert task %s completed: %s created, %s updated, %s errors",
            job_id,
            len(result.created_ids),
            len(result.updated_ids),
            result.error_count,
        )

    except Exception as e:
        logger.exception("Enhanced upsert task %s failed", job_id)
        result.add_error(0, f"Task failed: {e!s}")

        JobStateManager.update_job_state(
            job_id,
            JobState.FAILED,
            processed_items=len(data_list),
            success_count=result.success_count,
            error_count=result.error_count,
            errors=result.errors,
        )

    return result.to_dict()


@shared_task(bind=True)
def enhanced_delete_task(
    self,
    job_id: str,
    model_class_path: str,
    ids_list: List[int],
    user_id: Optional[int] = None,
):
    """
    Enhanced Celery task for async deletion with job state tracking.

    Args:
        job_id: Job ID for state tracking
        model_class_path: Full path to the model class
        ids_list: List of IDs to delete
        user_id: Optional user ID for audit purposes
    """
    result = EnhancedOperationResult(job_id, len(ids_list), "enhanced_delete")

    # Update job state to in progress
    JobStateManager.update_job_state(
        job_id, JobState.IN_PROGRESS, processed_items=0, total_items=len(ids_list)
    )

    try:
        model_class = import_string(model_class_path)

        # Validate IDs exist
        existing_ids = set(
            model_class.objects.filter(id__in=ids_list).values_list("id", flat=True)
        )

        if not existing_ids:
            result.add_error(0, "No valid IDs found to delete")
            JobStateManager.update_job_state(
                job_id, JobState.FAILED, error_count=1, errors=result.errors
            )
            return result.to_dict()

        # Perform bulk delete
        with transaction.atomic():
            deleted_count = model_class.objects.filter(id__in=existing_ids).delete()[0]

            for deleted_id in existing_ids:
                result.add_success(deleted_id, "deleted")

        # Update job state to completed
        JobStateManager.update_job_state(
            job_id,
            JobState.JOB_COMPLETE,
            processed_items=len(ids_list),
            success_count=result.success_count,
            error_count=result.error_count,
            deleted_ids=result.deleted_ids,
            errors=result.errors,
        )

        logger.info(
            "Enhanced delete task %s completed: %s deleted, %s errors",
            job_id,
            result.success_count,
            result.error_count,
        )

    except Exception as e:
        logger.exception("Enhanced delete task %s failed", job_id)
        result.add_error(0, f"Task failed: {e!s}")
        JobStateManager.update_job_state(
            job_id, JobState.FAILED, error_count=1, errors=result.errors
        )

    return result.to_dict()


@shared_task(bind=True)
def run_aggregates_task(self, job_id: str, aggregate_config: Dict[str, Any]):
    """
    Run aggregates on completed bulk job data.

    This task runs after a bulk job is completed and aggregates_ready=True.
    It provides controlled access to the inserted/updated data for aggregation.

    Args:
        job_id: Job ID to run aggregates on
        aggregate_config: Configuration for aggregates to run
    """
    job = JobStateManager.get_job(job_id)
    if not job:
        logger.error("Job %s not found for aggregates", job_id)
        return {"error": "Job not found"}

    if not job.aggregates_ready:
        logger.error("Job %s not ready for aggregates", job_id)
        return {"error": "Job not ready for aggregates"}

    if job.aggregates_completed:
        logger.info("Aggregates already completed for job %s", job_id)
        return job.aggregate_results

    try:
        # Import model class
        model_class = import_string(job.model_class_path)

        # Build query based on job results
        query = model_class.objects.all()

        # Filter to only records affected by this job
        if job.created_ids:
            query = query.filter(id__in=job.created_ids)
        elif job.updated_ids:
            query = query.filter(id__in=job.updated_ids)

        # Run configured aggregates
        aggregate_results = {}

        for aggregate_name, config in aggregate_config.items():
            if config.get("type") == "count":
                aggregate_results[aggregate_name] = query.count()
            elif config.get("type") == "sum":
                field = config.get("field")
                if field:
                    aggregate_results[aggregate_name] = (
                        query.aggregate(total=Sum(field))["total"] or 0
                    )
            elif config.get("type") == "avg":
                field = config.get("field")
                if field:
                    aggregate_results[aggregate_name] = (
                        query.aggregate(average=Avg(field))["average"] or 0
                    )
            elif config.get("type") == "custom":
                # Custom aggregate function
                custom_func = config.get("function")
                if custom_func:
                    aggregate_results[aggregate_name] = custom_func(query)

        # Update job with aggregate results
        JobStateManager.update_job_state(
            job_id,
            job.state,  # Keep current state
            aggregates_completed=True,
            aggregate_results=aggregate_results,
        )

        logger.info("Aggregates completed for job %s: %s", job_id, aggregate_results)
        return aggregate_results

    except Exception as e:
        logger.exception("Aggregates failed for job %s", job_id)
        return {"error": f"Aggregates failed: {e!s}"}
