"""
Enhanced mixins with job state tracking.

Provides controlled concurrency and explicit job state management
for bulk operations with aggregate support.
"""

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from django_drf_extensions.enhanced_processing import (
    enhanced_create_task,
    enhanced_upsert_task,
    run_aggregates_task,
)
from django_drf_extensions.job_state import JobStateManager, JobType


class EnhancedOperationsMixin:
    """
    Enhanced operations mixin with job state tracking.

    Provides controlled concurrency and explicit job state management
    for bulk operations, similar to Salesforce Bulk v2.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @action(detail=False, methods=["post"], url_path="bulk/v2")
    def enhanced_bulk_create(self, request):
        """
        Enhanced bulk create with job state tracking.

        Creates a job, processes data asynchronously, and provides
        controlled access for aggregates.
        """
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
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=False, methods=["patch"], url_path="bulk/v2")
    def enhanced_bulk_upsert(self, request):
        """
        Enhanced bulk upsert with job state tracking.

        Creates a job, processes data asynchronously, and provides
        controlled access for aggregates.
        """
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

        # Get unique fields parameter
        unique_fields_param = request.query_params.get("unique_fields")
        if not unique_fields_param:
            return Response(
                {"error": "unique_fields parameter is required for upsert operations"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        unique_fields = [f.strip() for f in unique_fields_param.split(",") if f.strip()]
        update_fields_param = request.query_params.get("update_fields")
        update_fields = None
        if update_fields_param:
            update_fields = [
                f.strip() for f in update_fields_param.split(",") if f.strip()
            ]

        # Create job
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
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=False, methods=["post"], url_path="bulk/v2/aggregates")
    def run_job_aggregates(self, request):
        """
        Run aggregates on a completed job.

        This endpoint allows running aggregates on the data that was
        processed by a bulk job, providing controlled access to the results.
        """
        job_id = request.data.get("job_id")
        aggregate_config = request.data.get("aggregates", {})

        if not job_id:
            return Response(
                {"error": "job_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not aggregate_config:
            return Response(
                {"error": "aggregates configuration is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if job exists and is ready for aggregates
        job = JobStateManager.get_job(job_id)
        if not job:
            return Response(
                {"error": "Job not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not job.aggregates_ready:
            return Response(
                {"error": "Job not ready for aggregates", "state": job.state.value},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if job.aggregates_completed:
            return Response(
                {
                    "message": "Aggregates already completed",
                    "results": job.aggregate_results,
                },
                status=status.HTTP_200_OK,
            )

        # Start aggregate task
        task = run_aggregates_task.delay(job_id, aggregate_config)

        return Response(
            {
                "message": "Aggregates task started",
                "job_id": job_id,
                "task_id": task.id,
                "status_url": f"/api/jobs/{job_id}/status/",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class JobStatusView:
    """
    View for checking job status and results.
    """

    def get_job_status(self, request, job_id):
        """Get job status and results."""
        summary = JobStateManager.get_job_summary(job_id)

        if "error" in summary:
            return Response(summary, status=status.HTTP_404_NOT_FOUND)

        return Response(summary, status=status.HTTP_200_OK)

    def get_job_aggregates(self, request, job_id):
        """Get job aggregate results."""
        job = JobStateManager.get_job(job_id)

        if not job:
            return Response(
                {"error": "Job not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not job.aggregates_ready:
            return Response(
                {"error": "Job not ready for aggregates", "state": job.state.value},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not job.aggregates_completed:
            return Response(
                {"error": "Aggregates not completed yet", "state": job.state.value},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "job_id": job_id,
                "aggregate_results": job.aggregate_results,
            },
            status=status.HTTP_200_OK,
        )
