"""
Enhanced Bulk Processing Example

This example demonstrates the new enhanced bulk processing functionality
that is now the default in OperationsMixin. The enhanced system provides:

1. Job state tracking (like Salesforce Bulk v2)
2. Controlled concurrency with locks
3. Aggregate support on processed data
4. Better error handling and progress tracking
5. Dedicated endpoints for job status and aggregates

The enhanced functionality replaces the old /bulk endpoints with
job state tracking while maintaining the same API interface.
"""

import json

import requests
from django.db import models
from rest_framework import serializers
from rest_framework.viewsets import ModelViewSet

from django_drf_extensions.mixins import OperationsMixin


# Example Model
class FinancialTransaction(models.Model):
    account_id = models.IntegerField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_date = models.DateField()
    description = models.CharField(max_length=255)
    category = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "financial_transactions"
        indexes = [
            models.Index(fields=["account_id", "transaction_date"]),
            models.Index(fields=["category"]),
        ]


# Serializer
class FinancialTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinancialTransaction
        fields = "__all__"


# ViewSet with Enhanced Operations (now the default)
class FinancialTransactionViewSet(OperationsMixin, ModelViewSet):
    """
    Enhanced Financial Transaction ViewSet.

    This now uses the enhanced bulk processing by default, which provides:
    - Job state tracking
    - Controlled concurrency
    - Aggregate support
    - Better error handling
    """

    queryset = FinancialTransaction.objects.all()
    serializer_class = FinancialTransactionSerializer


# Example usage functions
def example_enhanced_bulk_create():
    """
    Example: Enhanced bulk create with job state tracking
    """
    print("=== Enhanced Bulk Create Example ===")

    # Sample data
    transactions = [
        {
            "account_id": 1001,
            "amount": "1500.00",
            "transaction_date": "2024-01-15",
            "description": "Salary deposit",
            "category": "income",
        },
        {
            "account_id": 1001,
            "amount": "-250.00",
            "transaction_date": "2024-01-16",
            "description": "Rent payment",
            "category": "housing",
        },
        {
            "account_id": 1002,
            "amount": "750.00",
            "transaction_date": "2024-01-15",
            "description": "Freelance payment",
            "category": "income",
        },
    ]

    # Make the request
    response = requests.post(
        "http://localhost:8000/api/transactions/bulk/",
        json=transactions,
        headers={"Content-Type": "application/json"},
    )

    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

    if response.status_code == 202:
        data = response.json()
        job_id = data["job_id"]

        # Check job status
        print(f"\nChecking job status for {job_id}...")
        status_response = requests.get(
            f"http://localhost:8000/api/transactions/jobs/{job_id}/status/"
        )
        print(f"Status: {json.dumps(status_response.json(), indent=2)}")

        # Run aggregates when job is complete
        if status_response.json().get("state") == "JOB_COMPLETE":
            print(f"\nRunning aggregates for job {job_id}...")
            aggregate_config = {
                "total_amount": {"type": "sum", "field": "amount"},
                "transaction_count": {"type": "count"},
                "avg_amount": {"type": "avg", "field": "amount"},
                "by_category": {
                    "type": "group",
                    "field": "category",
                    "aggregate": "sum",
                    "target": "amount",
                },
            }

            aggregate_response = requests.post(
                "http://localhost:8000/api/transactions/jobs/aggregates/",
                json={"job_id": job_id, "aggregate_config": aggregate_config},
            )
            print(
                f"Aggregate Response: {json.dumps(aggregate_response.json(), indent=2)}"
            )


def example_enhanced_bulk_upsert():
    """
    Example: Enhanced bulk upsert with job state tracking
    """
    print("\n=== Enhanced Bulk Upsert Example ===")

    # Sample data with unique fields
    transactions = [
        {
            "account_id": 1001,
            "transaction_date": "2024-01-15",
            "amount": "1600.00",  # Updated amount
            "description": "Salary deposit (updated)",
            "category": "income",
        },
        {
            "account_id": 1003,
            "transaction_date": "2024-01-17",
            "amount": "-100.00",
            "description": "Grocery shopping",
            "category": "food",
        },
    ]

    # Make the request with unique_fields parameter
    response = requests.patch(
        "http://localhost:8000/api/transactions/bulk/?unique_fields=account_id,transaction_date",
        json=transactions,
        headers={"Content-Type": "application/json"},
    )

    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

    if response.status_code == 202:
        data = response.json()
        job_id = data["job_id"]

        # Check job status
        print(f"\nChecking job status for {job_id}...")
        status_response = requests.get(
            f"http://localhost:8000/api/transactions/jobs/{job_id}/status/"
        )
        print(f"Status: {json.dumps(status_response.json(), indent=2)}")


