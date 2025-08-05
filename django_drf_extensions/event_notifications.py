"""
Event notification system for bulk operations.

This module provides multiple open standard event mechanisms as alternatives to polling:
1. Webhooks - HTTP POST notifications to configured endpoints
2. Server-Sent Events (SSE) - Real-time streaming updates
3. WebSocket notifications - For real-time bidirectional communication
4. Message queue integration - For enterprise event streaming
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

import redis
import requests
import websockets
from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer
from django.conf import settings
from django.core.cache import cache
from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .job_state import JobState, JobStateManager, JobType

logger = logging.getLogger(__name__)

# Configuration
WEBHOOK_TIMEOUT = getattr(settings, "DRF_EXT_WEBHOOK_TIMEOUT", 10)
WEBHOOK_MAX_RETRIES = getattr(settings, "DRF_EXT_WEBHOOK_MAX_RETRIES", 3)
SSE_RETRY_INTERVAL = getattr(settings, "DRF_EXT_SSE_RETRY_INTERVAL", 5000)
WEBSOCKET_GROUP_PREFIX = getattr(
    settings, "DRF_EXT_WEBSOCKET_GROUP_PREFIX", "bulk_jobs"
)


class EventNotificationManager:
    """Manages event notifications for bulk operations."""

    @staticmethod
    def send_webhook_notification(
        job_id: str,
        webhook_url: str,
        event_type: str,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> bool:
        """
        Send webhook notification to external endpoint.

        Args:
            job_id: The job ID
            webhook_url: URL to send notification to
            event_type: Type of event (job_started, job_completed, job_failed, etc.)
            payload: Data to send
            headers: Optional headers for the request

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Prepare notification payload
            notification_data = {
                "event_type": event_type,
                "job_id": job_id,
                "timestamp": timezone.now().isoformat(),
                "data": payload,
            }

            # Set default headers
            default_headers = {
                "Content-Type": "application/json",
                "User-Agent": "django-drf-extensions/1.0",
                "X-Event-Type": event_type,
                "X-Job-ID": job_id,
            }

            if headers:
                default_headers.update(headers)

            # Send webhook with retry logic
            for attempt in range(WEBHOOK_MAX_RETRIES):
                try:
                    response = requests.post(
                        webhook_url,
                        json=notification_data,
                        headers=default_headers,
                        timeout=WEBHOOK_TIMEOUT,
                    )

                    if response.status_code in [200, 201, 202]:
                        logger.info(
                            "Webhook notification sent successfully to %s for job %s",
                            webhook_url,
                            job_id,
                        )
                        return True
                    else:
                        logger.warning(
                            "Webhook notification failed with status %d for job %s",
                            response.status_code,
                            job_id,
                        )

                except requests.exceptions.RequestException as e:
                    logger.warning(
                        "Webhook notification attempt %d failed for job %s: %s",
                        attempt + 1,
                        job_id,
                        str(e),
                    )

                    if attempt == WEBHOOK_MAX_RETRIES - 1:
                        logger.error(
                            "All webhook notification attempts failed for job %s",
                            job_id,
                        )
                        return False

        except Exception as e:
            logger.exception("Error sending webhook notification for job %s", job_id)
            return False

        return False

    @staticmethod
    def send_sse_notification(
        job_id: str, event_type: str, data: Dict[str, Any]
    ) -> None:
        """
        Store SSE notification for real-time streaming.

        Args:
            job_id: The job ID
            event_type: Type of event
            data: Event data
        """
        try:
            # Store event in Redis for SSE streaming
            event_key = f"sse:job:{job_id}:{event_type}"
            event_data = {
                "event": event_type,
                "data": json.dumps(data),
                "timestamp": timezone.now().isoformat(),
            }

            # Store in Redis with TTL
            cache.set(event_key, json.dumps(event_data), timeout=3600)  # 1 hour TTL

            # Also store in job events list
            events_key = f"sse:job:{job_id}:events"
            cache.lpush(events_key, json.dumps(event_data))
            cache.expire(events_key, 3600)  # 1 hour TTL

            logger.debug("SSE notification stored for job %s: %s", job_id, event_type)

        except Exception as e:
            logger.exception("Error storing SSE notification for job %s", job_id)

    @staticmethod
    def send_websocket_notification(
        job_id: str,
        event_type: str,
        data: Dict[str, Any],
        user_id: Optional[int] = None,
    ) -> None:
        """
        Send WebSocket notification for real-time updates.

        Args:
            job_id: The job ID
            event_type: Type of event
            data: Event data
            user_id: Optional user ID for targeted notifications
        """
        try:
            # Get channel layer
            channel_layer = get_channel_layer()

            # Prepare notification
            notification = {
                "type": "bulk_job.notification",
                "job_id": job_id,
                "event_type": event_type,
                "data": data,
                "timestamp": timezone.now().isoformat(),
            }

            # Send to job-specific group
            group_name = f"{WEBSOCKET_GROUP_PREFIX}:{job_id}"
            async_to_sync(channel_layer.group_send)(group_name, notification)

            # If user_id provided, also send to user-specific group
            if user_id:
                user_group_name = f"{WEBSOCKET_GROUP_PREFIX}:user:{user_id}"
                async_to_sync(channel_layer.group_send)(user_group_name, notification)

            logger.debug(
                "WebSocket notification sent for job %s: %s", job_id, event_type
            )

        except Exception as e:
            logger.exception("Error sending WebSocket notification for job %s", job_id)

    @staticmethod
    def send_message_queue_notification(
        job_id: str,
        event_type: str,
        data: Dict[str, Any],
        queue_name: str = "bulk_job_events",
    ) -> None:
        """
        Send notification to message queue (Redis/RabbitMQ/Kafka).

        Args:
            job_id: The job ID
            event_type: Type of event
            data: Event data
            queue_name: Name of the queue to send to
        """
        try:
            # Prepare message
            message = {
                "job_id": job_id,
                "event_type": event_type,
                "data": data,
                "timestamp": timezone.now().isoformat(),
                "source": "django-drf-extensions",
            }

            # Use Redis as message queue
            redis_client = redis.Redis.from_url(settings.REDIS_URL)
            redis_client.lpush(queue_name, json.dumps(message))

            logger.debug(
                "Message queue notification sent for job %s: %s", job_id, event_type
            )

        except Exception as e:
            logger.exception(
                "Error sending message queue notification for job %s", job_id
            )


