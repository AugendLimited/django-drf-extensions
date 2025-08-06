"""
Example: Increased Limits for Bank Onboarding

This example demonstrates how to handle large datasets (96K transactions)
by increasing Django, nginx, and Celery limits for a bank scenario.

This approach is suitable for:
- Controlled load (not thousands of users)
- High-value transactions (worth infrastructure cost)
- Simple implementation requirements
- Bank compliance scenarios
"""

import json
import time
import uuid
from datetime import datetime
from typing import Dict, List

import redis
import requests
from django.conf import settings
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

# =============================================================================
# CONFIGURATION - INCREASED LIMITS
# =============================================================================

"""
settings.py - Increase Django limits for bank scenario
"""

# Django settings for large file uploads
DATA_UPLOAD_MAX_MEMORY_SIZE = 500 * 1024 * 1024  # 500MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 500 * 1024 * 1024  # 500MB

# Celery settings for large messages
CELERY_TASK_SERIALIZER = "pickle"  # Handle larger messages
CELERY_RESULT_SERIALIZER = "pickle"
CELERY_ACCEPT_CONTENT = ["pickle"]

# Database settings for large transactions
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "bank_db",
        "OPTIONS": {
            "connect_timeout": 300,  # 5 minutes
        },
    }
}

"""
nginx.conf - Increase nginx limits
"""

# nginx configuration
# client_max_body_size 500M;  # 500MB
# proxy_read_timeout 600s;     # 10 minutes
# proxy_send_timeout 600s;     # 10 minutes


# =============================================================================
# BANK ONBOARDING ENDPOINT - SINGLE REQUEST APPROACH
# =============================================================================