def example_run_aggregates():
    """
    Example: Running aggregates on completed jobs
    """
    print("\n=== Running Aggregates Example ===")

    # Example job ID (you would get this from a previous bulk operation)
    job_id = "example-job-id"

    # Define aggregate configuration
    aggregate_config = {
        "total_amount": {"type": "sum", "field": "amount"},
        "transaction_count": {"type": "count"},
        "avg_amount": {"type": "avg", "field": "amount"},
        "by_category": {
            "type": "group",
            "field": "category",
            "aggregate": "sum",
            "target": "amount",
        },
        "custom_metric": {
            "type": "custom",
            "query": "SELECT category, COUNT(*) as count, SUM(amount) as total FROM financial_transactions WHERE id IN ({ids}) GROUP BY category",
        },
    }

    # Run aggregates
    response = requests.post(
        "http://localhost:8000/api/transactions/jobs/aggregates/",
        json={"job_id": job_id, "aggregate_config": aggregate_config},
    )

    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")


def example_check_job_status():
    """
    Example: Checking job status
    """
    print("\n=== Job Status Check Example ===")

    job_id = "example-job-id"

    response = requests.get(
        f"http://localhost:8000/api/transactions/jobs/{job_id}/status/"
    )

    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")


def example_get_aggregate_results():
    """
    Example: Getting aggregate results
    """
    print("\n=== Get Aggregate Results Example ===")

    job_id = "example-job-id"

    response = requests.get(
        f"http://localhost:8000/api/transactions/jobs/{job_id}/aggregates/"
    )

    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")


def comparison_with_old_system():
    """
    Comparison between old and new system
    """
    print("\n=== System Comparison ===")

    comparison = {
        "Old System": {
            "endpoints": ["/bulk/"],
            "state_tracking": "Basic Redis cache",
            "concurrency": "Uncontrolled",
            "aggregates": "Not supported",
            "error_handling": "Basic",
            "progress_tracking": "Every 10 items",
            "status_urls": "/api/operations/{task_id}/status/",
        },
        "New Enhanced System": {
            "endpoints": [
                "/bulk/ (enhanced)",
                "/jobs/{job_id}/status/",
                "/jobs/{job_id}/aggregates/",
                "/jobs/aggregates/",
            ],
            "state_tracking": "Job state management (Salesforce Bulk v2 style)",
            "concurrency": "Controlled with locks",
            "aggregates": "Full support with custom queries",
            "error_handling": "Enhanced with job state",
            "progress_tracking": "Real-time with job state",
            "status_urls": "/api/jobs/{job_id}/status/",
        },
    }

    print("Feature Comparison:")
    for system, features in comparison.items():
        print(f"\n{system}:")
        for feature, description in features.items():
            print(f"  {feature}: {description}")


