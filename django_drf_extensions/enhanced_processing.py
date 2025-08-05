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
from django.db.models import Avg, Count, F, Q, Sum
from django.utils.module_loading import import_string

from django_drf_extensions.cache import OperationCache
from django_drf_extensions.job_state import (
    BulkJob,
    JobState,
    JobStateManager,
    JobType,
)

from .models import DailyFinancialAggregates, FinancialTransaction

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


@shared_task
def process_transactions_pipeline_task(
    job_id, transaction_data, credit_model_config=None, aggregate_config=None
):
    """
    Complete pipeline task that:
    1. Imports transactions
    2. Aggregates data
    3. Runs credit model
    4. Generates offers
    """
    try:
        # Update job state to IN_PROGRESS
        JobStateManager.update_job_state(
            job_id, JobState.IN_PROGRESS, "Starting transaction pipeline"
        )

        # Step 1: Import transactions
        JobStateManager.update_job_state(
            job_id, JobState.IN_PROGRESS, "Importing transactions"
        )

        # Use the existing enhanced create task for transaction import
        result = enhanced_create_task.delay(
            job_id=f"{job_id}_import",
            data=transaction_data,
            model_name="FinancialTransaction",  # Adjust based on your model
        )

        # Wait for import to complete
        import_result = result.get()

        if not import_result.success:
            JobStateManager.update_job_state(
                job_id,
                JobState.FAILED,
                f"Transaction import failed: {import_result.errors}",
            )
            return

        # Step 2: Aggregate data
        JobStateManager.update_job_state(
            job_id, JobState.IN_PROGRESS, "Running aggregations"
        )

        # Run your aggregation logic
        aggregate_result = run_aggregates_task.delay(job_id, aggregate_config or {})
        aggregate_result.get()  # Wait for completion

        # Step 3: Run credit model
        JobStateManager.update_job_state(
            job_id, JobState.IN_PROGRESS, "Running credit model"
        )

        credit_model_results = run_credit_model_task.delay(
            job_id=job_id,
            config=credit_model_config or {},
            aggregate_data=aggregate_result.result,
        ).get()

        # Step 4: Generate offers
        JobStateManager.update_job_state(
            job_id, JobState.IN_PROGRESS, "Generating offers"
        )

        offers = generate_offers_task.delay(
            job_id=job_id,
            credit_model_results=credit_model_results,
            transaction_count=len(transaction_data),
        ).get()

        # Update job with final results
        JobStateManager.update_job_metadata(
            job_id,
            {
                "offers": offers,
                "pipeline_summary": {
                    "transactions_processed": len(transaction_data),
                    "aggregates_created": len(aggregate_result.result),
                    "offers_generated": len(offers),
                },
                "credit_model_results": credit_model_results,
            },
        )

        # Mark pipeline as complete
        JobStateManager.update_job_state(
            job_id, JobState.JOB_COMPLETE, "Pipeline completed successfully"
        )

    except Exception as e:
        JobStateManager.update_job_state(
            job_id, JobState.FAILED, f"Pipeline failed: {str(e)}"
        )
        raise


@shared_task
def run_credit_model_task(job_id, config, aggregate_data):
    """
    Run credit model on aggregated data
    This is a placeholder - implement your actual credit model logic
    """
    try:
        # Your credit model implementation here
        # Example:
        credit_scores = {}
        risk_assessments = {}

        for date, aggregate in aggregate_data.items():
            # Calculate credit score based on aggregate data
            credit_score = calculate_credit_score(aggregate, config)
            risk_assessment = assess_risk(aggregate, config)

            credit_scores[date] = credit_score
            risk_assessments[date] = risk_assessment

        return {
            "credit_scores": credit_scores,
            "risk_assessments": risk_assessments,
            "model_version": config.get("model_version", "v1.0"),
            "config_used": config,
        }

    except Exception as e:
        JobStateManager.update_job_state(
            job_id, JobState.FAILED, f"Credit model failed: {str(e)}"
        )
        raise


