# Transaction Processing Pipeline

## Overview

The Transaction Processing Pipeline provides a **single API call** that handles the complete workflow internally:

1. **Import transactions** (your 29GB file)
2. **Aggregate data** (daily financial aggregates)
3. **Run credit model** (on aggregated data)
4. **Generate offers** (based on credit model results)

The caller simply sends transaction data and gets back offers when the pipeline completes.

## API Endpoint

### Process Transactions Pipeline

```
POST /api/financial-transactions/process-transactions/
```

**Request Body:**
```json
{
    "data": [
        {
            "amount": 1500.00,
            "date": "2024-01-15",
            "is_revenue": true,
            "description": "Revenue transaction"
        }
        // ... your 29GB worth of transactions
    ],
    "credit_model_config": {
        "model_version": "v2.1",
        "risk_threshold": 0.7,
        "credit_score_weights": {
            "transaction_volume": 0.4,
            "revenue_ratio": 0.3,
            "consistency": 0.3
        }
    },
    "aggregate_config": {
        "group_by": "date",
        "include_metrics": ["total_amount", "revenue_amount", "transaction_count"],
        "date_range": "last_30_days"
    }
}
```

**Response (202 Accepted):**
```json
{
    "job_id": "pipeline_20241201_001",
    "status_url": "/api/jobs/pipeline_20241201_001/status/",
    "offers_url": "/api/jobs/pipeline_20241201_001/offers/",
    "estimated_duration": "5-10 minutes",
    "next_steps": "Monitor job status. Offers will be available when pipeline completes.",
    "tips": "Use the offers_url endpoint to retrieve results when job is complete"
}
```

### Get Pipeline Results

```
GET /api/jobs/{job_id}/offers/
```

**Response (200 OK):**
```json
{
    "offers": [
        {
            "date": "2024-01-15",
            "offer_type": "credit_line",
            "amount": 10000,
            "interest_rate": 0.05,
            "credit_score": 750,
            "risk_level": "LOW",
            "transaction_count": 2
        }
    ],
    "pipeline_summary": {
        "transactions_processed": 1000,
        "aggregates_created": 30,
        "offers_generated": 30
    },
    "credit_model_results": {
        "credit_scores": {"2024-01-15": 750, "2024-01-16": 720},
        "risk_assessments": {"2024-01-15": "LOW", "2024-01-16": "MEDIUM"},
        "model_version": "v2.1",
        "config_used": {...}
    }
}
```

## Pipeline Stages

### 1. Transaction Import
- Uses your enhanced bulk create system
- No database locks during import
- Tracks created transaction IDs
- Updates job state with progress

### 2. Data Aggregation
- Runs after ALL transactions are imported
- Creates `DailyFinancialAggregates` by date
- No foreign key complexity - aggregates by date
- Ensures data consistency

### 3. Credit Model Processing
- Runs on aggregated data only
- Calculates credit scores per date
- Assesses risk levels
- Uses configurable model parameters

### 4. Offer Generation
- Creates offers based on credit model results
- One offer per date with aggregated data
- Includes credit score, risk level, and transaction count

## Job State Tracking

The pipeline uses the same job state system as your bulk operations:

- **OPEN**: Pipeline created
- **IN_PROGRESS**: Processing transactions/aggregating/running credit model
- **JOB_COMPLETE**: Pipeline finished, offers ready
- **FAILED**: Pipeline failed with errors

## Monitoring Options

### 1. Polling (Traditional)
```python
# Check status periodically
response = requests.get(f"/api/jobs/{job_id}/status/")
status = response.json()
print(f"Status: {status['status']}")
```

### 2. Event Notifications (Real-time)
```python
# Use Server-Sent Events
response = requests.get(f"/api/jobs/{job_id}/events/", stream=True)
for line in response.iter_lines():
    if line.startswith(b'data: '):
        event = json.loads(line[6:])
        print(f"Event: {event['event_type']}")
```

### 3. Webhooks
```python
# Register webhook for job completion
requests.post("/api/jobs/webhooks/register/", json={
    "job_id": job_id,
    "webhook_url": "https://your-app.com/webhooks/pipeline-complete",
    "events": ["JOB_COMPLETE"]
})
```

## Implementation Details

### Pipeline Task
The `process_transactions_pipeline_task` orchestrates the entire workflow:

1. **Import Phase**: Uses `enhanced_create_task` for transaction import
2. **Aggregate Phase**: Calls `run_daily_financial_aggregates` 
3. **Credit Model Phase**: Runs `run_credit_model_task`
4. **Offer Phase**: Calls `generate_offers_task`

### Credit Model Integration
The pipeline includes placeholder functions for your credit model:

- `calculate_credit_score()`: Implement your scoring logic
- `assess_risk()`: Implement your risk assessment
- `generate_offer_for_date()`: Implement your offer generation

### Database Design
Recommended structure for your models:

```python
class FinancialTransaction(models.Model):
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    date = models.DateField()
    is_revenue = models.BooleanField()
    description = models.CharField(max_length=255)

class DailyFinancialAggregates(models.Model):
    date = models.DateField(unique=True)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)
    revenue_amount = models.DecimalField(max_digits=15, decimal_places=2)
    transaction_count = models.IntegerField()
    # No FK to FinancialTransaction - aggregate by date
```

## Benefits

### For Your 29GB File Import
- **No locks during import**: Transactions insert without blocking
- **Controlled aggregation**: Only runs after ALL transactions are imported
- **Consistent data**: Aggregates see complete, consistent dataset
- **Scalable**: Can handle large files in chunks

### For Your Business Logic
- **Single API call**: Caller doesn't need to orchestrate multiple steps
- **Internal orchestration**: All steps happen automatically
- **Configurable**: Credit model and aggregation settings
- **Trackable**: Full job state tracking and monitoring

### For Your Architecture
- **Event-driven**: Real-time notifications when pipeline completes
- **Resilient**: Job state tracking with retry capabilities
- **Extensible**: Easy to add new pipeline stages
- **Observable**: Detailed progress and error reporting

## Usage Example

See `examples/transaction_pipeline_example.py` for a complete working example that demonstrates:

- Sending transactions to the pipeline
- Monitoring progress via polling or events
- Retrieving final offers
- Error handling and retry logic

## Next Steps

1. **Implement your credit model logic** in the placeholder functions
2. **Customize offer generation** based on your business rules
3. **Add your specific aggregation logic** for `DailyFinancialAggregates`
4. **Configure event notifications** for your preferred monitoring method
5. **Test with your 29GB file** using chunked processing if needed

This pipeline gives you the **speed** (no locks), **reliability** (job state tracking), and **simplicity** (single API call) you need for your large-scale transaction processing. 