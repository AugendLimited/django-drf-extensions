import random
import string
import time
import requests
from datetime import UTC
from datetime import datetime
from datetime import timedelta

CHUNK_SIZE = 4000


def generate_transactions_unique_datetime(total_transaction_count):
    start_datetime = datetime.now(UTC) - timedelta(seconds=total_transaction_count)
    transactions_to_return = []
    for transaction_index in range(total_transaction_count):
        unique_datetime = start_datetime + timedelta(seconds=transaction_index)
        transactions_to_return.append(
            {
                "amount": round(random.uniform(10, 1000), 2),
                "datetime": unique_datetime.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "financial_account": 1,
            }
        )
    return transactions_to_return


TOTAL_TRANSACTIONS = 8000
transactions_data = generate_transactions_unique_datetime(TOTAL_TRANSACTIONS)


def upload_transactions_async():
    """Upload transactions using async bulk endpoints for better performance."""
    
    token = "26259b93ba854bf476eb75f851a5629c0665e6a3"
    headers = {
        "Authorization": f"Token {token}",
        "accept": "application/json",
        "Content-Type": "application/json",
    }
    
    base_url = "http://localhost:8000"  # Adjust to your server URL
    
    print("Starting async bulk upload...")
    start_time = time.time()
    
    # Send all data to async bulk endpoint
    response = requests.patch(
        f"{base_url}/api/financial-transactions/bulk/?unique_fields=financial_account,datetime,amount",
        json=transactions_data,
        headers=headers,
    )
    
    if response.status_code == 202:  # Accepted for async processing
        task_data = response.json()
        task_id = task_data.get('task_id')
        status_url = task_data.get('status_url')
        
        print(f"Async task started: {task_id}")
        print(f"Status URL: {status_url}")
        
        # Poll for completion
        while True:
            status_response = requests.get(
                f"{base_url}{status_url}",
                headers=headers
            )
            
            if status_response.status_code == 200:
                status_data = status_response.json()
                status = status_data.get('status')
                progress = status_data.get('progress', {})
                
                print(f"Status: {status}")
                if progress:
                    print(f"Progress: {progress.get('processed', 0)}/{progress.get('total', 0)} items")
                
                if status in ['completed', 'failed']:
                    print(f"Final result: {status_data}")
                    break
                    
            time.sleep(2)  # Poll every 2 seconds
    else:
        print(f"Failed to start async task: {response.status_code}")
        print(f"Response: {response.text}")
    
    total_time = time.time() - start_time
    print(f"Total time: {total_time:.2f} seconds")


def upload_transactions_sync_optimized():
    """Upload transactions using optimized sync approach with smaller chunks."""
    
    token = "26259b93ba854bf476eb75f851a5629c0665e6a3"
    headers = {
        "Authorization": f"Token {token}",
        "accept": "application/json",
        "Content-Type": "application/json",
    }
    
    base_url = "http://localhost:8000"  # Adjust to your server URL
    
    # Use smaller chunks for sync operations (within the 50-item limit)
    SYNC_CHUNK_SIZE = 50
    
    print("Starting optimized sync upload...")
    start_time = time.time()
    
    for chunk_start_index in range(0, len(transactions_data), SYNC_CHUNK_SIZE):
        chunk_end_index = min(chunk_start_index + SYNC_CHUNK_SIZE, len(transactions_data))
        transaction_chunk = transactions_data[chunk_start_index:chunk_end_index]
        
        chunk_num = (chunk_start_index // SYNC_CHUNK_SIZE) + 1
        total_chunks = (len(transactions_data) + SYNC_CHUNK_SIZE - 1) // SYNC_CHUNK_SIZE
        
        print(f"Processing chunk {chunk_num}/{total_chunks} ({len(transaction_chunk)} items)...")
        
        response = requests.patch(
            f"{base_url}/api/financial-transactions/?unique_fields=financial_account,datetime,amount&max_items=50",
            json=transaction_chunk,
            headers=headers,
        )
        
        print(f"Chunk {chunk_num}: Status {response.status_code}, Time: {response.elapsed.total_seconds():.2f}s")
        
        if response.status_code != 200:
            print(f"Error in chunk {chunk_num}: {response.text}")
            break
    
    total_time = time.time() - start_time
    print(f"Total time: {total_time:.2f} seconds")


if __name__ == "__main__":
    print("Choose upload method:")
    print("1. Async bulk upload (recommended for large datasets)")
    print("2. Optimized sync upload (smaller chunks)")
    
    choice = input("Enter choice (1 or 2): ").strip()
    
    if choice == "1":
        upload_transactions_async()
    elif choice == "2":
        upload_transactions_sync_optimized()
    else:
        print("Invalid choice. Using async bulk upload...")
        upload_transactions_async()