def example_best_practices_for_callers():
    """
    Best practices for callers to understand and monitor bulk operations.

    This example shows the recommended approach for:
    1. Starting bulk operations
    2. Monitoring progress with intelligent polling
    3. Handling different job states
    4. Retrieving results and aggregates
    5. Error handling and retry strategies
    """

    import json
    import time
    from typing import Any, Dict, Optional

    import requests

    class BulkOperationMonitor:
        """Helper class for monitoring bulk operations with best practices."""

        def __init__(self, base_url: str):
            self.base_url = base_url
            self.session = requests.Session()

        def start_bulk_create(self, data: list) -> Dict[str, Any]:
            """Start a bulk create operation and return job info."""
            response = self.session.post(
                f"{self.base_url}/api/transactions/bulk/",
                json=data,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            return response.json()

        def poll_job_status(
            self, job_id: str, max_wait_time: int = 300
        ) -> Dict[str, Any]:
            """
            Poll job status with intelligent backoff and timeout.

            Args:
                job_id: The job ID to monitor
                max_wait_time: Maximum time to wait in seconds (default: 5 minutes)

            Returns:
                Final job status when complete or failed
            """
            start_time = time.time()
            poll_interval = 2  # Start with 2 seconds

            while True:
                # Check if we've exceeded max wait time
                if time.time() - start_time > max_wait_time:
                    raise TimeoutError(
                        f"Job {job_id} did not complete within {max_wait_time} seconds"
                    )

                # Get current status
                status_response = self.session.get(
                    f"{self.base_url}/api/transactions/jobs/{job_id}/status/"
                )
                status_response.raise_for_status()
                status_data = status_response.json()

                # Print progress information
                self._print_status_update(status_data)

                # Check if job is complete
                if status_data["state"] in ["Job Complete", "Failed", "Aborted"]:
                    return status_data

                # Intelligent polling: increase interval for long-running jobs
                if status_data["percentage"] > 50:
                    poll_interval = min(poll_interval * 1.5, 10)  # Cap at 10 seconds
                elif status_data["percentage"] > 25:
                    poll_interval = min(poll_interval * 1.2, 5)  # Cap at 5 seconds

                time.sleep(poll_interval)

        def _print_status_update(self, status_data: Dict[str, Any]):
            """Print a user-friendly status update."""
            state = status_data["state"]
            percentage = status_data.get("percentage", 0)
            message = status_data.get("message", "")

            if state == "In Progress":
                print(f"🔄 {message} ({percentage}% complete)")
                if status_data.get("estimated_remaining"):
                    print(
                        f"   ⏱️  Estimated time remaining: {status_data['estimated_remaining']}"
                    )
            elif state == "Job Complete":
                print(f"✅ {message}")
                print(
                    f"   📊 Success: {status_data.get('success_count', 0)}, Errors: {status_data.get('error_count', 0)}"
                )
            elif state == "Failed":
                print(f"❌ {message}")
                if status_data.get("errors"):
                    print(f"   🔍 Errors: {status_data['errors']}")
            elif state == "Aborted":
                print(f"⏹️  {message}")

        def get_aggregates(self, job_id: str) -> Dict[str, Any]:
            """Get aggregate results for a completed job."""
            response = self.session.get(
                f"{self.base_url}/api/transactions/jobs/{job_id}/aggregates/"
            )
            response.raise_for_status()
            return response.json()

        def handle_job_completion(
            self, job_id: str, status_data: Dict[str, Any]
        ) -> Dict[str, Any]:
            """
            Handle job completion and retrieve results.

            Returns:
                Dictionary with job results and aggregates
            """
            result = {"job_id": job_id, "status": status_data, "aggregates": None}

            if status_data["state"] == "Job Complete":
                try:
                    aggregates = self.get_aggregates(job_id)
                    result["aggregates"] = aggregates
                    print(f"📈 Aggregate results retrieved successfully")
                except requests.exceptions.HTTPError as e:
                    print(f"⚠️  Could not retrieve aggregates: {e}")

            return result

    # Example usage
    def demonstrate_best_practices():
        """Demonstrate the best practices for monitoring bulk operations."""

        monitor = BulkOperationMonitor("http://localhost:8000")

        # 1. Start bulk operation
        print("🚀 Starting bulk create operation...")
        sample_data = [
            {"amount": 100, "description": "Test transaction 1"},
            {"amount": 200, "description": "Test transaction 2"},
            {"amount": 300, "description": "Test transaction 3"},
        ]

        try:
            job_info = monitor.start_bulk_create(sample_data)
            job_id = job_info["job_id"]

            print(f"📋 Job created: {job_id}")
            print(f"📊 Total items: {job_info['total_items']}")
            print(f"⏱️  Estimated duration: {job_info['estimated_duration']}")
            print(f"📝 Next steps: {job_info['next_steps']}")
            print(f"💡 Tips: {job_info['tips']}")
            print()

            # 2. Monitor progress with intelligent polling
            print("🔍 Monitoring job progress...")
            final_status = monitor.poll_job_status(job_id, max_wait_time=60)

            # 3. Handle completion
            print("\n📋 Processing final results...")
            results = monitor.handle_job_completion(job_id, final_status)

            # 4. Display results
            if results["aggregates"]:
                print(f"📊 Aggregate Results:")
                print(json.dumps(results["aggregates"], indent=2))

            return results

        except requests.exceptions.RequestException as e:
            print(f"❌ Network error: {e}")
            return None
        except TimeoutError as e:
            print(f"⏰ {e}")
            return None
        except Exception as e:
            print(f"💥 Unexpected error: {e}")
            return None

    # Example of error handling and retry strategies
    def demonstrate_error_handling():
        """Demonstrate error handling and retry strategies."""

        monitor = BulkOperationMonitor("http://localhost:8000")

        def retry_with_backoff(func, max_retries=3, base_delay=1):
            """Retry function with exponential backoff."""
            for attempt in range(max_retries):
                try:
                    return func()
                except requests.exceptions.RequestException as e:
                    if attempt == max_retries - 1:
                        raise e
                    delay = base_delay * (2**attempt)
                    print(f"⚠️  Attempt {attempt + 1} failed, retrying in {delay}s...")
                    time.sleep(delay)

        # Example: Retry job status check
        try:
            result = retry_with_backoff(lambda: monitor.poll_job_status("some-job-id"))
            print("✅ Job monitoring completed successfully")
        except Exception as e:
            print(f"❌ All retry attempts failed: {e}")

    # Example of batch processing with progress tracking
    def demonstrate_batch_processing():
        """Demonstrate processing multiple batches with progress tracking."""

        monitor = BulkOperationMonitor("http://localhost:8000")

        # Large dataset split into batches
        large_dataset = [
            {"amount": i * 100, "description": f"Transaction {i}"}
            for i in range(1, 1001)  # 1000 items
        ]

        batch_size = 100
        batches = [
            large_dataset[i : i + batch_size]
            for i in range(0, len(large_dataset), batch_size)
        ]

        print(f"📦 Processing {len(large_dataset)} items in {len(batches)} batches...")

        completed_jobs = []
        failed_jobs = []

        for i, batch in enumerate(batches, 1):
            print(f"\n🔄 Processing batch {i}/{len(batches)} ({len(batch)} items)...")

            try:
                job_info = monitor.start_bulk_create(batch)
                final_status = monitor.poll_job_status(job_info["job_id"])

                if final_status["state"] == "Job Complete":
                    completed_jobs.append(
                        {
                            "batch": i,
                            "job_id": job_info["job_id"],
                            "success_count": final_status["success_count"],
                            "error_count": final_status["error_count"],
                        }
                    )
                    print(f"✅ Batch {i} completed successfully")
                else:
                    failed_jobs.append(
                        {
                            "batch": i,
                            "job_id": job_info["job_id"],
                            "state": final_status["state"],
                        }
                    )
                    print(f"❌ Batch {i} failed")

            except Exception as e:
                print(f"💥 Batch {i} failed with error: {e}")
                failed_jobs.append({"batch": i, "error": str(e)})

        # Summary
        print(f"\n📊 Batch Processing Summary:")
        print(f"   ✅ Completed: {len(completed_jobs)} batches")
        print(f"   ❌ Failed: {len(failed_jobs)} batches")
        print(
            f"   📈 Total successful items: {sum(j['success_count'] for j in completed_jobs)}"
        )
        print(f"   ⚠️  Total errors: {sum(j['error_count'] for j in completed_jobs)}")

    return {
        "demonstrate_best_practices": demonstrate_best_practices,
        "demonstrate_error_handling": demonstrate_error_handling,
        "demonstrate_batch_processing": demonstrate_batch_processing,
        "BulkOperationMonitor": BulkOperationMonitor,
    }


if __name__ == "__main__":
    print("Enhanced Bulk Processing Examples")
    print("=" * 50)

    # Run examples
    example_enhanced_bulk_create()
    example_enhanced_bulk_upsert()
    example_run_aggregates()
    example_check_job_status()
    example_get_aggregate_results()
    comparison_with_old_system()

    print("\n" + "=" * 50)
    print("Enhanced bulk processing is now the default!")
    print("All /bulk/ endpoints now use job state tracking.")
    print("Additional endpoints available:")
    print("  - GET /jobs/{job_id}/status/")
    print("  - GET /jobs/{job_id}/aggregates/")
    print("  - POST /jobs/aggregates/")
