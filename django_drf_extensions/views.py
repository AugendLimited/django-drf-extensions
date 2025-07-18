"""
Views for operation status tracking.
"""
from celery.result import AsyncResult
from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from django_drf_extensions.cache import OperationCache


class OperationStatusView(APIView):
    """
    API view to check the status of async operations.
    """

    def get(self, request, task_id):
        """
        Get the status and results of an async operation task.

        Args:
            task_id: The Celery task ID

        Returns:
            Task status, results, and progress information
        """
        try:
            task_result = AsyncResult(task_id)
        except (ValueError, TypeError) as exc:
            msg = "Task not found"
            raise Http404(msg) from exc

        # Try to get cached progress first
        progress_data = OperationCache.get_task_progress(task_id)
        cached_result = OperationCache.get_task_result(task_id)

        # Determine task state
        task_state = task_result.state
        
        response_data = {
            "task_id": task_id,
            "state": task_state,
        }

        if task_state == "PENDING":
            # Task is waiting to be processed
            response_data.update({
                "status": "pending",
                "message": "Task is waiting to be processed",
                "progress": progress_data or {"current": 0, "total": 0, "percentage": 0},
            })
        
        elif task_state == "PROGRESS":
            # Task is currently being processed
            response_data.update({
                "status": "in_progress",
                "message": "Task is being processed",
                "progress": progress_data or {"current": 0, "total": 0, "percentage": 0},
            })
        
        elif task_state == "SUCCESS":
            # Task completed successfully
            if cached_result:
                # Use cached result for better performance
                result_data = cached_result
            else:
                # Fall back to Celery result
                result_data = task_result.result or {}
            
            response_data.update({
                "status": "completed",
                "message": "Task completed successfully",
                "result": result_data,
                "progress": progress_data or {"current": 100, "total": 100, "percentage": 100},
            })
        
        elif task_state == "FAILURE":
            # Task failed
            error_info = str(task_result.info) if task_result.info else "Unknown error"
            response_data.update({
                "status": "failed",
                "message": "Task failed",
                "error": error_info,
                "progress": progress_data,
            })
        
        elif task_state == "RETRY":
            # Task is being retried
            response_data.update({
                "status": "retrying",
                "message": "Task is being retried",
                "progress": progress_data,
            })
        
        elif task_state == "REVOKED":
            # Task was cancelled/revoked
            response_data.update({
                "status": "cancelled",
                "message": "Task was cancelled",
                "progress": progress_data,
            })
        
        else:
            # Unknown state
            response_data.update({
                "status": "unknown",
                "message": f"Task in unknown state: {task_state}",
                "progress": progress_data,
            })

        return Response(response_data, status=status.HTTP_200_OK)

    def delete(self, request, task_id):
        """
        Cancel a running task and clean up its cached data.

        Args:
            task_id: The Celery task ID

        Returns:
            Cancellation confirmation
        """
        try:
            task_result = AsyncResult(task_id)
            
            # Revoke the task if it's still running
            if task_result.state in ["PENDING", "PROGRESS", "RETRY"]:
                task_result.revoke(terminate=True)
                message = "Task cancelled successfully"
            else:
                message = f"Task was already in state: {task_result.state}"
            
            # Clean up cached data
            OperationCache.delete_task_data(task_id)
            
            return Response({
                "task_id": task_id,
                "message": message,
                "cancelled": True,
            }, status=status.HTTP_200_OK)
            
        except (ValueError, TypeError) as exc:
            return Response({
                "error": "Task not found",
                "task_id": task_id,
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                "error": f"Failed to cancel task: {str(e)}",
                "task_id": task_id,
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR) 