@csrf_exempt
@require_http_methods(["POST"])
def bank_onboarding_endpoint(request):
    """
    Single endpoint for bank customer onboarding with 96K transactions.

    This approach works for:
    - Controlled load (not thousands of users)
    - High-value transactions (worth infrastructure cost)
    - Simple implementation requirements
    - Bank compliance scenarios
    """

    try:
        # Parse request data
        data = json.loads(request.body)
        customer_id = data.get("customer_id")
        transactions = data.get("transactions", [])
        compliance_level = data.get("compliance_level", "high")

        # Validate input
        if not customer_id:
            return JsonResponse({"error": "customer_id is required"}, status=400)

        if not transactions:
            return JsonResponse({"error": "transactions array is required"}, status=400)

        # Log bank activity for compliance
        log_bank_activity(
            customer_id,
            "onboarding_started",
            {
                "transaction_count": len(transactions),
                "compliance_level": compliance_level,
                "ip_address": request.META.get("REMOTE_ADDR"),
                "user_agent": request.META.get("HTTP_USER_AGENT"),
            },
        )

        # Process transactions in single request
        start_time = time.time()
        result = process_bank_transactions(customer_id, transactions, compliance_level)
        processing_time = time.time() - start_time

        # Log completion
        log_bank_activity(
            customer_id,
            "onboarding_completed",
            {
                "transaction_count": len(transactions),
                "processing_time": processing_time,
                "result": result,
            },
        )

        return JsonResponse(
            {
                "status": "completed",
                "customer_id": customer_id,
                "transactions_processed": len(transactions),
                "processing_time_seconds": round(processing_time, 2),
                "compliance_level": compliance_level,
                "result": result,
            }
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON in request body"}, status=400)
    except Exception as e:
        # Log error for compliance
        log_bank_activity(
            customer_id,
            "onboarding_failed",
            {
                "error": str(e),
                "transaction_count": len(transactions)
                if "transactions" in locals()
                else 0,
            },
        )

        return JsonResponse(
            {"error": "Processing failed", "details": str(e)}, status=500
        )


def process_bank_transactions(
    customer_id: str, transactions: List[Dict], compliance_level: str
) -> Dict:
    """
    Process 96K transactions for bank onboarding.

    This function handles the entire processing pipeline:
    1. Import transactions
    2. Aggregate data
    3. Run credit model
    4. Generate offers
    """

    print(f"Processing {len(transactions)} transactions for customer {customer_id}")

    # Step 1: Import transactions with real-time aggregation
    print("Step 1: Importing transactions with real-time aggregation")
    import_result = import_transactions_with_aggregation(transactions)

    # Step 2: Final consistency check
    print("Step 2: Running final consistency check")
    consistency_result = run_consistency_check(import_result["transaction_ids"])

    # Step 3: Run credit model
    print("Step 3: Running credit model")
    credit_model_result = run_credit_model(consistency_result["aggregates"])

    # Step 4: Generate offers
    print("Step 4: Generating offers")
    offers = generate_offers(credit_model_result, len(transactions))

    return {
        "import_result": import_result,
        "consistency_result": consistency_result,
        "credit_model_result": credit_model_result,
        "offers": offers,
        "compliance_level": compliance_level,
    }


# =============================================================================
# STREAMING RESPONSE VERSION
# =============================================================================


@csrf_exempt
@require_http_methods(["POST"])
def bank_onboarding_streaming(request):
    """
    Streaming version of bank onboarding for real-time progress updates.
    """

    def generate_streaming_response():
        try:
            # Parse request data
            data = json.loads(request.body)
            customer_id = data.get("customer_id")
            transactions = data.get("transactions", [])

            # Start processing
            yield f"data: {json.dumps({'status': 'started', 'customer_id': customer_id})}\n\n"

            # Step 1: Import transactions
            yield f"data: {json.dumps({'step': 1, 'message': 'Importing transactions...'})}\n\n"
            import_result = import_transactions_with_aggregation(transactions)
            yield f"data: {json.dumps({'step': 1, 'complete': True, 'result': import_result})}\n\n"

            # Step 2: Consistency check
            yield f"data: {json.dumps({'step': 2, 'message': 'Running consistency check...'})}\n\n"
            consistency_result = run_consistency_check(import_result["transaction_ids"])
            yield f"data: {json.dumps({'step': 2, 'complete': True, 'result': consistency_result})}\n\n"

            # Step 3: Credit model
            yield f"data: {json.dumps({'step': 3, 'message': 'Running credit model...'})}\n\n"
            credit_model_result = run_credit_model(consistency_result["aggregates"])
            yield f"data: {json.dumps({'step': 3, 'complete': True, 'result': credit_model_result})}\n\n"

            # Step 4: Generate offers
            yield f"data: {json.dumps({'step': 4, 'message': 'Generating offers...'})}\n\n"
            offers = generate_offers(credit_model_result, len(transactions))
            yield f"data: {json.dumps({'step': 4, 'complete': True, 'result': offers})}\n\n"

            # Complete
            yield f"data: {json.dumps({'status': 'completed', 'customer_id': customer_id})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'error': str(e)})}\n\n"

    return StreamingHttpResponse(
        generate_streaming_response(), content_type="text/event-stream"
    )


# =============================================================================
# REDIS-BASED LARGE DATA HANDLING
# =============================================================================


def handle_large_request_with_redis(request):
    """
    Handle large request using Redis for memory management.
    """

    try:
        # Parse request data
        data = json.loads(request.body)
        customer_id = data.get("customer_id")
        transactions = data.get("transactions", [])

        # Store in Redis to free memory
        job_id = str(uuid.uuid4())
        r = redis.Redis()

        # Store transactions in Redis
        r.setex(f"transactions:{job_id}", 3600, json.dumps(transactions))
        r.setex(f"customer:{job_id}", 3600, customer_id)

        # Process from Redis
        result = process_from_redis(job_id)

        # Clean up Redis
        r.delete(f"transactions:{job_id}")
        r.delete(f"customer:{job_id}")

        return JsonResponse(
            {
                "status": "completed",
                "job_id": job_id,
                "customer_id": customer_id,
                "result": result,
            }
        )

    except Exception as e:
        return JsonResponse(
            {"error": "Processing failed", "details": str(e)}, status=500
        )


def process_from_redis(job_id: str) -> Dict:
    """
    Process data from Redis to manage memory usage.
    """

    r = redis.Redis()

    # Get data from Redis
    transactions_json = r.get(f"transactions:{job_id}")
    customer_id = r.get(f"customer:{job_id}")

    if not transactions_json or not customer_id:
        raise ValueError("Data not found in Redis")

    transactions = json.loads(transactions_json.decode("utf-8"))
    customer_id = customer_id.decode("utf-8")

    # Process transactions
    return process_bank_transactions(customer_id, transactions, "high")


# =============================================================================
# PROCESSING FUNCTIONS
# =============================================================================


def import_transactions_with_aggregation(transactions: List[Dict]) -> Dict:
    """
    Import transactions with real-time aggregation.
    """

    transaction_ids = []
    aggregates = {}

    for i, transaction in enumerate(transactions):
        # Simulate transaction import
        transaction_id = f"txn_{i}_{uuid.uuid4().hex[:8]}"
        transaction_ids.append(transaction_id)

        # Real-time aggregation
        date = transaction.get("date")
        account_id = transaction.get("account_id")
        amount = transaction.get("amount", 0)

        if date and account_id:
            key = f"{account_id}_{date}"
            if key not in aggregates:
                aggregates[key] = {
                    "account_id": account_id,
                    "date": date,
                    "total_amount": 0,
                    "transaction_count": 0,
                    "revenue_amount": 0,
                    "expense_amount": 0,
                }

            aggregates[key]["total_amount"] += amount
            aggregates[key]["transaction_count"] += 1

            if transaction.get("is_revenue", False):
                aggregates[key]["revenue_amount"] += amount
            else:
                aggregates[key]["expense_amount"] += abs(amount)

        # Progress update every 10K transactions
        if (i + 1) % 10000 == 0:
            print(f"Imported {i + 1}/{len(transactions)} transactions")

    return {
        "transaction_ids": transaction_ids,
        "aggregates": aggregates,
        "total_transactions": len(transactions),
    }


def run_consistency_check(transaction_ids: List[str]) -> Dict:
    """
    Run final consistency check on aggregates.
    """

    # Simulate consistency check
    print(f"Running consistency check on {len(transaction_ids)} transactions")

    # In real implementation, this would recalculate aggregates from scratch
    aggregates = {"consistency_check": True, "corrections_made": 0, "aggregates": {}}

    return aggregates


def run_credit_model(aggregates: Dict) -> Dict:
    """
    Run credit model on aggregated data.
    """

    print("Running credit model...")

    credit_scores = {}
    risk_assessments = {}

    # Simple rolling average credit model
    for key, aggregate in aggregates.items():
        # Calculate credit score based on aggregate data
        total_amount = aggregate.get("total_amount", 0)
        transaction_count = aggregate.get("transaction_count", 0)
        revenue_amount = aggregate.get("revenue_amount", 0)

        # Simple credit score calculation
        if transaction_count > 0:
            avg_amount = total_amount / transaction_count
            revenue_ratio = revenue_amount / total_amount if total_amount > 0 else 0

            credit_score = min(
                100, max(0, 50 + (avg_amount / 1000) * 10 + revenue_ratio * 20)
            )

            risk_level = (
                "LOW"
                if credit_score > 80
                else "MEDIUM"
                if credit_score > 60
                else "HIGH"
            )
        else:
            credit_score = 50
            risk_level = "MEDIUM"

        credit_scores[key] = credit_score
        risk_assessments[key] = risk_level

    return {
        "credit_scores": credit_scores,
        "risk_assessments": risk_assessments,
        "model_version": "v1.0",
        "aggregates_processed": len(aggregates),
    }


def generate_offers(credit_model_result: Dict, transaction_count: int) -> List[Dict]:
    """
    Generate offers based on credit model results.
    """

    print("Generating offers...")

    offers = []
    credit_scores = credit_model_result.get("credit_scores", {})
    risk_assessments = credit_model_result.get("risk_assessments", {})

    for key, credit_score in credit_scores.items():
        risk_level = risk_assessments.get(key, "MEDIUM")

        # Generate offer based on credit score
        if credit_score > 80:
            offer_amount = 10000
            interest_rate = 4.5
        elif credit_score > 60:
            offer_amount = 5000
            interest_rate = 6.0
        else:
            offer_amount = 2000
            interest_rate = 8.5

        offer = {
            "date": key.split("_")[1] if "_" in key else "2024-01-01",
            "credit_score": credit_score,
            "risk_level": risk_level,
            "offer_amount": offer_amount,
            "interest_rate": interest_rate,
            "terms": "12 months",
            "account_id": key.split("_")[0] if "_" in key else "unknown",
        }

        offers.append(offer)

    return offers


# =============================================================================
# COMPLIANCE AND LOGGING
# =============================================================================


def log_bank_activity(customer_id: str, activity: str, details: Dict):
    """
    Log bank activity for compliance requirements.
    """

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "customer_id": customer_id,
        "activity": activity,
        "details": details,
        "compliance_level": "high",
    }

    # In production, this would go to a compliance logging system
    print(f"BANK_ACTIVITY: {json.dumps(log_entry)}")

    # Store in Redis for audit trail
    r = redis.Redis()
    audit_key = f"audit:{customer_id}:{datetime.now().strftime('%Y%m%d')}"
    r.lpush(audit_key, json.dumps(log_entry))
    r.expire(audit_key, 86400 * 365)  # Keep for 1 year


