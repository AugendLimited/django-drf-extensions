"""
Example: Chunked Upload for Large Transaction Datasets

This example shows how to handle large datasets (like 96K transactions)
by breaking them into manageable chunks and uploading them piece by piece.
"""

import json
import uuid
from typing import Dict, List

import requests


def chunk_transactions(
    transactions: List[Dict], chunk_size: int = 10000
) -> List[List[Dict]]:
    """Split transactions into chunks of specified size."""
    return [
        transactions[i : i + chunk_size]
        for i in range(0, len(transactions), chunk_size)
    ]


def upload_large_dataset(
    api_base_url: str,
    transactions: List[Dict],
    credit_model_config: Dict = None,
    aggregate_config: Dict = None,
) -> str:
    """
    Upload a large dataset using chunked upload.

    Args:
        api_base_url: Base URL of your API
        transactions: List of transaction dictionaries
        credit_model_config: Credit model configuration
        aggregate_config: Aggregation configuration

    Returns:
        job_id: The job ID for tracking progress
    """

    # Generate unique session ID
    session_id = str(uuid.uuid4())

    # Split into chunks (max 10K per chunk)
    chunks = chunk_transactions(transactions, chunk_size=10000)
    total_chunks = len(chunks)

    print(f"Uploading {len(transactions)} transactions in {total_chunks} chunks...")

    # Upload each chunk
    for chunk_number, chunk_data in enumerate(chunks, 1):
        print(
            f"Uploading chunk {chunk_number}/{total_chunks} ({len(chunk_data)} transactions)"
        )

        payload = {
            "chunk_data": chunk_data,
            "chunk_number": chunk_number,
            "total_chunks": total_chunks,
            "session_id": session_id,
            "credit_model_config": credit_model_config or {},
            "aggregate_config": aggregate_config or {},
        }

        response = requests.post(
            f"{api_base_url}/api/financial-transactions/upload-chunked/",
            json=payload,
            headers={"Content-Type": "application/json"},
        )

        if response.status_code == 202:
            # More chunks to upload
            data = response.json()
            progress = data.get("progress", 0)
            print(f"Progress: {progress}% - Waiting for more chunks...")

        elif response.status_code == 200:
            # All chunks uploaded, processing started
            data = response.json()
            job_id = data["job_id"]
            print(f"✅ All chunks uploaded! Job ID: {job_id}")
            print(f"Status URL: {data['status_url']}")
            print(f"Estimated duration: {data['estimated_duration']}")
            return job_id

        else:
            print(f"❌ Upload failed: {response.status_code}")
            print(response.text)
            raise Exception(f"Upload failed: {response.text}")

    return None


def monitor_job_progress(api_base_url: str, job_id: str):
    """Monitor job progress and display updates."""

    print(f"Monitoring job {job_id}...")

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


def get_final_offers(api_base_url: str, job_id: str):
    """Retrieve final offers from completed job."""

    response = requests.get(
        f"{api_base_url}/api/financial-transactions/jobs/{job_id}/offers/"
    )

    if response.status_code == 200:
        data = response.json()
        offers = data.get("offers", [])
        summary = data.get("pipeline_summary", {})

        print(f"🎯 Generated {len(offers)} offers:")
        for offer in offers[:5]:  # Show first 5 offers
            print(
                f"  - {offer['date']}: Score {offer['credit_score']}, Amount ${offer['offer_amount']}"
            )

        print(f"\n📈 Pipeline Summary:")
        print(f"  - Transactions processed: {summary.get('transactions_processed', 0)}")
        print(f"  - Aggregates created: {summary.get('aggregates_created', 0)}")
        print(f"  - Offers generated: {summary.get('offers_generated', 0)}")

        return data
    else:
        print(f"❌ Failed to get offers: {response.status_code}")
        return None


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

    # Generate sample data
    print("Generating sample 96K transactions...")
    transactions = generate_sample_transactions(96000)

    # Upload using chunked approach
    job_id = upload_large_dataset(
        api_base_url=API_BASE_URL,
        transactions=transactions,
        credit_model_config=credit_model_config,
        aggregate_config=aggregate_config,
    )

    if job_id:
        # Monitor progress
        job_data = monitor_job_progress(API_BASE_URL, job_id)

        if job_data and job_data["state"] == "JOB_COMPLETE":
            # Get final offers
            offers_data = get_final_offers(API_BASE_URL, job_id)

    print("\n🎉 Chunked upload example completed!")


# Alternative: Using SSE for real-time updates
def monitor_with_sse(api_base_url: str, job_id: str):
    """Monitor job progress using Server-Sent Events."""

    import sseclient

    url = f"{api_base_url}/api/financial-transactions/jobs/{job_id}/events/"

    try:
        client = sseclient.SSEClient(url)

        print(f"🔗 Connected to SSE stream for job {job_id}")

        for event in client.events():
            data = json.loads(event.data)
            event_type = data.get("event")

            if event_type == "state_change":
                state = data.get("state")
                message = data.get("message", "")
                print(f"📊 {state}: {message}")

                if state == "JOB_COMPLETE":
                    print("✅ Job completed via SSE!")
                    break
                elif state == "FAILED":
                    print(f"❌ Job failed via SSE: {message}")
                    break

            elif event_type == "progress":
                processed = data.get("processed", 0)
                total = data.get("total", 0)
                percentage = data.get("percentage", 0)
                print(f"📈 Progress: {processed}/{total} ({percentage}%)")

    except Exception as e:
        print(f"❌ SSE connection failed: {e}")


# Alternative: Using webhooks
def register_webhook(api_base_url: str, job_id: str, callback_url: str):
    """Register webhook for job notifications."""

    payload = {
        "callback_url": callback_url,
        "events": ["state_change", "progress", "completion"],
        "job_id": job_id,
    }

    response = requests.post(
        f"{api_base_url}/api/financial-transactions/jobs/webhooks/register/",
        json=payload,
    )

    if response.status_code == 200:
        print(f"✅ Webhook registered for job {job_id}")
        return response.json()
    else:
        print(f"❌ Webhook registration failed: {response.status_code}")
        return None
