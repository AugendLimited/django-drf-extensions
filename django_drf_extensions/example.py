"""
Example script demonstrating how to use the DRF extensions endpoints.

This script shows how to:
1. Create multiple financial transactions using async create
2. Update multiple financial transactions using async update
3. Delete multiple financial transactions using async delete
4. Perform synchronous upserts for immediate results
5. Track progress using the status endpoint

Run this script from a Django shell or as a management command.
"""
import time
import csv

import requests


class DRFExtensionsExample:
    """Example class demonstrating DRF extensions usage."""

    def __init__(self, base_url: str = "http://localhost:8000/api"):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        # Add authentication if needed
        # self.session.headers.update({'Authorization': 'Token your-token-here'})

    def async_create_financial_transactions(self, transactions_data: list[dict]) -> str:
        """
        Create multiple financial transactions using async endpoint with POST method.

        Args:
            transactions_data: List of transaction data dictionaries

        Returns:
            Task ID for tracking the operation
        """
        url = f"{self.base_url}/financial-transactions/operations/"
        response = self.session.post(url, json=transactions_data)
        
        if response.status_code == 202:
            result = response.json()
            print(f"✅ Async create started: {result['message']}")
            print(f"📋 Task ID: {result['task_id']}")
            print(f"🔗 Status URL: {result['status_url']}")
            return result["task_id"]
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")
            return ""

    def async_update_financial_transactions(self, updates_data: list[dict]) -> str:
        """
        Update multiple financial transactions using async endpoint with PATCH method.

        Args:
            updates_data: List of update data dictionaries (must include 'id' field)

        Returns:
            Task ID for tracking the operation
        """
        url = f"{self.base_url}/financial-transactions/operations/"
        response = self.session.patch(url, json=updates_data)
        
        if response.status_code == 202:
            result = response.json()
            print(f"✅ Async update started: {result['message']}")
            print(f"📋 Task ID: {result['task_id']}")
            print(f"🔗 Status URL: {result['status_url']}")
            return result["task_id"]
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")
            return ""

    def async_replace_financial_transactions(self, replacement_data: list[dict]) -> str:
        """
        Replace multiple financial transactions using async endpoint with PUT method.

        Args:
            replacement_data: List of complete transaction data dictionaries (must include 'id' field)

        Returns:
            Task ID for tracking the operation
        """
        url = f"{self.base_url}/financial-transactions/operations/"
        response = self.session.put(url, json=replacement_data)
        
        if response.status_code == 202:
            result = response.json()
            print(f"✅ Async replace started: {result['message']}")
            print(f"📋 Task ID: {result['task_id']}")
            print(f"🔗 Status URL: {result['status_url']}")
            return result["task_id"]
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")
            return ""

    def async_delete_financial_transactions(self, ids_to_delete: list[int]) -> str:
        """
        Delete multiple financial transactions using async endpoint with DELETE method.

        Args:
            ids_to_delete: List of transaction IDs to delete

        Returns:
            Task ID for tracking the operation
        """
        url = f"{self.base_url}/financial-transactions/operations/"
        response = self.session.delete(url, json=ids_to_delete)
        
        if response.status_code == 202:
            result = response.json()
            print(f"✅ Async delete started: {result['message']}")
            print(f"📋 Task ID: {result['task_id']}")
            print(f"🔗 Status URL: {result['status_url']}")
            return result["task_id"]
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")
            return ""

    def async_retrieve_financial_transactions(self, ids: list[int] = None, filters: dict = None) -> dict:
        """
        Retrieve multiple financial transactions using async endpoint.

        Args:
            ids: List of IDs to retrieve (for small lists, returns data directly)
            filters: Complex filters for advanced queries

        Returns:
            Either direct data (small result sets) or task information (large result sets)
        """
        url = f"{self.base_url}/financial-transactions/operations/"
        
        if ids:
            # ID-based retrieval
            ids_str = ",".join(map(str, ids))
            response = self.session.get(f"{url}?ids={ids_str}")
        elif filters:
            # Complex query via request body
            response = self.session.get(url, json=filters)
        else:
            print("❌ Error: Provide either ids or filters")
            return {}
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Retrieved {result['count']} records directly")
            return result
        elif response.status_code == 202:
            result = response.json()
            print(f"✅ Async retrieve started: {result['message']}")
            print(f"📋 Task ID: {result['task_id']}")
            print(f"🔗 Status URL: {result['status_url']}")
            return result
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")
            return {}

    def async_upsert_financial_transactions(self, data, unique_fields: list[str], salesforce_style: bool = True) -> str:
        """
        Upsert multiple financial transactions using PATCH async endpoint.
        
        Similar to Django's bulk_create with update_conflicts=True, this will create
        new records or update existing ones based on unique field constraints.

        Args:
            data: Single object or list of transaction data dictionaries
            unique_fields: List of field names that form the unique constraint
            salesforce_style: If True, use query params (default). If False, use legacy body structure.

        Returns:
            Task ID for tracking the operation
        """
        url = f"{self.base_url}/financial-transactions/operations/"
        
        if salesforce_style:
            # Salesforce-style: unique_fields in query params, data as payload
            params = {"unique_fields": ",".join(unique_fields)}
            response = self.session.patch(url, json=data, params=params)
        else:
            # Legacy style: structured body with data, unique_fields, update_fields
            payload = {
                "data": data,
                "unique_fields": unique_fields,
            }
            response = self.session.patch(url, json=payload)
        
        if response.status_code == 202:
            result = response.json()
            print(f"✅ Async upsert started: {result['message']}")
            print(f"📋 Task ID: {result['task_id']}")
            print(f"🔗 Status URL: {result['status_url']}")
            print(f"🔑 Unique fields: {unique_fields}")
            style = "Salesforce-style" if salesforce_style else "Legacy-style"
            print(f"🎯 Style: {style}")
            return result["task_id"]
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")
            return ""

    def async_upsert_csv_financial_transactions(self, csv_file_path: str, unique_fields: list[str], update_fields: list[str] = None) -> dict:
        """
        Upsert multiple financial transactions from CSV file using PATCH async endpoint.
        
        Note: CSV upsert uses form data approach (unique_fields in form data).

        Args:
            csv_file_path: Path to the CSV file
            unique_fields: List of field names that form the unique constraint
            update_fields: Optional list of field names to update on conflict (auto-inferred if not provided)

        Returns:
            Response data with task information
        """
        url = f"{self.base_url}/financial-transactions/operations/"
        
        with open(csv_file_path, 'rb') as csv_file:
            files = {'file': csv_file}
            data = {
                'unique_fields': ','.join(unique_fields),
            }
            if update_fields:
                data['update_fields'] = ','.join(update_fields)
            
            response = self.session.patch(url, files=files, data=data)
        
        if response.status_code == 202:
            result = response.json()
            print(f"✅ Async upsert from CSV started: {result['message']}")
            print(f"📋 Task ID: {result['task_id']}")
            print(f"📁 Source file: {result['source_file']}")
            print(f"🔑 Unique fields: {result['unique_fields']}")
            if result.get('update_fields'):
                print(f"📝 Update fields: {result['update_fields']}")
            return result
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")
            return {}

    def sync_upsert_financial_transactions(self, data, unique_fields: list[str], update_fields: list[str] = None, max_items: int = 50) -> dict:
        """
        Synchronously upsert financial transactions using the sync upsert endpoint.
        
        Returns immediate results without async processing - great for small datasets.

        Args:
            data: Single object or list of transaction data dictionaries
            unique_fields: List of field names that form the unique constraint
            update_fields: Optional list of field names to update on conflict (auto-inferred if not provided)
            max_items: Maximum items to process synchronously

        Returns:
            Immediate response with results
        """
        url = f"{self.base_url}/financial-transactions/upsert/"
        
        # Build query parameters
        params = {"unique_fields": ",".join(unique_fields)}
        if update_fields:
            params["update_fields"] = ",".join(update_fields)
        if max_items != 50:
            params["max_items"] = str(max_items)
        
        response = self.session.post(url, json=data, params=params)
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Sync upsert completed: {result['message']}")
            print(f"📊 Results:")
            print(f"   • Total items: {result['total_items']}")
            print(f"   • Created: {result['created_count']} (IDs: {result['created_ids']})")
            print(f"   • Updated: {result['updated_count']} (IDs: {result['updated_ids']})")
            print(f"   • Errors: {result['error_count']}")
            if result['errors']:
                print(f"   • Error details: {result['errors']}")
            print(f"🔑 Unique fields: {result['unique_fields']}")
            print(f"📝 Update fields: {result['update_fields']}")
            return result
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")
            return {}

    def sync_upsert_single_transaction(self, transaction_data: dict, unique_fields: list[str]) -> dict:
        """
        Synchronously upsert a single financial transaction.
        
        Convenience method for single-item upserts with immediate results.

        Args:
            transaction_data: Single transaction data dictionary
            unique_fields: List of field names that form the unique constraint

        Returns:
            Immediate response with results
        """
        return self.sync_upsert_financial_transactions(
            data=transaction_data,  # Single object, not array
            unique_fields=unique_fields
        )

    def check_task_status(self, task_id: str) -> dict:
        """
        Check the status of an async operation task.

        Args:
            task_id: The task ID returned from async operations

        Returns:
            Task status information
        """
        url = f"{self.base_url}/operations/{task_id}/status/"
        response = self.session.get(url)
        
        if response.status_code == 200:
            result = response.json()
            print(f"📊 Task {task_id} Status: {result['status']}")
            if 'progress' in result:
                progress = result['progress']
                print(f"📈 Progress: {progress['current']}/{progress['total']} ({progress['percentage']}%)")
            if result['status'] == 'completed' and 'result' in result:
                task_result = result['result']
                print(f"✅ Operation completed successfully!")
                if 'success_count' in task_result:
                    print(f"   • Success: {task_result['success_count']}")
                if 'error_count' in task_result:
                    print(f"   • Errors: {task_result['error_count']}")
            return result
        else:
            print(f"❌ Error checking status: {response.status_code} - {response.text}")
            return {}

    def wait_for_completion(self, task_id: str, max_wait_seconds: int = 300, poll_interval: int = 2) -> dict:
        """
        Wait for an async task to complete.

        Args:
            task_id: The task ID to wait for
            max_wait_seconds: Maximum time to wait (default: 5 minutes)
            poll_interval: How often to check status (default: 2 seconds)

        Returns:
            Final task result
        """
        print(f"⏳ Waiting for task {task_id} to complete...")
        start_time = time.time()
        
        while time.time() - start_time < max_wait_seconds:
            status_result = self.check_task_status(task_id)
            
            if not status_result:
                print("❌ Failed to get task status")
                break
            
            if status_result['status'] in ['completed', 'failed', 'cancelled']:
                print(f"🏁 Task finished with status: {status_result['status']}")
                return status_result
            
            print(f"⏱️  Task still {status_result['status']}, checking again in {poll_interval}s...")
            time.sleep(poll_interval)
        
        print(f"⏰ Timeout waiting for task {task_id}")
        return self.check_task_status(task_id)


