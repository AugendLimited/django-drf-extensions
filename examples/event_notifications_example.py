"""
Event Notification Examples - Alternatives to Polling

This example demonstrates multiple open standard event mechanisms as alternatives
to polling for job status updates:

1. Server-Sent Events (SSE) - Real-time streaming updates
2. Webhooks - HTTP POST notifications to external endpoints
3. WebSocket notifications - Real-time bidirectional communication
4. Message queue integration - For enterprise event streaming

Usage:
    python examples/event_notifications_example.py
"""

import asyncio
import json
import threading
import time
from typing import Any, Dict, List
from urllib.parse import urljoin

import requests
import websockets

# Example configuration
BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api/transactions"


class EventNotificationExamples:
    """Demonstrates various event notification mechanisms."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {"Content-Type": "application/json", "Accept": "application/json"}
        )

    def example_1_server_sent_events(self):
        """
        Example 1: Server-Sent Events (SSE)

        SSE provides real-time streaming updates without polling.
        Perfect for web applications that need live progress updates.
        """
        print("\n=== Example 1: Server-Sent Events (SSE) ===")

        # Step 1: Start a bulk operation
        bulk_data = [
            {"account": "ACC001", "amount": 100.00, "description": "Payment 1"},
            {"account": "ACC002", "amount": 250.50, "description": "Payment 2"},
            {"account": "ACC003", "amount": 75.25, "description": "Payment 3"},
        ]

        print("Starting bulk operation...")
        response = self.session.post(f"{API_BASE}/bulk/", json=bulk_data)

        if response.status_code == 202:
            result = response.json()
            job_id = result["job_id"]
            events_url = f"{API_BASE}/jobs/{job_id}/events/"

            print(f"Job started: {job_id}")
            print(f"Events URL: {events_url}")

            # Step 2: Connect to SSE stream
            print("\nConnecting to SSE stream...")
            self._connect_to_sse(events_url)
        else:
            print(f"Failed to start bulk operation: {response.text}")

    def _connect_to_sse(self, events_url: str):
        """
        Connect to Server-Sent Events stream.

        In a real application, you would use the browser's EventSource API:

        ```javascript
        const eventSource = new EventSource('/api/transactions/jobs/abc123/events/');

        eventSource.onopen = () => {
            console.log('SSE connection established');
        };

        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log('Job update:', data);

            if (data.state === 'completed') {
                eventSource.close();
            }
        };

        eventSource.onerror = (error) => {
            console.error('SSE error:', error);
            eventSource.close();
        };
        ```
        """
        try:
            # Simulate SSE connection with requests
            response = self.session.get(
                events_url, headers={"Accept": "text/event-stream"}, stream=True
            )

            print("SSE stream connected. Receiving events...")
            for line in response.iter_lines():
                if line:
                    line_str = line.decode("utf-8")
                    if line_str.startswith("data: "):
                        data = json.loads(line_str[6:])  # Remove 'data: ' prefix
                        print(f"SSE Event: {data}")

                        # Check if job is complete
                        if data.get("state") in ["completed", "failed", "aborted"]:
                            print("Job completed via SSE!")
                            break

        except Exception as e:
            print(f"SSE connection error: {e}")

    def example_2_webhooks(self):
        """
        Example 2: Webhooks

        Webhooks send HTTP POST notifications to external endpoints.
        Perfect for server-to-server communication and integrations.
        """
        print("\n=== Example 2: Webhooks ===")

        # Step 1: Register a webhook
        webhook_data = {
            "webhook_url": "https://your-app.com/webhooks/job-updates",
            "event_types": ["job_completed", "job_failed", "job_started"],
            "headers": {
                "Authorization": "Bearer your-secret-token",
                "X-Custom-Header": "custom-value",
            },
        }

        print("Registering webhook...")
        response = self.session.post(
            f"{API_BASE}/jobs/webhooks/register/", json=webhook_data
        )

        if response.status_code == 201:
            webhook_info = response.json()
            webhook_id = webhook_info["webhook_id"]
            print(f"Webhook registered: {webhook_id}")

            # Step 2: List registered webhooks
            print("\nListing registered webhooks...")
            response = self.session.get(f"{API_BASE}/jobs/webhooks/list/")
            if response.status_code == 200:
                webhooks = response.json()
                print(f"Registered webhooks: {webhooks}")

            # Step 3: Start a bulk operation (webhook will be triggered)
            bulk_data = [
                {
                    "account": "ACC004",
                    "amount": 300.00,
                    "description": "Webhook test 1",
                },
                {
                    "account": "ACC005",
                    "amount": 150.75,
                    "description": "Webhook test 2",
                },
            ]

            print("\nStarting bulk operation (webhook will be triggered)...")
            response = self.session.post(f"{API_BASE}/bulk/", json=bulk_data)

            if response.status_code == 202:
                result = response.json()
                job_id = result["job_id"]
                print(f"Job started: {job_id}")
                print("Webhook notifications will be sent to your endpoint!")

                # In a real scenario, your webhook endpoint would receive:
                webhook_payload_example = {
                    "event_type": "job_started",
                    "job_id": job_id,
                    "timestamp": "2024-01-15T10:30:00Z",
                    "data": {
                        "state": "in_progress",
                        "processed_items": 0,
                        "total_items": 2,
                        "percentage": 0.0,
                    },
                }
                print(f"\nExample webhook payload your endpoint would receive:")
                print(json.dumps(webhook_payload_example, indent=2))
        else:
            print(f"Failed to register webhook: {response.text}")

    def example_3_websockets(self):
        """
        Example 3: WebSocket Notifications

        WebSockets provide real-time bidirectional communication.
        Perfect for interactive applications and real-time dashboards.
        """
        print("\n=== Example 3: WebSocket Notifications ===")

        # Note: This requires Django Channels setup
        print("WebSocket notifications require Django Channels setup.")
        print(
            "The system automatically sends WebSocket notifications when jobs update."
        )

        # Example WebSocket consumer code:
        websocket_consumer_example = """
        # consumers.py
        import json
        from channels.generic.websocket import AsyncWebsocketConsumer
        
        class BulkJobConsumer(AsyncWebsocketConsumer):
            async def connect(self):
                self.job_id = self.scope['url_route']['kwargs']['job_id']
                self.room_group_name = f'bulk_jobs:{self.job_id}'
                
                await self.channel_layer.group_add(
                    self.room_group_name,
                    self.channel_name
                )
                await self.accept()
            
            async def disconnect(self, close_code):
                await self.channel_layer.group_discard(
                    self.room_group_name,
                    self.channel_name
                )
            
            async def bulk_job_notification(self, event):
                # Send notification to WebSocket
                await self.send(text_data=json.dumps({
                    'job_id': event['job_id'],
                    'event_type': event['event_type'],
                    'data': event['data'],
                    'timestamp': event['timestamp']
                }))
        """

        print("\nExample WebSocket consumer code:")
        print(websocket_consumer_example)

        # Example JavaScript client code:
        js_client_example = """
        // JavaScript WebSocket client
        const ws = new WebSocket('ws://localhost:8000/ws/jobs/abc123/');
        
        ws.onopen = () => {
            console.log('WebSocket connected');
        };
        
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log('WebSocket notification:', data);
            
            if (data.event_type === 'job_completed') {
                console.log('Job completed via WebSocket!');
                ws.close();
            }
        };
        
        ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
        """

        print("\nExample JavaScript client code:")
        print(js_client_example)

    def example_4_message_queues(self):
        """
        Example 4: Message Queue Integration

        Message queues provide reliable event streaming for enterprise applications.
        Perfect for microservices and event-driven architectures.
        """
        print("\n=== Example 4: Message Queue Integration ===")

        print("The system automatically publishes events to Redis message queues.")
        print("You can consume these events with any message queue client.")

        # Example Redis consumer:
        redis_consumer_example = """
        # redis_consumer.py
        import redis
        import json
        import time
        
        # Connect to Redis
        r = redis.Redis(host='localhost', port=6379, db=0)
        
        def consume_bulk_job_events():
            queue_name = 'bulk_job_events'
            
            while True:
                # Pop message from queue
                message = r.brpop(queue_name, timeout=1)
                
                if message:
                    _, message_data = message
                    event = json.loads(message_data)
                    
                    print(f"Received event: {event['event_type']}")
                    print(f"Job ID: {event['job_id']}")
                    print(f"Data: {event['data']}")
                    
                    # Process the event
                    if event['event_type'] == 'job_completed':
                        print("Job completed! Processing results...")
                        # Your business logic here
                
                time.sleep(0.1)  # Small delay to prevent busy waiting
        
        if __name__ == '__main__':
            consume_bulk_job_events()
        """

        print("\nExample Redis consumer code:")
        print(redis_consumer_example)

        # Example event structure:
        event_structure = {
            "job_id": "abc123",
            "event_type": "job_completed",
            "data": {
                "state": "completed",
                "processed_items": 1000,
                "total_items": 1000,
                "success_count": 995,
                "error_count": 5,
                "percentage": 100.0,
                "created_ids": [1, 2, 3, 4, 5],
                "errors": [
                    {"index": 10, "error": "Validation failed"},
                    {"index": 25, "error": "Duplicate record"},
                ],
            },
            "timestamp": "2024-01-15T10:35:00Z",
            "source": "django-drf-extensions",
        }

        print("\nExample event structure:")
        print(json.dumps(event_structure, indent=2))

    def example_5_comparison_and_best_practices(self):
        """
        Example 5: Comparison and Best Practices

        When to use each notification method:
        """
        print("\n=== Example 5: Comparison and Best Practices ===")

        comparison = {
            "Server-Sent Events (SSE)": {
                "best_for": "Web applications needing real-time updates",
                "pros": [
                    "Simple to implement",
                    "Automatic reconnection",
                    "Works through firewalls",
                    "Low overhead",
                ],
                "cons": [
                    "Unidirectional (server to client only)",
                    "Limited browser support for older browsers",
                ],
                "use_case": "Progress bars, live dashboards, real-time notifications",
            },
            "Webhooks": {
                "best_for": "Server-to-server communication",
                "pros": [
                    "Reliable delivery with retries",
                    "Works with any HTTP endpoint",
                    "No persistent connections needed",
                    "Great for integrations",
                ],
                "cons": [
                    "Requires public endpoint",
                    "Need to handle delivery failures",
                    "Security considerations",
                ],
                "use_case": "Third-party integrations, microservices, external systems",
            },
            "WebSockets": {
                "best_for": "Interactive applications",
                "pros": [
                    "Bidirectional communication",
                    "Real-time updates",
                    "Low latency",
                    "Full-duplex",
                ],
                "cons": [
                    "More complex to implement",
                    "Connection management",
                    "Scaling challenges",
                ],
                "use_case": "Chat applications, collaborative tools, real-time dashboards",
            },
            "Message Queues": {
                "best_for": "Enterprise and microservices",
                "pros": [
                    "Reliable delivery",
                    "Decoupling of systems",
                    "Scalable",
                    "Event sourcing support",
                ],
                "cons": [
                    "More complex infrastructure",
                    "Additional dependencies",
                    "Learning curve",
                ],
                "use_case": "Microservices, event-driven architectures, data pipelines",
            },
        }

        print("Notification Method Comparison:")
        for method, details in comparison.items():
            print(f"\n{method}:")
            print(f"  Best for: {details['best_for']}")
            print(f"  Pros: {', '.join(details['pros'])}")
            print(f"  Cons: {', '.join(details['cons'])}")
            print(f"  Use case: {details['use_case']}")

        print("\n" + "=" * 50)
        print("RECOMMENDATIONS:")
        print("1. Use SSE for simple web applications")
        print("2. Use Webhooks for integrations and external systems")
        print("3. Use WebSockets for interactive applications")
        print("4. Use Message Queues for enterprise/microservices")
        print("5. You can use multiple methods simultaneously!")
        print("=" * 50)


def run_examples():
    """Run all event notification examples."""
    examples = EventNotificationExamples()

    print("Event Notification Examples - Alternatives to Polling")
    print("=" * 60)

    try:
        # Run examples
        examples.example_1_server_sent_events()
        examples.example_2_webhooks()
        examples.example_3_websockets()
        examples.example_4_message_queues()
        examples.example_5_comparison_and_best_practices()

    except requests.exceptions.ConnectionError:
        print("\nERROR: Could not connect to the API server.")
        print("Please make sure your Django server is running on http://localhost:8000")
        print("You can still review the examples and code snippets above.")

    except Exception as e:
        print(f"\nERROR: {e}")
        print(
            "Some examples may have failed, but you can still review the code snippets."
        )


if __name__ == "__main__":
    run_examples()