@shared_task
def generate_offers_task(job_id, credit_model_results, transaction_count):
    """
    Generate offers based on credit model results
    This is a placeholder - implement your actual offer generation logic
    """
    try:
        offers = []

        # Your offer generation logic here
        # Example:
        for date, credit_score in credit_model_results["credit_scores"].items():
            risk_assessment = credit_model_results["risk_assessments"][date]

            # Generate offer based on credit score and risk
            offer = generate_offer_for_date(
                date=date,
                credit_score=credit_score,
                risk_assessment=risk_assessment,
                transaction_count=transaction_count,
            )

            offers.append(offer)

        return offers

    except Exception as e:
        JobStateManager.update_job_state(
            job_id, JobState.FAILED, f"Offer generation failed: {str(e)}"
        )
        raise


# Placeholder functions for credit model and offer generation
def calculate_credit_score(aggregate_data, config):
    """Calculate credit score based on aggregate data"""
    # Implement your credit scoring logic
    return 750  # Example score


def assess_risk(aggregate_data, config):
    """Assess risk based on aggregate data"""
    # Implement your risk assessment logic
    return "LOW"  # Example risk level


def generate_offer_for_date(date, credit_score, risk_assessment, transaction_count):
    """Generate offer for a specific date"""
    # Implement your offer generation logic
    return {
        "date": date,
        "offer_type": "credit_line",
        "amount": 10000,
        "interest_rate": 0.05,
        "credit_score": credit_score,
        "risk_level": risk_assessment,
        "transaction_count": transaction_count,
    }


@shared_task
def process_transactions_pipeline_hybrid_task(
    job_id, transaction_data, credit_model_config=None, aggregate_config=None
):
    """
    Hybrid pipeline that combines real-time aggregation with final consistency check:
    1. Import transactions with real-time aggregation
    2. Final consistency check and correction
    3. Run credit model
    4. Generate offers
    """
    try:
        JobStateManager.update_job_state(
            job_id, JobState.IN_PROGRESS, "Starting hybrid transaction pipeline"
        )

        # Step 1: Import with real-time aggregation
        JobStateManager.update_job_state(
            job_id,
            JobState.IN_PROGRESS,
            "Importing transactions with real-time aggregation",
        )

        # Use enhanced create task with real-time aggregation
        result = enhanced_create_with_realtime_aggregation.delay(
            job_id=f"{job_id}_import",
            data=transaction_data,
            model_name="FinancialTransaction",
            aggregate_config=aggregate_config or {},
        )

        # Wait for import to complete
        import_result = result.get()

        if not import_result.success:
            JobStateManager.update_job_state(
                job_id,
                JobState.FAILED,
                f"Transaction import failed: {import_result.errors}",
            )
            return

        # Step 2: Final consistency check
        JobStateManager.update_job_state(
            job_id, JobState.IN_PROGRESS, "Running final consistency check"
        )

        consistency_result = run_consistency_check.delay(
            job_id=job_id,
            transaction_ids=import_result.created_ids,
            aggregate_config=aggregate_config or {},
        ).get()

        # Step 3: Run credit model
        JobStateManager.update_job_state(
            job_id, JobState.IN_PROGRESS, "Running credit model"
        )

        credit_model_results = run_credit_model_task.delay(
            job_id=job_id,
            config=credit_model_config or {},
            aggregate_data=consistency_result,
        ).get()

        # Step 4: Generate offers
        JobStateManager.update_job_state(
            job_id, JobState.IN_PROGRESS, "Generating offers"
        )

        offers = generate_offers_task.delay(
            job_id=job_id,
            credit_model_results=credit_model_results,
            transaction_count=len(transaction_data),
        ).get()

        # Update job with final results
        JobStateManager.update_job_metadata(
            job_id,
            {
                "offers": offers,
                "pipeline_summary": {
                    "transactions_processed": len(transaction_data),
                    "aggregates_created": len(consistency_result),
                    "offers_generated": len(offers),
                    "consistency_corrections": consistency_result.get("corrections", 0),
                },
                "credit_model_results": credit_model_results,
            },
        )

        # Mark pipeline as complete
        JobStateManager.update_job_state(
            job_id, JobState.JOB_COMPLETE, "Hybrid pipeline completed successfully"
        )

    except Exception as e:
        JobStateManager.update_job_state(
            job_id, JobState.FAILED, f"Hybrid pipeline failed: {str(e)}"
        )
        raise