# =============================================================================
# CLIENT EXAMPLES
# =============================================================================


def client_example_simple():
    """
    Simple client example for bank onboarding.
    """

    # Generate sample 96K transactions
    transactions = generate_sample_transactions(96000)

    # Single request with increased limits
    response = requests.post(
        "https://api.bank.com/api/bank/onboard/",
        json={
            "customer_id": "cust_123",
            "transactions": transactions,
            "compliance_level": "high",
        },
        headers={"Content-Type": "application/json"},
        timeout=600,  # 10 minute timeout
    )

    if response.status_code == 200:
        result = response.json()
        print(f"✅ Onboarding completed!")
        print(f"   Customer: {result['customer_id']}")
        print(f"   Transactions: {result['transactions_processed']}")
        print(f"   Processing time: {result['processing_time_seconds']}s")
        return result
    else:
        print(f"❌ Onboarding failed: {response.text}")
        return None


def client_example_streaming():
    """
    Streaming client example for real-time progress.
    """

    import sseclient

    # Generate sample data
    transactions = generate_sample_transactions(96000)

    # Start streaming request
    response = requests.post(
        "https://api.bank.com/api/bank/onboard/stream/",
        json={"customer_id": "cust_123", "transactions": transactions},
        stream=True,
    )

    # Process streaming response
    client = sseclient.SSEClient(response)

    for event in client.events():
        data = json.loads(event.data)

        if data.get("status") == "started":
            print("🚀 Onboarding started...")
        elif data.get("step"):
            print(f"📊 Step {data['step']}: {data.get('message', '')}")
        elif data.get("status") == "completed":
            print("✅ Onboarding completed!")
            break
        elif data.get("status") == "error":
            print(f"❌ Error: {data.get('error', '')}")
            break