def run_example():
    """Run the comprehensive DRF extensions example."""
    
    # Initialize the example client
    example = DRFExtensionsExample()
    
    print("🚀 Django DRF Extensions Example")
    print("=" * 50)
    
    # Example 1: Async Create Financial Transactions
    print("\n📝 Example 1: Async Create Financial Transactions")
    
    create_data = [
        {
            "amount": "100.50",
            "description": "Example transaction 1",
            "datetime": "2025-01-01T10:00:00Z",
            "financial_account": 1,
            "classification_status": 1,
        },
        {
            "amount": "-25.75",
            "description": "Example transaction 2",
            "datetime": "2025-01-01T11:00:00Z",
            "financial_account": 1,
            "classification_status": 1,
        },
    ]
    
    create_task_id = example.async_create_financial_transactions(create_data)
    
    if create_task_id:
        # Wait for completion and get results
        create_result = example.wait_for_completion(create_task_id)
        
        if create_result.get("status") == "completed":
            create_task_result = create_result.get("result", {})
            print(f"📊 Create Results:")
            print(f"   • Created: {create_task_result.get('success_count', 0)}")
            print(f"   • Errors: {create_task_result.get('error_count', 0)}")
            print(f"   • Created IDs: {create_task_result.get('created_ids', [])}")

    # Example 2: Async Update Financial Transactions
    print("\n✏️ Example 2: Async Update Financial Transactions")
    
    update_data = [
        {"id": 1, "amount": "150.00", "description": "Updated transaction 1"},
        {"id": 2, "description": "Updated transaction 2"},
    ]
    
    update_task_id = example.async_update_financial_transactions(update_data)
    
    if update_task_id:
        update_result = example.wait_for_completion(update_task_id)
        
        if update_result.get("status") == "completed":
            update_task_result = update_result.get("result", {})
            print(f"📊 Update Results:")
            print(f"   • Updated: {update_task_result.get('success_count', 0)}")
            print(f"   • Errors: {update_task_result.get('error_count', 0)}")

    # Example 3: Async Retrieve Financial Transactions
    print("\n🔍 Example 3: Async Retrieve Financial Transactions")
    
    # Small ID list (should return directly)
    small_ids = [1, 2, 3, 4, 5]
    retrieve_result = example.async_retrieve_financial_transactions(ids=small_ids)
    
    if retrieve_result.get("count") is not None:
        print(f"📊 Retrieved {retrieve_result['count']} records directly")
    
    # Complex query example
    complex_filters = {
        "filters": {
            "amount": {"gte": "50.00"},
            "datetime": {"gte": "2025-01-01"},
            "financial_account": 1
        }
    }
    
    complex_result = example.async_retrieve_financial_transactions(filters=complex_filters)

    # Example 4: Async Delete Financial Transactions
    print("\n🗑️ Example 4: Async Delete Financial Transactions")
    
    # Delete some transactions (assuming they exist)
    ids_to_delete = [10, 11, 12]  # Use IDs that you know exist
    delete_task_id = example.async_delete_financial_transactions(ids_to_delete)
    
    if delete_task_id:
        delete_result = example.wait_for_completion(delete_task_id)
        
        if delete_result.get("status") == "completed":
            delete_task_result = delete_result.get("result", {})
            print(f"📊 Delete Results:")
            print(f"   • Deleted: {delete_task_result.get('success_count', 0)}")
            print(f"   • Errors: {delete_task_result.get('error_count', 0)}")

    # Example 5: Async Upsert Operations
    print("\n🔄 Example 5: Async Upsert Operations")
    
    # Example 5a: Async upsert with immediate results (small dataset)
    print("\n🔄 Example 5a: Async Upsert - Multiple Items")
    
    async_upsert_data = [
        {
            "amount": "100.50",
            "description": "Async upsert transaction 1",
            "datetime": "2025-01-01T15:00:00Z",
            "financial_account": 1,
            "classification_status": 1,
        },
        {
            "amount": "200.75",
            "description": "Async upsert transaction 2", 
            "datetime": "2025-01-01T16:00:00Z",
            "financial_account": 1,
            "classification_status": 1,
        },
        {
            "amount": "350.00",  # This might update an existing record
            "description": "Async upsert transaction 1 (updated)",
            "datetime": "2025-01-01T15:00:00Z",  # Same datetime as first
            "financial_account": 1,  # Same account as first
            "classification_status": 2,  # Different status
        }
    ]
    
    async_upsert_task_id = example.async_upsert_financial_transactions(
        data=async_upsert_data,
        unique_fields=["financial_account", "datetime"],
        salesforce_style=True  # Use query params approach
    )
    
    if async_upsert_task_id:
        # Wait for completion and get results
        async_upsert_result = example.wait_for_completion(async_upsert_task_id)
        
        if async_upsert_result.get("status") == "completed":
            async_upsert_task_result = async_upsert_result.get("result", {})
            print(f"📊 Async Upsert Results:")
            print(f"   • Created: {len(async_upsert_task_result.get('created_ids', []))}")
            print(f"   • Updated: {len(async_upsert_task_result.get('updated_ids', []))}")
            print(f"   • Errors: {async_upsert_task_result.get('error_count', 0)}")
            print(f"   • Created IDs: {async_upsert_task_result.get('created_ids', [])}")
            print(f"   • Updated IDs: {async_upsert_task_result.get('updated_ids', [])}")

    # Example 6: Synchronous Upsert Operations
    print("\n" + "="*60)
    print("🔄 Example 6: Synchronous Upsert Operations")
    print("="*60)
    
    # Example 6a: Sync upsert with immediate results (small dataset)
    print("\n🔄 Example 6a: Sync Upsert - Multiple Items")
    
    sync_upsert_data = [
        {
            "amount": "150.00",
            "description": "Sync upsert transaction 1",
            "datetime": "2025-01-01T15:00:00Z",
            "financial_account": 1,
            "classification_status": 1,
        },
        {
            "amount": "250.00",
            "description": "Sync upsert transaction 2", 
            "datetime": "2025-01-01T16:00:00Z",
            "financial_account": 1,
            "classification_status": 1,
        },
        {
            "amount": "350.00",  # This might update an existing record
            "description": "Sync upsert transaction 1 (updated)",
            "datetime": "2025-01-01T15:00:00Z",  # Same datetime as first
            "financial_account": 1,  # Same account as first
            "classification_status": 2,  # Different status
        }
    ]
    
    sync_result = example.sync_upsert_financial_transactions(
        data=sync_upsert_data,
        unique_fields=["financial_account", "datetime"],
        update_fields=["amount", "description", "classification_status"]
    )
    
    if sync_result:
        print(f"📈 Sync upsert completed in real-time!")
        print(f"   Created {sync_result['created_count']} records")
        print(f"   Updated {sync_result['updated_count']} records")
    
    # Example 6b: Single item sync upsert
    print("\n🔄 Example 6b: Sync Upsert - Single Item")
    
    single_sync_data = {
        "amount": "999.99",
        "description": "Single sync upsert transaction",
        "datetime": "2025-01-01T17:00:00Z",
        "financial_account": 1,
        "classification_status": 1,
    }
    
    single_sync_result = example.sync_upsert_single_transaction(
        transaction_data=single_sync_data,
        unique_fields=["financial_account", "datetime"]
    )
    
    if single_sync_result:
        print(f"📈 Single sync upsert completed immediately!")
    
    # Example 6c: Demonstrating sync vs async choice
    print("\n🔄 Example 6c: Sync vs Async - When to Use Each")
    
    print("📚 Usage Guidelines:")
    print("   • Sync Upsert (/upsert): ≤50 items, need immediate results")
    print("     - Real-time form submissions")
    print("     - API integrations with small payloads") 
    print("     - User interactions requiring instant feedback")
    print("   • Async Operations (/operations): >50 items, can wait for results")
    print("     - Large data imports")
    print("     - Batch processing jobs")
    print("     - CSV file uploads")
    
    # Example with too many items for sync (will suggest async)
    print("\n🔄 Example 6d: Too Many Items for Sync")
    
    large_dataset = [
        {
            "amount": f"{i * 10}.00",
            "description": f"Large dataset item {i}",
            "datetime": f"2025-01-01T{18 + (i % 6):02d}:00:00Z",
            "financial_account": 1,
            "classification_status": 1,
        }
        for i in range(55)  # 55 items > default 50 limit
    ]
    
    large_sync_result = example.sync_upsert_financial_transactions(
        data=large_dataset,
        unique_fields=["financial_account", "datetime"]
    )
    
    if not large_sync_result:
        print("📊 As expected, sync endpoint rejected large dataset")
        print("💡 Use async endpoint for large datasets")
        
        # Demonstrate using async for large dataset
        large_async_task_id = example.async_upsert_financial_transactions(
            data=large_dataset,
            unique_fields=["financial_account", "datetime"],
            salesforce_style=True
        )
        
        if large_async_task_id:
            print(f"✅ Large dataset handled by async upsert: {large_async_task_id}")
    
    print("\n🎉 All Examples Completed!")
    print("\n📋 Summary:")
    print("   ✅ Async Operations: For large datasets (>50 items)")
    print("   ✅ Sync Upsert Operations: For small datasets (≤50 items)")
    print("   ✅ Both support the same upsert functionality")
    print("   ✅ Choose based on dataset size and response time needs")


if __name__ == "__main__":
    # This can be run as a Django management command
    # or from a Django shell
    run_example() 