@shared_task
def enhanced_create_with_realtime_aggregation(
    job_id, data, model_name, aggregate_config=None
):
    """
    Enhanced create task that performs real-time aggregation during import.
    This provides speed while maintaining some consistency.
    """
    try:
        # Import transactions in batches with real-time aggregation
        batch_size = 1000
        created_ids = []

        for i in range(0, len(data), batch_size):
            batch = data[i : i + batch_size]

            # Import batch
            batch_result = enhanced_create_task.delay(
                job_id=f"{job_id}_batch_{i // batch_size}",
                data=batch,
                model_name=model_name,
            ).get()

            created_ids.extend(batch_result.created_ids)

            # Real-time aggregation for this batch
            if aggregate_config:
                run_realtime_aggregation.delay(
                    job_id=job_id,
                    transaction_ids=batch_result.created_ids,
                    aggregate_config=aggregate_config,
                )

        return EnhancedOperationResult(
            success=True,
            created_ids=created_ids,
            success_count=len(created_ids),
            error_count=0,
        )

    except Exception as e:
        return EnhancedOperationResult(success=False, errors=[str(e)], error_count=1)


@shared_task
def run_realtime_aggregation(job_id, transaction_ids, aggregate_config):
    """
    Perform real-time aggregation on a batch of transactions.
    This runs concurrently with import for speed.
    """
    try:
        # Get the transactions for this batch
        transactions = FinancialTransaction.objects.filter(id__in=transaction_ids)

        # Aggregate by date for this batch
        batch_aggregates = transactions.values("date").annotate(
            total_amount=Sum("amount"),
            revenue_amount=Sum("amount", filter=Q(is_revenue=True)),
            transaction_count=Count("id"),
        )

        # Update or create aggregates (with optimistic locking)
        for agg in batch_aggregates:
            DailyFinancialAggregates.objects.update_or_create(
                date=agg["date"],
                defaults={
                    "total_amount": F("total_amount") + agg["total_amount"],
                    "revenue_amount": F("revenue_amount") + agg["revenue_amount"],
                    "transaction_count": F("transaction_count")
                    + agg["transaction_count"],
                },
            )

    except Exception as e:
        logger.error(f"Real-time aggregation failed for batch: {e}")
        # Don't fail the entire pipeline, just log the error


@shared_task
def run_consistency_check(job_id, transaction_ids, aggregate_config):
    """
    Run final consistency check to ensure aggregates are accurate.
    This corrects any race conditions from real-time aggregation.
    """
    try:
        # Get all transactions for this job
        transactions = FinancialTransaction.objects.filter(id__in=transaction_ids)

        # Recalculate aggregates from scratch
        final_aggregates = transactions.values("date").annotate(
            total_amount=Sum("amount"),
            revenue_amount=Sum("amount", filter=Q(is_revenue=True)),
            transaction_count=Count("id"),
        )

        corrections = 0

        # Update aggregates with final values
        for agg in final_aggregates:
            daily_agg, created = DailyFinancialAggregates.objects.get_or_create(
                date=agg["date"],
                defaults={
                    "total_amount": agg["total_amount"],
                    "revenue_amount": agg["revenue_amount"],
                    "transaction_count": agg["transaction_count"],
                },
            )

            if not created:
                # Check if correction is needed
                if (
                    daily_agg.total_amount != agg["total_amount"]
                    or daily_agg.revenue_amount != agg["revenue_amount"]
                    or daily_agg.transaction_count != agg["transaction_count"]
                ):
                    daily_agg.total_amount = agg["total_amount"]
                    daily_agg.revenue_amount = agg["revenue_amount"]
                    daily_agg.transaction_count = agg["transaction_count"]
                    daily_agg.save()
                    corrections += 1

        return {
            "aggregates": {str(agg["date"]): agg for agg in final_aggregates},
            "corrections": corrections,
        }

    except Exception as e:
        JobStateManager.update_job_state(
            job_id, JobState.FAILED, f"Consistency check failed: {str(e)}"
        )
        raise
