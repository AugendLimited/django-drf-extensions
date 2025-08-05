# Caller Visibility Guide: Understanding Bulk Operations

This guide explains the **best practices** for callers to understand and monitor bulk operations in the enhanced Django DRF Extensions system.

## 🎯 Overview

The enhanced bulk processing system provides **multi-layered visibility** to help callers understand exactly what's happening during bulk operations:

1. **Immediate Response** - What's happening right now
2. **Real-time Progress** - Live status updates with intelligent polling
3. **Clear Next Steps** - What to do next at each stage
4. **Error Handling** - How to handle failures and retries

## 📋 Initial Response (What's Happening Now)

When you start a bulk operation, you get an immediate response with all the information you need:

```json
{
  "message": "Enhanced bulk create job started for 1000 items",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "task_id": "task-123",
  "total_items": 1000,
  "status_url": "/api/jobs/550e8400-e29b-41d4-a716-446655440000/status/",
  "aggregates_url": "/api/jobs/550e8400-e29b-41d4-a716-446655440000/aggregates/",
  "estimated_duration": "1-2 minutes",
  "next_steps": [
    "Poll status_url every 10 seconds for progress updates",
    "Check aggregates_url when status shows 'Job Complete'",
    "Review any errors in the status response"
  ],
  "tips": [
    "Large batches (>10k items) may take several minutes",
    "You can safely poll status_url frequently",
    "Aggregates are automatically calculated when job completes"
  ]
}
```

### Key Information Provided:
- **Job ID**: Unique identifier for tracking
- **Estimated Duration**: Rough time estimate based on batch size
- **Next Steps**: Clear instructions on what to do
- **Tips**: Best practices and expectations

## 🔍 Real-time Progress Monitoring

### Status Response Format

When you poll the status URL, you get detailed progress information:

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "job_type": "insert",
  "state": "In Progress",
  "status": "processing",
  "message": "Processing 500 of 1000 items (50.0% complete)",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:30Z",
  "completed_at": null,
  "total_items": 1000,
  "processed_items": 500,
  "success_count": 495,
  "error_count": 5,
  "percentage": 50.0,
  "estimated_remaining": "30 seconds",
  "aggregates_ready": false,
  "aggregates_completed": false,
  "next_steps": [
    "Continue polling every 10 seconds",
    "Estimated completion: 30 seconds"
  ],
  "can_retry": false,
  "errors": null
}
```

### Job States Explained

| State | Status | Meaning | Next Steps |
|-------|--------|---------|------------|
| `Open` | `queued` | Job created, waiting to start | Wait for processing to begin |
| `In Progress` | `processing` | Actively processing items | Continue polling, check estimated time |
| `Job Complete` | `completed` | Successfully finished | Get aggregates, review results |
| `Failed` | `failed` | Job failed with errors | Review errors, consider retry |
| `Aborted` | `aborted` | Manually stopped | Review why aborted, restart if needed |

## 🚀 Best Practices for Callers

### 1. Intelligent Polling Strategy

```python
import requests
import time

def monitor_bulk_job(base_url, job_id, max_wait_time=300):
    """Monitor job with intelligent polling."""
    start_time = time.time()
    poll_interval = 2  # Start with 2 seconds
    
    while True:
        # Check timeout
        if time.time() - start_time > max_wait_time:
            raise TimeoutError(f"Job {job_id} did not complete within {max_wait_time} seconds")
        
        # Get status
        response = requests.get(f"{base_url}/api/jobs/{job_id}/status/")
        status_data = response.json()
        
        # Print progress
        print(f"🔄 {status_data['message']}")
        if status_data.get('estimated_remaining'):
            print(f"   ⏱️  {status_data['estimated_remaining']} remaining")
        
        # Check if complete
        if status_data["state"] in ["Job Complete", "Failed", "Aborted"]:
            return status_data
        
        # Intelligent backoff
        if status_data["percentage"] > 50:
            poll_interval = min(poll_interval * 1.5, 10)
        elif status_data["percentage"] > 25:
            poll_interval = min(poll_interval * 1.2, 5)
        
        time.sleep(poll_interval)
