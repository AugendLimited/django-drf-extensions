"""
Example: Transaction Processing Pipeline

This example demonstrates the new transaction pipeline that handles:
1. Import transactions
2. Aggregate data
3. Run credit model
4. Generate offers

All in a single API call with internal orchestration.
"""

import json
import time

import requests

# Configuration
API_BASE_URL = "http://localhost:8000/api"
FINANCIAL_TRANSACTIONS_URL = f"{API_BASE_URL}/financial-transactions"


def send_transactions_for_processing():
    """
    Send transactions to the pipeline endpoint.
    The system will handle everything internally.
    """

    # Sample transaction data (your 29GB file would be much larger)
    transaction_data = [
        {
            "amount": 1500.00,
            "date": "2024-01-15",
            "is_revenue": True,
            "description": "Revenue transaction 1",
        },
        {
            "amount": 2500.00,
            "date": "2024-01-15",
            "is_revenue": True,
            "description": "Revenue transaction 2",
        },
        {
            "amount": 500.00,
            "date": "2024-01-16",
            "is_revenue": False,
            "description": "Expense transaction 1",
        },
        {
            "amount": 3000.00,
            "date": "2024-01-16",
            "is_revenue": True,
            "description": "Revenue transaction 3",
        },
    ]

    # Credit model configuration
    credit_model_config = {
        "model_version": "v2.1",
        "risk_threshold": 0.7,
        "credit_score_weights": {
            "transaction_volume": 0.4,
            "revenue_ratio": 0.3,
            "consistency": 0.3,
        },
    }

    # Aggregation configuration
    aggregate_config = {
        "group_by": "date",
        "include_metrics": ["total_amount", "revenue_amount", "transaction_count"],
        "date_range": "last_30_days",
    }

    # Send to pipeline endpoint
    response = requests.post(
        f"{FINANCIAL_TRANSACTIONS_URL}/process-transactions/",
        json={
            "data": transaction_data,
            "credit_model_config": credit_model_config,
            "aggregate_config": aggregate_config,
        },
    )

    if response.status_code == 202:
        result = response.json()
        print("✅ Pipeline started successfully!")
        print(f"Job ID: {result['job_id']}")
        print(f"Status URL: {result['status_url']}")
        print(f"Offers URL: {result['offers_url']}")
        print(f"Estimated Duration: {result['estimated_duration']}")
        print(f"Next Steps: {result['next_steps']}")
        return result
    else:
        print(f"❌ Failed to start pipeline: {response.status_code}")
        print(response.text)
        return None


def monitor_pipeline_progress(job_id):
    """Monitor the pipeline progress using the status endpoint."""

    status_url = f"{API_BASE_URL}/jobs/{job_id}/status/"

    print(f"\n📊 Monitoring pipeline progress...")
    print(f"Status URL: {status_url}")

    while True:
        response = requests.get(status_url)

        if response.status_code == 200:
            status = response.json()

            print(f"\n🔄 Current Status: {status['status']}")
            print(f"📝 Message: {status['message']}")
            print(f"⏱️  Estimated Remaining: {status['estimated_remaining']}")
            print(f"📈 Progress: {status.get('progress', 'N/A')}")

            if status["status"] == "Job Complete":
                print("✅ Pipeline completed successfully!")
                return True
            elif status["status"] == "Failed":
                print(f"❌ Pipeline failed: {status.get('errors', 'Unknown error')}")
                return False

        else:
            print(f"❌ Failed to get status: {response.status_code}")
            return False

        time.sleep(5)  # Check every 5 seconds


def get_pipeline_results(job_id):
    """Retrieve the final offers from the completed pipeline."""

    offers_url = f"{API_BASE_URL}/jobs/{job_id}/offers/"

    response = requests.get(offers_url)

    if response.status_code == 200:
        results = response.json()

        print("\n🎯 Pipeline Results:")
        print("=" * 50)

        print(f"\n📊 Pipeline Summary:")
        summary = results["pipeline_summary"]
        print(f"  • Transactions Processed: {summary['transactions_processed']}")
        print(f"  • Aggregates Created: {summary['aggregates_created']}")
        print(f"  • Offers Generated: {summary['offers_generated']}")

        print(f"\n🧠 Credit Model Results:")
        credit_results = results["credit_model_results"]
        print(f"  • Model Version: {credit_results['model_version']}")
        print(
            f"  • Credit Scores: {len(credit_results['credit_scores'])} dates processed"
        )
        print(
            f"  • Risk Assessments: {len(credit_results['risk_assessments'])} dates assessed"
        )

        print(f"\n💼 Generated Offers:")
        for i, offer in enumerate(results["offers"], 1):
            print(f"  {i}. Date: {offer['date']}")
            print(f"     Offer Type: {offer['offer_type']}")
            print(f"     Amount: ${offer['amount']:,}")
            print(f"     Interest Rate: {offer['interest_rate']:.1%}")
            print(f"     Credit Score: {offer['credit_score']}")
            print(f"     Risk Level: {offer['risk_level']}")
            print()

        return results
    else:
        print(f"❌ Failed to get results: {response.status_code}")
        print(response.text)
        return None


def use_event_notifications(job_id):
    """
    Alternative: Use event notifications instead of polling.
    This shows how to get real-time updates via SSE.
    """

    print(f"\n🔔 Using Server-Sent Events for real-time updates...")

    # Register for SSE events
    events_url = f"{API_BASE_URL}/jobs/{job_id}/events/"

    try:
        response = requests.get(events_url, stream=True)

        if response.status_code == 200:
            print("📡 Connected to event stream...")

            for line in response.iter_lines():
                if line:
                    # Parse SSE data
                    if line.startswith(b"data: "):
                        data = line[6:].decode("utf-8")
                        if data != "[DONE]":
                            try:
                                event = json.loads(data)
                                print(
                                    f"📢 Event: {event['event_type']} - {event['message']}"
                                )

                                if event["event_type"] == "JOB_COMPLETE":
                                    print("✅ Pipeline completed via events!")
                                    break

                            except json.JSONDecodeError:
                                continue

        else:
            print(f"❌ Failed to connect to event stream: {response.status_code}")

    except Exception as e:
        print(f"❌ Event stream error: {e}")


def main():
    """Run the complete pipeline example."""

    print("🚀 Transaction Processing Pipeline Example")
    print("=" * 50)

    # Step 1: Send transactions to pipeline
    result = send_transactions_for_processing()
    if not result:
        return

    job_id = result["job_id"]

    # Step 2: Monitor progress (choose one method)
    print("\nChoose monitoring method:")
    print("1. Polling (traditional)")
    print("2. Event notifications (real-time)")

    choice = input("Enter choice (1 or 2): ").strip()

    if choice == "2":
        # Use event notifications
        use_event_notifications(job_id)
    else:
        # Use traditional polling
        success = monitor_pipeline_progress(job_id)
        if not success:
            return

    # Step 3: Get results
    get_pipeline_results(job_id)

    print("\n✅ Pipeline example completed!")


if __name__ == "__main__":
    main()
