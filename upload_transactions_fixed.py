import random
import string
from datetime import UTC
from datetime import datetime
from datetime import timedelta

from locust import HttpUser
from locust.exception import StopUser
from locust import task


# Use smaller chunks for sync operations (within the 50-item limit)
SYNC_CHUNK_SIZE = 50


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


class FinancialTransactionUser(HttpUser):
    def wait_time(self):
        return 0

    token = "26259b93ba854bf476eb75f851a5629c0665e6a3"
    headers = {
        "Authorization": f"Token {token}",
        "accept": "application/json",
        "Content-Type": "application/json",
    }

    def on_start(self):
        # This runs only once per user, immediately upon spawning.
        print(f"Starting upload of {len(transactions_data)} transactions in {SYNC_CHUNK_SIZE}-item chunks...")
        
        for transaction_chunk_start_index in range(0, len(transactions_data), SYNC_CHUNK_SIZE):
            transaction_chunk = transactions_data[
                transaction_chunk_start_index : transaction_chunk_start_index + SYNC_CHUNK_SIZE
            ]
            
            chunk_num = (transaction_chunk_start_index // SYNC_CHUNK_SIZE) + 1
            total_chunks = (len(transactions_data) + SYNC_CHUNK_SIZE - 1) // SYNC_CHUNK_SIZE
            
            print(f"Processing chunk {chunk_num}/{total_chunks} ({len(transaction_chunk)} items)...")
            
            response = self.client.patch(
                f"/api/financial-transactions/?unique_fields=financial_account,datetime,amount&max_items={SYNC_CHUNK_SIZE}",
                json=transaction_chunk,
                headers=self.headers,
            )
            
            print(
                f"Chunk {chunk_num}: Status code: {response.status_code}, "
                f"Time: {response.elapsed.total_seconds():.2f}s"
            )
            
            if response.status_code != 200:
                print(f"Error in chunk {chunk_num}: {response.text}")
                break

        # After sending all chunks, stop this user to avoid re-running
        raise StopUser()