```

### 2. Error Handling and Retry

```python
def handle_job_with_retry(base_url, job_id, max_retries=3):
    """Handle job completion with retry logic."""
    
    for attempt in range(max_retries):
        try:
            status = monitor_bulk_job(base_url, job_id)
            
            if status["state"] == "Job Complete":
                print(f"✅ Job completed successfully!")
                print(f"   📊 Success: {status['success_count']}, Errors: {status['error_count']}")
                return status
            elif status["state"] == "Failed":
                print(f"❌ Job failed: {status.get('errors', 'Unknown error')}")
                if attempt < max_retries - 1:
                    print(f"🔄 Retrying... (attempt {attempt + 2}/{max_retries})")
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    raise Exception("All retry attempts failed")
            else:
                print(f"⏹️  Job aborted")
                return status
                
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            print(f"⚠️  Attempt {attempt + 1} failed: {e}")
            time.sleep(2 ** attempt)
```

### 3. Batch Processing with Progress Tracking

```python
def process_large_dataset(base_url, data, batch_size=100):
    """Process large datasets in batches with progress tracking."""
    
    batches = [data[i:i + batch_size] for i in range(0, len(data), batch_size)]
    results = []
    
    print(f"📦 Processing {len(data)} items in {len(batches)} batches...")
    
    for i, batch in enumerate(batches, 1):
        print(f"\n🔄 Batch {i}/{len(batches)} ({len(batch)} items)...")
        
        # Start batch
        response = requests.post(f"{base_url}/api/transactions/bulk/", json=batch)
        job_info = response.json()
        
        # Monitor batch
        status = monitor_bulk_job(base_url, job_info["job_id"])
        
        if status["state"] == "Job Complete":
            results.append({
                "batch": i,
                "success_count": status["success_count"],
                "error_count": status["error_count"]
            })
            print(f"✅ Batch {i} completed")
        else:
            print(f"❌ Batch {i} failed: {status['state']}")
    
    return results
```

## 📊 Understanding Results

### Successful Completion

When a job completes successfully:

```json
{
  "state": "Job Complete",
  "status": "completed",
  "message": "Job completed successfully! Processed 1000 items with 5 errors",
  "success_count": 995,
  "error_count": 5,
  "percentage": 100.0,
  "aggregates_ready": true,
  "aggregates_completed": true,
  "next_steps": [
    "Check aggregates_url for results",
    "Review any errors in the response"
  ]
}
```

### Getting Aggregate Results

```python
# Get aggregate results
response = requests.get(f"{base_url}/api/jobs/{job_id}/aggregates/")
aggregates = response.json()

print("📊 Aggregate Results:")
print(json.dumps(aggregates, indent=2))
```

Example aggregate response:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "aggregate_results": {
    "total_amount": 150000.00,
    "average_amount": 150.00,
    "transaction_count": 1000,
    "successful_transactions": 995,
    "failed_transactions": 5
  }
}
```

## ⚠️ Error Handling

### Common Error Scenarios

1. **Job Not Found**
   ```json
   {"error": "Job not found"}
   ```
   - **Cause**: Job ID is invalid or job has expired
   - **Solution**: Check job ID, restart operation if needed

2. **Job Failed**
   ```json
   {
     "state": "Failed",
     "message": "Job failed after processing 500 items",
     "errors": ["Database connection lost", "Invalid data format"]
   }
   ```
   - **Cause**: Database issues, invalid data, system errors
   - **Solution**: Review errors, fix data, retry with smaller batch

3. **Aggregates Not Ready**
   ```json
   {"error": "Job not ready for aggregates", "state": "In Progress"}
   ```
   - **Cause**: Job is still running
   - **Solution**: Wait for job completion, then retry

### Retry Strategies

1. **Immediate Retry**: For transient network issues
2. **Exponential Backoff**: For persistent issues (1s, 2s, 4s delays)
3. **Smaller Batch Size**: For data validation errors
4. **Manual Review**: For complex data issues

## 🎯 Summary: The Best Approach

The **best way for callers to understand what's happening** is:

1. **Start with the enhanced response** - Get job ID and URLs immediately
2. **Use intelligent polling** - Start frequent, then back off as job progresses
3. **Follow the next_steps** - The API tells you exactly what to do
4. **Handle errors gracefully** - Use retry strategies and error analysis
5. **Get aggregates when complete** - Automatic calculation of results

This approach provides:
- ✅ **Immediate feedback** on job creation
- ✅ **Real-time progress** with estimated completion times
- ✅ **Clear next steps** at every stage
- ✅ **Comprehensive error handling** with retry strategies
- ✅ **Automatic aggregate calculation** when jobs complete

The system is designed to be **self-documenting** - the responses tell you exactly what's happening and what to do next! 