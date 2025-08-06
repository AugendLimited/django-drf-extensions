"""
Example: Salesforce-Style Bulk API for Large Datasets

This example demonstrates how to use the Salesforce Bulk v2-style approach
for handling large datasets by separating job creation, data upload, and completion.
"""

import csv
import json
from io import StringIO
from typing import Dict, List

import requests


def create_bulk_job(
    api_base_url: str,
    object_name: str,
    operation: str = "create",
    content_type: str = "json",
    credit_model_config: Dict = None,
    aggregate_config: Dict = None,
) -> str:
    """
    Create a bulk job without data (Salesforce-style).

    Args:
        api_base_url: Base URL of your API
        object_name: Model name (e.g., 'FinancialTransaction')
        operation: Operation type (create, update, upsert, delete, pipeline)
        content_type: Data format (json, csv)
        credit_model_config: Credit model configuration
        aggregate_config: Aggregation configuration

    Returns:
        job_id: The job ID for subsequent operations
    """

    payload = {
        "object": object_name,
        "operation": operation,
        "content_type": content_type,
        "credit_model_config": credit_model_config or {},
        "aggregate_config": aggregate_config or {},
    }

    response = requests.post(
        f"{api_base_url}/api/financial-transactions/jobs/",
        json=payload,
        headers={"Content-Type": "application/json"},
    )

    if response.status_code == 201:
        data = response.json()
        job_id = data["job_id"]
        print(f"✅ Created bulk job: {job_id}")
        print(f"   Object: {data['object']}")
        print(f"   Operation: {data['operation']}")
        print(f"   State: {data['state']}")
        print(f"   Upload URL: {data['upload_url']}")
        return job_id
    else:
        print(f"❌ Failed to create job: {response.status_code}")
        print(response.text)
        raise Exception(f"Job creation failed: {response.text}")


def upload_data_json(api_base_url: str, job_id: str, data: List[Dict]) -> Dict:
    """
    Upload JSON data to a bulk job.

    Args:
        api_base_url: Base URL of your API
        job_id: Job ID from create_bulk_job
        data: List of records to upload

    Returns:
        Upload response data
    """

    response = requests.put(
        f"{api_base_url}/api/financial-transactions/jobs/{job_id}/upload/",
        data=json.dumps(data),
        headers={"Content-Type": "application/json"},
    )

    if response.status_code == 200:
        result = response.json()
        print(f"✅ Uploaded {result['records_count']} records")
        print(f"   Total records: {result['total_records']}")
        print(f"   Batch number: {result['batch_number']}")
        return result
    else:
        print(f"❌ Upload failed: {response.status_code}")
        print(response.text)
        raise Exception(f"Upload failed: {response.text}")


def upload_data_csv(api_base_url: str, job_id: str, data: List[Dict]) -> Dict:
    """
    Upload CSV data to a bulk job.

    Args:
        api_base_url: Base URL of your API
        job_id: Job ID from create_bulk_job
        data: List of records to upload

    Returns:
        Upload response data
    """

    # Convert data to CSV
    if not data:
        raise ValueError("No data to upload")

    # Get field names from first record
    fieldnames = list(data[0].keys())

    # Create CSV string
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(data)

    csv_data = output.getvalue()

    response = requests.put(
        f"{api_base_url}/api/financial-transactions/jobs/{job_id}/upload/",
        data=csv_data,
        headers={"Content-Type": "text/csv"},
    )

    if response.status_code == 200:
        result = response.json()
        print(f"✅ Uploaded {result['records_count']} records (CSV)")
        print(f"   Total records: {result['total_records']}")
        print(f"   Batch number: {result['batch_number']}")
        return result
    else:
        print(f"❌ Upload failed: {response.status_code}")
        print(response.text)
        raise Exception(f"Upload failed: {response.text}")


def complete_job_upload(api_base_url: str, job_id: str) -> Dict:
    """
    Complete job upload and start processing.

    Args:
        api_base_url: Base URL of your API
        job_id: Job ID from create_bulk_job

    Returns:
        Completion response data
    """

    response = requests.patch(
        f"{api_base_url}/api/financial-transactions/jobs/{job_id}/complete/",
        headers={"Content-Type": "application/json"},
    )

    if response.status_code == 200:
        result = response.json()
        print(f"✅ Job upload completed")
        print(f"   Total records: {result['total_records']}")
        print(f"   Total bytes: {result['total_bytes']}")
        print(f"   State: {result['state']}")
        print(f"   Estimated duration: {result['estimated_duration']}")
        return result
    else:
        print(f"❌ Completion failed: {response.status_code}")
        print(response.text)
        raise Exception(f"Completion failed: {response.text}")