class ServerSentEventsView(APIView):
    """
    Server-Sent Events endpoint for real-time job status updates.

    Usage:
        GET /api/jobs/{job_id}/events/
        Accept: text/event-stream
    """

    def get(self, request, job_id: str):
        """
        Stream job events as Server-Sent Events.

        Args:
            job_id: The job ID to stream events for
        """

        def event_stream():
            """Generate SSE event stream."""
            # Send initial connection event
            yield f"event: connected\ndata: {json.dumps({'job_id': job_id, 'message': 'SSE connection established'})}\n\n"

            # Send current job status
            job_summary = JobStateManager.get_job_summary(job_id)
            if job_summary and "error" not in job_summary:
                yield f"event: status\ndata: {json.dumps(job_summary)}\n\n"

            # Stream real-time updates
            last_event_id = None
            while True:
                try:
                    # Check for new events
                    events_key = f"sse:job:{job_id}:events"
                    events = cache.lrange(events_key, 0, 9)  # Get last 10 events

                    for event_data in reversed(events):
                        event = json.loads(event_data)
                        event_id = f"{job_id}_{event['timestamp']}"

                        if last_event_id != event_id:
                            yield f"id: {event_id}\n"
                            yield f"event: {event['event']}\n"
                            yield f"data: {event['data']}\n\n"
                            last_event_id = event_id

                    # Check if job is complete
                    job = JobStateManager.get_job(job_id)
                    if job and job.state in [
                        JobState.JOB_COMPLETE,
                        JobState.FAILED,
                        JobState.ABORTED,
                    ]:
                        yield f"event: job_complete\ndata: {json.dumps({'job_id': job_id, 'state': job.state.value})}\n\n"
                        break

                    # Keep connection alive
                    yield f": keepalive\n\n"

                except Exception as e:
                    logger.exception("Error in SSE stream for job %s", job_id)
                    yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
                    break

                # Wait before next check
                import time

                time.sleep(2)

        response = StreamingHttpResponse(
            event_stream(), content_type="text/event-stream"
        )
        response["Cache-Control"] = "no-cache"
        response["Connection"] = "keep-alive"
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Headers"] = "Cache-Control"

        return response


