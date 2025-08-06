# Large Dataset Processing Approaches

## **96K Transactions - Can it work in a single request?**

### **❌ Single Request Approach (NOT RECOMMENDED)**

**Problems:**
- **Request Size**: ~15-20MB (exceeds Django's 2.5MB default)
- **Memory Pressure**: Web server memory exhaustion
- **Timeout Risks**: Upload timeouts, processing timeouts
- **Celery Limits**: Redis message size limits
- **Database Issues**: Connection timeouts, memory pressure

**Technical Limits:**
```python
# 96K transactions estimate
per_transaction = 150 bytes  # JSON overhead
total_size = 96000 * 150 = 14.4MB
with_overhead = ~15-20MB

# Common limits
django_default = 2.5MB
nginx_default = 1MB
load_balancer = 10-50MB
celery_message = 1MB
```

### **✅ Chunked Upload Approach (RECOMMENDED)**

**How it works:**
1. **Split data** into 10K transaction chunks
2. **Upload chunks** sequentially with progress tracking
3. **Redis storage** for temporary chunk assembly
4. **Single processing** once all chunks received

**Benefits:**
- ✅ **Bypasses request size limits**
- ✅ **Progress tracking** during upload
- ✅ **Resume capability** if chunks fail
- ✅ **Memory efficient** processing
- ✅ **Same final result** as single request

## **Approach Comparison**

| Approach | Request Size | Memory | Reliability | Complexity | Performance |
|----------|-------------|---------|-------------|------------|-------------|
| **Single Request** | ❌ 15-20MB | ❌ High | ❌ Low | ✅ Simple | ❌ Poor |
| **Chunked Upload** | ✅ 1-2MB | ✅ Low | ✅ High | ⚠️ Medium | ✅ Good |
| **File Upload** | ✅ Any size | ✅ Low | ✅ High | ⚠️ Medium | ✅ Good |
| **Streaming** | ✅ Unlimited | ✅ Low | ✅ High | ❌ Complex | ✅ Excellent |

## **Chunked Upload Implementation**

### **Endpoint:**
```http
POST /api/financial-transactions/upload-chunked/
```

### **Request Format:**
```json
{
  "chunk_data": [...],           // Max 10K transactions
  "chunk_number": 1,             // 1-based chunk number
  "total_chunks": 10,            // Total chunks expected
  "session_id": "uuid-string",   // Unique session
  "credit_model_config": {...},   // Credit model settings
  "aggregate_config": {...}       // Aggregation settings
}
```

### **Response (More chunks expected):**
```json
{
  "session_id": "uuid-string",
  "chunk_received": 1,
  "total_chunks": 10,
  "progress": 10.0,
  "next_chunk": 2,
  "message": "Chunk 1 received, waiting for more chunks"
}
```

### **Response (All chunks received):**
```json
{
  "session_id": "uuid-string",
  "job_id": "job_abc123",
  "status_url": "/api/jobs/job_abc123/status/",
  "offers_url": "/api/jobs/job_abc123/offers/",
  "estimated_duration": "50-65 minutes",
  "total_transactions": 96000,
  "message": "All chunks received, processing started"
}
```

## **Usage Examples**

### **Python Client:**
```python
import requests
import uuid

def upload_96k_transactions(api_url, transactions):
    session_id = str(uuid.uuid4())
    chunks = [transactions[i:i+10000] for i in range(0, len(transactions), 10000)]
    
    for chunk_num, chunk_data in enumerate(chunks, 1):
        payload = {
            "chunk_data": chunk_data,
            "chunk_number": chunk_num,
            "total_chunks": len(chunks),
            "session_id": session_id,
            "credit_model_config": {"rolling_period": 12},
            "aggregate_config": {"group_by": ["account_id", "date"]}
        }
        
        response = requests.post(f"{api_url}/upload-chunked/", json=payload)
        
        if response.status_code == 200:
            # All chunks uploaded, processing started
            job_id = response.json()["job_id"]
            return job_id
        elif response.status_code == 202:
            # More chunks to upload
            continue
        else:
            raise Exception(f"Upload failed: {response.text}")
```

### **JavaScript Client:**
```javascript
async function uploadChunked(apiUrl, transactions) {
    const sessionId = crypto.randomUUID();
    const chunkSize = 10000;
    const chunks = [];
    
    // Split into chunks
    for (let i = 0; i < transactions.length; i += chunkSize) {
        chunks.push(transactions.slice(i, i + chunkSize));
    }
    
    // Upload chunks
    for (let chunkNum = 1; chunkNum <= chunks.length; chunkNum++) {
        const payload = {
            chunk_data: chunks[chunkNum - 1],
            chunk_number: chunkNum,
            total_chunks: chunks.length,
            session_id: sessionId,
            credit_model_config: { rolling_period: 12 },
            aggregate_config: { group_by: ["account_id", "date"] }
        };
        
        const response = await fetch(`${apiUrl}/upload-chunked/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        const data = await response.json();
        
        if (response.status === 200) {
            // All chunks uploaded
            return data.job_id;
        } else if (response.status === 202) {
            // More chunks to upload
            console.log(`Progress: ${data.progress}%`);
            continue;
        } else {
            throw new Error(`Upload failed: ${data.error}`);
        }
    }
}
```

## **Alternative Approaches**

### **1. File Upload Approach**
```http
POST /api/financial-transactions/upload-file/
Content-Type: multipart/form-data

file: transactions.csv
credit_model_config: {...}
aggregate_config: {...}
```

**Pros:** No request size limits, standard file upload
**Cons:** Requires file parsing, more complex

### **2. Streaming Upload**
```http
POST /api/financial-transactions/stream-upload/
Content-Type: application/octet-stream

[streaming transaction data]
```

**Pros:** Unlimited size, real-time processing
**Cons:** Complex implementation, requires streaming parser

### **3. Database Direct Import**
```python
# Bypass API, import directly to database
from django.db import connection

with connection.cursor() as cursor:
    cursor.executemany(
        "INSERT INTO financial_transactions (...) VALUES (...)",
        transaction_data
    )
```

**Pros:** Fastest, bypasses API overhead
**Cons:** Bypasses validation, security concerns

## **Performance Estimates for 96K Transactions**

### **Chunked Upload:**
```
Upload: 10 chunks × 2 seconds = 20 seconds
Processing: 50-65 minutes (hybrid approach)
Total: ~55-65 minutes
```

### **Single Request (if it worked):**
```
Upload: 15-20MB = 30-60 seconds
Processing: 50-65 minutes
Total: ~55-65 minutes
```

### **File Upload:**
```
Upload: 15-20MB file = 30-60 seconds
Processing: 50-65 minutes
Total: ~55-65 minutes
```

## **Recommendation**

**For 96K transactions, use the Chunked Upload approach:**

✅ **Reliable**: Bypasses all size limits  
✅ **Scalable**: Works for any dataset size  
✅ **Progress tracking**: Real-time upload progress  
✅ **Error handling**: Resume capability  
✅ **Same result**: Identical to single request  

**Implementation priority:**
1. **Chunked Upload** (implemented above)
2. **File Upload** (fallback option)
3. **Streaming Upload** (future enhancement)

The chunked approach gives you the **best balance** of reliability, performance, and user experience for large datasets! 🎯 