def upload_large_dataset_salesforce_style(
    api_base_url: str,
    transactions: List[Dict],
    chunk_size: int = 10000,
    content_type: str = "json",
    operation: str = "pipeline",
) -> str:
    """
    Upload large dataset using Salesforce-style approach.

    Args:
        api_base_url: Base URL of your API
        transactions: List of transaction dictionaries
        chunk_size: Size of each upload chunk
        content_type: Data format (json, csv)
        operation: Operation type (create, pipeline, etc.)

    Returns:
        job_id: The job ID for monitoring
    """

    # Configuration
    credit_model_config = {
        "model_version": "v1.0",
        "rolling_period": 12,
        "risk_threshold": 0.7,
    }

    aggregate_config = {
        "group_by": ["account_id", "date"],
        "aggregations": ["sum", "count", "avg"],
    }

    # Step 1: Create bulk job
    print("📋 Creating bulk job...")
    job_id = create_bulk_job(
        api_base_url=api_base_url,
        object_name="FinancialTransaction",
        operation=operation,
        content_type=content_type,
        credit_model_config=credit_model_config,
        aggregate_config=aggregate_config,
    )

    # Step 2: Upload data in chunks
    print(f"📤 Uploading {len(transactions)} transactions in chunks...")
    chunks = [
        transactions[i : i + chunk_size]
        for i in range(0, len(transactions), chunk_size)
    ]

    for chunk_num, chunk_data in enumerate(chunks, 1):
        print(
            f"   Uploading chunk {chunk_num}/{len(chunks)} ({len(chunk_data)} records)"
        )

        if content_type == "json":
            upload_data_json(api_base_url, job_id, chunk_data)
        elif content_type == "csv":
            upload_data_csv(api_base_url, job_id, chunk_data)
        else:
            raise ValueError(f"Unsupported content type: {content_type}")

    # Step 3: Complete upload and start processing
    print("🚀 Completing upload and starting processing...")
    complete_result = complete_job_upload(api_base_url, job_id)

    return job_id


def monitor_job_progress(api_base_url: str, job_id: str):
    """Monitor job progress and display updates."""

    print(f"📊 Monitoring job {job_id}...")

    while True:
        response = requests.get(
            f"{api_base_url}/api/financial-transactions/jobs/{job_id}/status/"
        )

        if response.status_code == 200:
            data = response.json()
            state = data["state"]
            message = data.get("message", "")
            progress = data.get("progress", {})

            if progress:
                processed = progress.get("processed_items", 0)
                total = progress.get("total_items", 0)
                percentage = progress.get("percentage", 0)
                print(f"📊 {state}: {message} ({processed}/{total} - {percentage}%)")
            else:
                print(f"📊 {state}: {message}")

            if state == "JOB_COMPLETE":
                print("✅ Job completed successfully!")
                return data
            elif state == "FAILED":
                print(f"❌ Job failed: {message}")
                return data

        else:
            print(f"❌ Failed to get status: {response.status_code}")
            break

        # Wait before next check
        import time

        time.sleep(5)


# Example usage
if __name__ == "__main__":
    # Example configuration
    API_BASE_URL = "https://api.example.com"

    # Generate sample 96K transactions
    def generate_sample_transactions(count: int = 96000) -> List[Dict]:
        """Generate sample transaction data."""
        transactions = []

        for i in range(count):
            transaction = {
                "account_id": (i % 20000) + 1,  # 20K accounts
                "amount": round((i % 10000) - 5000, 2),  # -5000 to 5000
                "date": f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",
                "is_revenue": i % 3 != 0,  # 2/3 revenue, 1/3 expenses
                "description": f"Transaction {i + 1}",
            }
            transactions.append(transaction)

        return transactions

    # Generate sample data
    print("Generating sample 96K transactions...")
    transactions = generate_sample_transactions(96000)

    # Upload using Salesforce-style approach
    job_id = upload_large_dataset_salesforce_style(
        api_base_url=API_BASE_URL,
        transactions=transactions,
        chunk_size=10000,
        content_type="json",
        operation="pipeline",
    )

    if job_id:
        # Monitor progress
        job_data = monitor_job_progress(API_BASE_URL, job_id)

        if job_data and job_data["state"] == "JOB_COMPLETE":
            # Get final offers
            response = requests.get(
                f"{API_BASE_URL}/api/financial-transactions/jobs/{job_id}/offers/"
            )

            if response.status_code == 200:
                offers_data = response.json()
                offers = offers_data.get("offers", [])
                summary = offers_data.get("pipeline_summary", {})

                print(f"🎯 Generated {len(offers)} offers:")
                for offer in offers[:5]:  # Show first 5 offers
                    print(
                        f"  - {offer['date']}: Score {offer['credit_score']}, Amount ${offer['offer_amount']}"
                    )

                print(f"\n📈 Pipeline Summary:")
                print(
                    f"  - Transactions processed: {summary.get('transactions_processed', 0)}"
                )
                print(f"  - Aggregates created: {summary.get('aggregates_created', 0)}")
                print(f"  - Offers generated: {summary.get('offers_generated', 0)}")

    print("\n🎉 Salesforce-style bulk API example completed!")


# Alternative: Using CSV format
def upload_csv_example(api_base_url: str):
    """Example using CSV format for data upload."""

    # Create job for CSV upload
    job_id = create_bulk_job(
        api_base_url=api_base_url,
        object_name="FinancialTransaction",
        operation="create",
        content_type="csv",
    )

    # Generate sample data
    transactions = generate_sample_transactions(1000)  # Smaller sample for demo

    # Upload as CSV
    upload_data_csv(api_base_url, job_id, transactions)

    # Complete upload
    complete_job_upload(api_base_url, job_id)

    return job_id


# Alternative: Multiple batches to same job
def upload_multiple_batches(api_base_url: str):
    """Example uploading multiple batches to the same job."""

    # Create job
    job_id = create_bulk_job(
        api_base_url=api_base_url,
        object_name="FinancialTransaction",
        operation="create",
        content_type="json",
    )

    # Upload multiple batches
    for batch_num in range(1, 6):  # 5 batches
        batch_data = generate_sample_transactions(1000)  # 1K per batch

        print(f"Uploading batch {batch_num}/5...")
        upload_data_json(api_base_url, job_id, batch_data)

    # Complete upload
    complete_job_upload(api_base_url, job_id)

    return job_id