class WebhookRegistrationView(APIView):
    """
    Webhook registration and management.

    Usage:
        POST /api/jobs/webhooks/register/
        GET /api/jobs/webhooks/list/
        DELETE /api/jobs/webhooks/{webhook_id}/
    """

    def post(self, request):
        """Register a webhook for job notifications."""
        webhook_url = request.data.get("webhook_url")
        event_types = request.data.get("event_types", ["job_completed", "job_failed"])
        headers = request.data.get("headers", {})

        if not webhook_url:
            return Response(
                {"error": "webhook_url is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Validate URL
        try:
            urlparse(webhook_url)
        except Exception:
            return Response(
                {"error": "Invalid webhook URL"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Store webhook registration
        webhook_id = f"webhook_{timezone.now().timestamp()}"
        webhook_data = {
            "id": webhook_id,
            "url": webhook_url,
            "event_types": event_types,
            "headers": headers,
            "created_at": timezone.now().isoformat(),
            "active": True,
        }

        cache.set(f"webhook:{webhook_id}", webhook_data, timeout=86400 * 30)  # 30 days

        return Response(
            {
                "webhook_id": webhook_id,
                "message": "Webhook registered successfully",
                "webhook_url": webhook_url,
                "event_types": event_types,
            },
            status=status.HTTP_201_CREATED,
        )

    def get(self, request):
        """List registered webhooks."""
        webhook_keys = cache.keys("webhook:*")
        webhooks = []

        for key in webhook_keys:
            webhook_data = cache.get(key)
            if webhook_data:
                webhooks.append(webhook_data)

        return Response({"webhooks": webhooks, "count": len(webhooks)})


@shared_task
def notify_job_event(
    job_id: str,
    event_type: str,
    data: Dict[str, Any],
    notification_methods: List[str] = None,
) -> None:
    """
    Celery task to send job event notifications.

    Args:
        job_id: The job ID
        event_type: Type of event
        data: Event data
        notification_methods: List of notification methods to use
    """
    if notification_methods is None:
        notification_methods = ["sse", "websocket"]

    # Send SSE notification
    if "sse" in notification_methods:
        EventNotificationManager.send_sse_notification(job_id, event_type, data)

    # Send WebSocket notification
    if "websocket" in notification_methods:
        EventNotificationManager.send_websocket_notification(job_id, event_type, data)

    # Send message queue notification
    if "queue" in notification_methods:
        EventNotificationManager.send_message_queue_notification(
            job_id, event_type, data
        )

    # Send webhook notifications
    if "webhook" in notification_methods:
        webhook_keys = cache.keys("webhook:*")
        for key in webhook_keys:
            webhook_data = cache.get(key)
            if webhook_data and webhook_data.get("active"):
                # Check if webhook is subscribed to this event type
                if event_type in webhook_data.get("event_types", []):
                    EventNotificationManager.send_webhook_notification(
                        job_id,
                        webhook_data["url"],
                        event_type,
                        data,
                        webhook_data.get("headers", {}),
                    )


# Integration with existing job state manager
def enhance_job_state_manager_with_notifications():
    """Enhance JobStateManager with event notifications."""

    # Store original methods
    original_update_job_state = JobStateManager.update_job_state

    def enhanced_update_job_state(
        job_id: str,
        state: JobState,
        processed_items: int = 0,
        total_items: int = 0,
        success_count: int = 0,
        error_count: int = 0,
        created_ids: List[int] = None,
        updated_ids: List[int] = None,
        deleted_ids: List[int] = None,
        errors: List[Dict] = None,
        **kwargs,
    ):
        """Enhanced update_job_state with event notifications."""
        # Call original method
        result = original_update_job_state(
            job_id,
            state,
            processed_items,
            total_items,
            success_count,
            error_count,
            created_ids,
            updated_ids,
            deleted_ids,
            errors,
            **kwargs,
        )

        # Determine event type based on state
        event_type_map = {
            JobState.OPEN: "job_created",
            JobState.IN_PROGRESS: "job_started",
            JobState.JOB_COMPLETE: "job_completed",
            JobState.FAILED: "job_failed",
            JobState.ABORTED: "job_aborted",
        }

        event_type = event_type_map.get(state, "job_updated")

        # Prepare notification data
        notification_data = {
            "state": state.value,
            "processed_items": processed_items,
            "total_items": total_items,
            "success_count": success_count,
            "error_count": error_count,
            "percentage": round((processed_items / total_items) * 100, 2)
            if total_items > 0
            else 0,
        }

        # Add IDs if available
        if created_ids:
            notification_data["created_ids"] = created_ids
        if updated_ids:
            notification_data["updated_ids"] = updated_ids
        if deleted_ids:
            notification_data["deleted_ids"] = deleted_ids
        if errors:
            notification_data["errors"] = errors

        # Send notification asynchronously
        notify_job_event.delay(job_id, event_type, notification_data)

        return result

    # Replace the method
    JobStateManager.update_job_state = enhanced_update_job_state


# Auto-enhance when module is imported
enhance_job_state_manager_with_notifications()