def generate_sample_transactions(count: int) -> List[Dict]:
    """
    Generate sample transaction data for testing.
    """

    transactions = []

    for i in range(count):
        transaction = {
            "account_id": (i % 20000) + 1,  # 20K accounts
            "amount": round((i % 10000) - 5000, 2),  # -5000 to 5000
            "date": f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",
            "is_revenue": i % 3 != 0,  # 2/3 revenue, 1/3 expenses
            "description": f"Transaction {i + 1}",
            "category": "banking",
            "reference": f"REF_{i:06d}",
        }
        transactions.append(transaction)

    return transactions


# =============================================================================
# PERFORMANCE ESTIMATES
# =============================================================================


def estimate_performance():
    """
    Performance estimates for 96K transactions with increased limits.
    """

    print("📊 Performance Estimates for 96K Transactions")
    print("=" * 50)

    # Data size estimates
    per_transaction = 200  # bytes (JSON overhead)
    total_size = 96000 * 200  # 19.2MB

    print(f"Data size: {total_size / (1024 * 1024):.1f}MB")
    print(f"Django limit: 500MB ✅")
    print(f"nginx limit: 500MB ✅")

    # Processing time estimates
    print("\nProcessing time estimates:")
    print(f"Import: 96K × 0.1ms = 9.6 seconds")
    print(f"Aggregation: 365 days × 1ms = 0.4 seconds")
    print(f"Credit model: 365 × 0.1ms = 0.04 seconds")
    print(f"Offers: 365 × 0.1ms = 0.04 seconds")
    print(f"Total: ~10 seconds")

    # Memory usage estimates
    print("\nMemory usage estimates:")
    print(f"Request data: 20MB")
    print(f"Processing: 50MB")
    print(f"Total: ~70MB")
    print(f"Available: 500MB ✅")

    # Bank-specific considerations
    print("\nBank-specific considerations:")
    print(f"✅ Controlled load (not thousands of users)")
    print(f"✅ High-value transactions (worth infrastructure)")
    print(f"✅ Simple implementation (faster development)")
    print(f"✅ Manageable memory (20MB is doable)")


if __name__ == "__main__":
    # Run performance estimates
    estimate_performance()

    print("\n" + "=" * 50)
    print("Example usage:")
    print("python examples/increased_limits_bank_example.py")
    print("=" * 50)
