"""
Job state tracking system for bulk operations.

Inspired by Salesforce Bulk v2 API, this provides explicit job states
and controlled concurrency for bulk operations.
"""

import enum
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


class JobState(enum.Enum):
    """Job states for bulk operations."""

    # Initial state - job created but not started
    OPEN = "Open"

    # Job is being processed
    UPLOAD_COMPLETE = "Upload Complete"
    IN_PROGRESS = "In Progress"

    # Job completed successfully
    JOB_COMPLETE = "Job Complete"

    # Job failed
    FAILED = "Failed"

    # Job was aborted
    ABORTED = "Aborted"


class JobType(enum.Enum):
    """Types of bulk operations."""

    INSERT = "insert"
    UPDATE = "update"
    UPSERT = "upsert"
    DELETE = "delete"
    REPLACE = "replace"


class BulkJob:
    """
    Represents a bulk operation job with state tracking.

    Provides controlled concurrency and explicit state management
    for bulk operations, similar to Salesforce Bulk v2.
    """

    def __init__(
        self,
        job_id: str,
        job_type: JobType,
        model_class_path: str,
        serializer_class_path: Optional[str] = None,
        user_id: Optional[int] = None,
        total_items: int = 0,
        unique_fields: Optional[List[str]] = None,
        update_fields: Optional[List[str]] = None,
    ):
        self.job_id = job_id
        self.job_type = job_type
        self.model_class_path = model_class_path
        self.serializer_class_path = serializer_class_path
        self.user_id = user_id
        self.total_items = total_items
        self.unique_fields = unique_fields or []
        self.update_fields = update_fields or []

        # State tracking
        self.state = JobState.OPEN
        self.created_at = timezone.now()
        self.updated_at = timezone.now()
        self.completed_at: Optional[datetime] = None

        # Progress tracking
        self.processed_items = 0
        self.success_count = 0
        self.error_count = 0
        self.errors: List[Dict[str, Any]] = []
        self.created_ids: List[int] = []
        self.updated_ids: List[int] = []
        self.deleted_ids: List[int] = []

        # Concurrency control
        self.locked = False
        self.lock_expires_at: Optional[datetime] = None

        # Aggregate tracking
        self.aggregates_ready = False
        self.aggregates_completed = False
        self.aggregate_results: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert job to dictionary for serialization."""
        return {
            "job_id": self.job_id,
            "job_type": self.job_type.value,
            "model_class_path": self.model_class_path,
            "serializer_class_path": self.serializer_class_path,
            "user_id": self.user_id,
            "total_items": self.total_items,
            "unique_fields": self.unique_fields,
            "update_fields": self.update_fields,
            "state": self.state.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "processed_items": self.processed_items,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "errors": self.errors,
            "created_ids": self.created_ids,
            "updated_ids": self.updated_ids,
            "deleted_ids": self.deleted_ids,
            "locked": self.locked,
            "lock_expires_at": self.lock_expires_at.isoformat()
            if self.lock_expires_at
            else None,
            "aggregates_ready": self.aggregates_ready,
            "aggregates_completed": self.aggregates_completed,
            "aggregate_results": self.aggregate_results,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BulkJob":
        """Create job from dictionary."""
        job = cls(
            job_id=data["job_id"],
            job_type=JobType(data["job_type"]),
            model_class_path=data["model_class_path"],
            serializer_class_path=data.get("serializer_class_path"),
            user_id=data.get("user_id"),
            total_items=data.get("total_items", 0),
            unique_fields=data.get("unique_fields", []),
            update_fields=data.get("update_fields", []),
        )

        # Restore state
        job.state = JobState(data["state"])
        job.created_at = datetime.fromisoformat(data["created_at"])
        job.updated_at = datetime.fromisoformat(data["updated_at"])
        if data.get("completed_at"):
            job.completed_at = datetime.fromisoformat(data["completed_at"])

        # Restore progress
        job.processed_items = data.get("processed_items", 0)
        job.success_count = data.get("success_count", 0)
        job.error_count = data.get("error_count", 0)
        job.errors = data.get("errors", [])
        job.created_ids = data.get("created_ids", [])
        job.updated_ids = data.get("updated_ids", [])
        job.deleted_ids = data.get("deleted_ids", [])

        # Restore concurrency state
        job.locked = data.get("locked", False)
        if data.get("lock_expires_at"):
            job.lock_expires_at = datetime.fromisoformat(data["lock_expires_at"])

        # Restore aggregate state
        job.aggregates_ready = data.get("aggregates_ready", False)
        job.aggregates_completed = data.get("aggregates_completed", False)
        job.aggregate_results = data.get("aggregate_results", {})

        return job


class JobStateManager:
    """
    Manages job states and provides controlled concurrency.
    """

    CACHE_PREFIX = "bulk_job:"
    LOCK_TIMEOUT = 300  # 5 minutes
    JOB_TIMEOUT = 3600  # 1 hour

    @classmethod
    def _get_cache_key(cls, job_id: str) -> str:
        """Get cache key for job."""
        return f"{cls.CACHE_PREFIX}{job_id}"

    @classmethod
    def create_job(
        cls,
        job_type: JobType,
        model_class_path: str,
        serializer_class_path: Optional[str] = None,
        user_id: Optional[int] = None,
        total_items: int = 0,
        unique_fields: Optional[List[str]] = None,
        update_fields: Optional[List[str]] = None,
    ) -> BulkJob:
        """Create a new bulk job."""
        job_id = str(uuid4())
        job = BulkJob(
            job_id=job_id,
            job_type=job_type,
            model_class_path=model_class_path,
            serializer_class_path=serializer_class_path,
            user_id=user_id,
            total_items=total_items,
            unique_fields=unique_fields or [],
            update_fields=update_fields or [],
        )

        cls._save_job(job)
        logger.info("Created bulk job %s of type %s", job_id, job_type.value)
        return job

    @classmethod
    def get_job(cls, job_id: str) -> Optional[BulkJob]:
        """Get job by ID."""
        cache_key = cls._get_cache_key(job_id)
        job_data = cache.get(cache_key)

        if job_data:
            return BulkJob.from_dict(job_data)
        return None

    @classmethod
    def _save_job(cls, job: BulkJob) -> None:
        """Save job to cache."""
        cache_key = cls._get_cache_key(job.job_id)
        cache.set(cache_key, job.to_dict(), timeout=cls.JOB_TIMEOUT)

    @classmethod
    def update_job_state(
        cls, job_id: str, state: JobState, **kwargs
    ) -> Optional[BulkJob]:
        """Update job state and optional progress."""
        job = cls.get_job(job_id)
        if not job:
            return None

        job.state = state
        job.updated_at = timezone.now()

        # Update optional progress fields
        for key, value in kwargs.items():
            if hasattr(job, key):
                setattr(job, key, value)

        # Set completion time if job is finished
        if state in [JobState.JOB_COMPLETE, JobState.FAILED, JobState.ABORTED]:
            job.completed_at = timezone.now()
            job.aggregates_ready = True  # Allow aggregates to run

        cls._save_job(job)
        logger.info("Updated job %s state to %s", job_id, state.value)
        return job

    @classmethod
    def acquire_lock(cls, job_id: str, timeout: int = None) -> bool:
        """Acquire lock for job processing."""
        job = cls.get_job(job_id)
        if not job:
            return False

        # Check if already locked
        if job.locked and job.lock_expires_at and job.lock_expires_at > timezone.now():
            return False

        # Acquire lock
        job.locked = True
        job.lock_expires_at = timezone.now() + timedelta(
            seconds=timeout or cls.LOCK_TIMEOUT
        )
        cls._save_job(job)

        logger.info("Acquired lock for job %s", job_id)
        return True

    @classmethod
    def release_lock(cls, job_id: str) -> None:
        """Release lock for job."""
        job = cls.get_job(job_id)
        if job:
            job.locked = False
            job.lock_expires_at = None
            cls._save_job(job)
            logger.info("Released lock for job %s", job_id)

    @classmethod
    def get_jobs_by_state(cls, state: JobState) -> List[BulkJob]:
        """Get all jobs with a specific state."""
        # This would need a more sophisticated implementation with a job index
        # For now, we'll return empty list - you might want to use a database table
        # for job indexing in production
        return []

    @classmethod
    def cleanup_expired_jobs(cls) -> int:
        """Clean up expired jobs and locks."""
        # This would need implementation with job indexing
        # For now, we rely on cache TTL
        return 0

    @classmethod
    def get_job_summary(cls, job_id: str) -> Dict[str, Any]:
        """Get job summary for API responses."""
        job = cls.get_job(job_id)
        if not job:
            return {"error": "Job not found"}

        # Calculate progress percentage
        percentage = round((job.processed_items / job.total_items) * 100, 2) if job.total_items > 0 else 0
        
        # Estimate remaining time based on processing rate
        estimated_remaining = None
        if job.state == JobState.IN_PROGRESS and job.processed_items > 0:
            # Rough estimate: 100 items per second
            items_per_second = 100
            remaining_items = job.total_items - job.processed_items
            estimated_seconds = remaining_items / items_per_second
            estimated_remaining = f"{int(estimated_seconds)} seconds"

        # Determine status message and next steps
        status_info = cls._get_status_info(job, percentage, estimated_remaining)

        return {
            "job_id": job.job_id,
            "job_type": job.job_type.value,
            "state": job.state.value,
            "status": status_info["status"],
            "message": status_info["message"],
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "total_items": job.total_items,
            "processed_items": job.processed_items,
            "success_count": job.success_count,
            "error_count": job.error_count,
            "percentage": percentage,
            "estimated_remaining": estimated_remaining,
            "aggregates_ready": job.aggregates_ready,
            "aggregates_completed": job.aggregates_completed,
            "next_steps": status_info["next_steps"],
            "can_retry": job.state in [JobState.FAILED, JobState.ABORTED],
            "errors": getattr(job, 'errors', []) if job.state == JobState.FAILED else None,
        }

    @classmethod
    def _get_status_info(cls, job: "BulkJob", percentage: float, estimated_remaining: Optional[str]) -> Dict[str, Any]:
        """Get human-readable status information."""
        if job.state == JobState.OPEN:
            return {
                "status": "queued",
                "message": "Job is queued and waiting to start",
                "next_steps": ["Wait for job to begin processing"]
            }
        
        elif job.state == JobState.IN_PROGRESS:
            return {
                "status": "processing",
                "message": f"Processing {job.processed_items} of {job.total_items} items ({percentage}% complete)",
                "next_steps": [
                    f"Continue polling every 10 seconds",
                    f"Estimated completion: {estimated_remaining}" if estimated_remaining else "Processing in progress"
                ]
            }
        
        elif job.state == JobState.JOB_COMPLETE:
            return {
                "status": "completed",
                "message": f"Job completed successfully! Processed {job.success_count} items with {job.error_count} errors",
                "next_steps": [
                    "Check aggregates_url for results",
                    "Review any errors in the response"
                ]
            }
        
        elif job.state == JobState.FAILED:
            return {
                "status": "failed",
                "message": f"Job failed after processing {job.processed_items} items",
                "next_steps": [
                    "Review error details",
                    "Consider retrying with smaller batch size",
                    "Check server logs for more details"
                ]
            }
        
        elif job.state == JobState.ABORTED:
            return {
                "status": "aborted",
                "message": "Job was manually aborted",
                "next_steps": [
                    "Review why job was aborted",
                    "Consider restarting the job"
                ]
            }
        
        else:
            return {
                "status": "unknown",
                "message": f"Job in unknown state: {job.state.value}",
                "next_steps": ["Contact support for assistance"]
            }
