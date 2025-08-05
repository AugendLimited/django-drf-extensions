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
