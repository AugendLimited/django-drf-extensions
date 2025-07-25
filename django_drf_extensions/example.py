"""
Example script demonstrating how to use the unified DRF extensions.

This script shows how to:
1. Use enhanced standard endpoints for sync operations (immediate results)
2. Use bulk endpoints for async operations (background processing)
3. Track progress using the status endpoint

The new design provides:
- Smart standard endpoints: GET/POST/PATCH/PUT with ?unique_fields= for sync operations
- Bulk endpoints: GET/POST/PATCH/PUT/DELETE /bulk/ for async operations

Run this script from a Django shell or as a management command.
"""

import time

import requests


class DRFExtensionsExample:
    """Example class demonstrating the unified DRF extensions usage."""

    def __init__(self, base_url: str = "https://sit-sg.augend.io/api"):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        # Add authentication if needed
        # self.session.headers.update({'Authorization': 'Token your-token-here'})

    # =============================================================================
    # Sync Operations (Enhanced Standard Endpoints)
    # =============================================================================

    def sync_multi_get(self, ids: list[int]) -> dict:
        """
        Retrieve multiple records using enhanced standard endpoint.

        - Small datasets: immediate results
        - Uses: GET /api/model/?ids=1,2,3
        """
        url = f"{self.base_url}/contracts/"
        ids_str = ",".join(map(str, ids))
        response = self.session.get(f"{url}?ids={ids_str}")

        if response.status_code == 200:
            result = response.json()
            print(f"✅ Sync multi-get completed: {result['count']} records retrieved")
            print(f"📊 Results: {len(result['results'])} items")
            return result
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")
            return {}

    def sync_upsert(
        self,
        data: list[dict],
        unique_fields: list[str],
        update_fields: list[str] = None,
    ) -> dict:
        """
        Perform sync upsert using enhanced standard endpoint.

        - Small datasets: immediate results
        - Uses: POST /api/model/?unique_fields=field1,field2
        """
        url = f"{self.base_url}/contracts/"
        params = {"unique_fields": ",".join(unique_fields)}
        if update_fields:
            params["update_fields"] = ",".join(update_fields)

        response = self.session.post(url, json=data, params=params)

        if response.status_code == 200:
            result = response.json()
            print(f"✅ Sync upsert completed: {result['message']}")
            print(f"📊 Results:")
            print(f"   • Total: {result['total_items']}")
            print(
                f"   • Created: {result['created_count']} (IDs: {result['created_ids']})"
            )
            print(
                f"   • Updated: {result['updated_count']} (IDs: {result['updated_ids']})"
            )
            print(f"   • Errors: {result['error_count']}")
            return result
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")
            return {}

    def sync_upsert_update(self, data: list[dict], unique_fields: list[str]) -> dict:
        """
        Perform sync upsert using PATCH method.

        - Uses: PATCH /api/model/?unique_fields=field1,field2
        """
        url = f"{self.base_url}/contracts/"
        params = {"unique_fields": ",".join(unique_fields)}

        response = self.session.patch(url, json=data, params=params)

        if response.status_code == 200:
            result = response.json()
            print(f"✅ Sync upsert (PATCH) completed: {result['message']}")
            return result
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")
            return {}

    # =============================================================================
    # Async Operations (Bulk Endpoints)
    # =============================================================================

    def bulk_get(self, ids: list[int]) -> str:
        """
        Retrieve multiple records using bulk endpoint for large datasets.

        - Large datasets: background processing
        - Uses: GET /api/model/bulk/?ids=1,2,3
        """
        url = f"{self.base_url}/contracts/bulk/"
        ids_str = ",".join(map(str, ids))
        response = self.session.get(f"{url}?ids={ids_str}")

        if response.status_code == 202:
            result = response.json()
            print(f"✅ Bulk get started: {result['message']}")
            print(f"📋 Task ID: {result['task_id']}")
            print(f"🔗 Status URL: {result['status_url']}")
            return result["task_id"]
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")
            return ""

    def bulk_create(self, data: list[dict]) -> str:
        """
        Create multiple records using bulk endpoint.

        - Uses: POST /api/model/bulk/
        """
        url = f"{self.base_url}/contracts/bulk/"
        response = self.session.post(url, json=data)

        if response.status_code == 202:
            result = response.json()
            print(f"✅ Bulk create started: {result['message']}")
            print(f"📋 Task ID: {result['task_id']}")
            print(f"🔗 Status URL: {result['status_url']}")
            return result["task_id"]
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")
            return ""

    def bulk_update(self, data: list[dict]) -> str:
        """
        Update multiple records using bulk endpoint.

        - Uses: PATCH /api/model/bulk/
        - Requires 'id' field in each object
        """
        url = f"{self.base_url}/contracts/bulk/"
        response = self.session.patch(url, json=data)

        if response.status_code == 202:
            result = response.json()
            print(f"✅ Bulk update started: {result['message']}")
            print(f"📋 Task ID: {result['task_id']}")
            print(f"🔗 Status URL: {result['status_url']}")
            return result["task_id"]
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")
            return ""

    def bulk_upsert(
        self,
        data: list[dict],
        unique_fields: list[str],
        update_fields: list[str] = None,
    ) -> str:
        """
        Upsert multiple records using bulk endpoint.

        - Uses: PATCH /api/model/bulk/?unique_fields=field1,field2
        """
        url = f"{self.base_url}/contracts/bulk/"
        params = {"unique_fields": ",".join(unique_fields)}
        if update_fields:
            params["update_fields"] = ",".join(update_fields)

        response = self.session.patch(url, json=data, params=params)

        if response.status_code == 202:
            result = response.json()
            print(f"✅ Bulk upsert started: {result['message']}")
            print(f"📋 Task ID: {result['task_id']}")
            print(f"🔑 Unique fields: {result['unique_fields']}")
            if result.get("update_fields"):
                print(f"📝 Update fields: {result['update_fields']}")
            print(f"🔗 Status URL: {result['status_url']}")
            return result["task_id"]
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")
            return ""

    def bulk_delete(self, ids: list[int]) -> str:
        """
        Delete multiple records using bulk endpoint.

        - Uses: DELETE /api/model/bulk/
        """
        url = f"{self.base_url}/contracts/bulk/"
        response = self.session.delete(url, json=ids)

        if response.status_code == 202:
            result = response.json()
            print(f"✅ Bulk delete started: {result['message']}")
            print(f"📋 Task ID: {result['task_id']}")
            print(f"🔗 Status URL: {result['status_url']}")
            return result["task_id"]
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")
            return ""

    # =============================================================================
    # Task Monitoring
    # =============================================================================

    def check_task_status(self, task_id: str) -> dict:
        """
        Check the status of an async operation task.
        """
        url = f"{self.base_url}/../operations/{task_id}/status/"  # Note: operations is outside the model URL
        response = self.session.get(url)

        if response.status_code == 200:
            result = response.json()
            print(f"📊 Task {task_id} Status: {result['status']}")
            if "progress" in result:
                progress = result["progress"]
                print(
                    f"📈 Progress: {progress['current']}/{progress['total']} ({progress['percentage']}%)"
                )
            if result["status"] == "completed" and "result" in result:
                task_result = result["result"]
                print(f"✅ Operation completed successfully!")
                if "success_count" in task_result:
                    print(f"   • Success: {task_result['success_count']}")
                if "error_count" in task_result:
                    print(f"   • Errors: {task_result['error_count']}")
            return result
        else:
            print(f"❌ Error checking status: {response.status_code} - {response.text}")
            return {}

    def wait_for_completion(
        self, task_id: str, max_wait_seconds: int = 300, poll_interval: int = 2
    ) -> dict:
        """
        Wait for an async task to complete.
        """
        print(f"⏳ Waiting for task {task_id} to complete...")
        start_time = time.time()

        while time.time() - start_time < max_wait_seconds:
            status_result = self.check_task_status(task_id)

            if not status_result:
                print("❌ Failed to get task status")
                break

            if status_result["status"] in ["completed", "failed", "cancelled"]:
                print(f"🏁 Task finished with status: {status_result['status']}")
                return status_result

            print(
                f"⏱️  Task still {status_result['status']}, checking again in {poll_interval}s..."
            )
            time.sleep(poll_interval)

        print(f"⏰ Timeout waiting for task {task_id}")
        return self.check_task_status(task_id)


def run_example():
    """Run the unified DRF extensions example."""

    # Initialize the example client
    example = DRFExtensionsExample()

    print("🚀 Django DRF Extensions - Unified Design Example")
    print("=" * 60)

    # =============================================================================
    # Sync Operations Examples (Enhanced Standard Endpoints)
    # =============================================================================

    print("\n" + "=" * 60)
    print("📝 SYNC OPERATIONS (Enhanced Standard Endpoints)")
    print("=" * 60)
    print("✨ Immediate results for small datasets")

    # Example 1: Sync Multi-Get
    print("\n📖 Example 1: Sync Multi-Get")
    print("GET /api/contracts/?ids=1,2,3,4,5")

    small_ids = [1, 2, 3, 4, 5]
    sync_get_result = example.sync_multi_get(small_ids)

    # Example 2: Sync Upsert via POST
    print("\n📝 Example 2: Sync Upsert via POST")
    print("POST /api/contracts/?unique_fields=contract_number,year")

    sync_upsert_data = [
        {
            "contract_number": "C001",
            "year": 2024,
            "amount": 1000,
            "description": "Sync contract 1",
        },
        {
            "contract_number": "C002",
            "year": 2024,
            "amount": 2000,
            "description": "Sync contract 2",
        },
        {
            "contract_number": "C001",  # This will update C001
            "year": 2024,
            "amount": 1500,  # Updated amount
            "description": "Sync contract 1 updated",
        },
    ]

    sync_result = example.sync_upsert(
        data=sync_upsert_data,
        unique_fields=["contract_number", "year"],
        update_fields=["amount", "description"],
    )

    # Example 3: Sync Upsert via PATCH
    print("\n📝 Example 3: Sync Upsert via PATCH")
    print("PATCH /api/contracts/?unique_fields=contract_number,year")

    patch_data = [
        {
            "contract_number": "C003",
            "year": 2024,
            "amount": 3000,
            "description": "Patch contract 3",
        }
    ]

    patch_result = example.sync_upsert_update(
        data=patch_data, unique_fields=["contract_number", "year"]
    )

    # =============================================================================
    # Async Operations Examples (Bulk Endpoints)
    # =============================================================================

    print("\n" + "=" * 60)
    print("🔄 ASYNC OPERATIONS (Bulk Endpoints)")
    print("=" * 60)
    print("⚡ Background processing for large datasets")

    # Example 4: Bulk Create
    print("\n📝 Example 4: Bulk Create")
    print("POST /api/contracts/bulk/")

    bulk_create_data = [
        {
            "contract_number": f"BC{i:03d}",
            "year": 2024,
            "amount": i * 100,
            "description": f"Bulk contract {i}",
        }
        for i in range(1, 51)  # 50 contracts for bulk processing
    ]

    create_task_id = example.bulk_create(bulk_create_data)

    if create_task_id:
        create_result = example.wait_for_completion(create_task_id, max_wait_seconds=60)

    # Example 5: Bulk Upsert
    print("\n📝 Example 5: Bulk Upsert")
    print("PATCH /api/contracts/bulk/?unique_fields=contract_number,year")

    bulk_upsert_data = [
        {
            "contract_number": f"BU{i:03d}",
            "year": 2024,
            "amount": i * 150,  # Different amounts
            "description": f"Bulk upsert contract {i}",
        }
        for i in range(1, 101)  # 100 contracts for bulk upsert
    ]

    upsert_task_id = example.bulk_upsert(
        data=bulk_upsert_data,
        unique_fields=["contract_number", "year"],
        update_fields=["amount", "description"],
    )

    if upsert_task_id:
        upsert_result = example.wait_for_completion(upsert_task_id, max_wait_seconds=60)

    # Example 6: Bulk Get (Large Dataset)
    print("\n📖 Example 6: Bulk Get (Large Dataset)")
    print("GET /api/contracts/bulk/?ids=1,2,3,...,200")

    large_ids = list(range(1, 201))  # 200 IDs for bulk processing
    get_task_id = example.bulk_get(large_ids)

    if get_task_id:
        get_result = example.wait_for_completion(get_task_id, max_wait_seconds=60)

    # Example 7: Bulk Update
    print("\n✏️ Example 7: Bulk Update")
    print("PATCH /api/contracts/bulk/")

    bulk_update_data = [
        {"id": 1, "amount": 9999, "description": "Updated via bulk"},
        {"id": 2, "amount": 8888, "description": "Updated via bulk"},
        {"id": 3, "amount": 7777, "description": "Updated via bulk"},
    ]

    update_task_id = example.bulk_update(bulk_update_data)

    if update_task_id:
        update_result = example.wait_for_completion(update_task_id, max_wait_seconds=60)

    # Example 8: Bulk Delete
    print("\n🗑️ Example 8: Bulk Delete")
    print("DELETE /api/contracts/bulk/")

    # Delete some test records (use IDs that you know exist)
    ids_to_delete = [100, 101, 102, 103, 104, 105]
    delete_task_id = example.bulk_delete(ids_to_delete)

    if delete_task_id:
        delete_result = example.wait_for_completion(delete_task_id, max_wait_seconds=60)

    # =============================================================================
    # Summary
    # =============================================================================

    print("\n" + "=" * 60)
    print("🎉 All Examples Completed!")
    print("=" * 60)

    print("\n📋 Summary of New Unified Design:")
    print("┌─────────────────────────────────────────────────────────┐")
    print("│                    SYNC OPERATIONS                      │")
    print("│  Enhanced Standard Endpoints (Immediate Results)       │")
    print("├─────────────────────────────────────────────────────────┤")
    print("│ GET    /api/contracts/?ids=1,2,3        → Multi-get     │")
    print("│ POST   /api/contracts/?unique_fields=... → Upsert       │")
    print("│ PATCH  /api/contracts/?unique_fields=... → Upsert       │")
    print("│ PUT    /api/contracts/?unique_fields=... → Upsert       │")
    print("└─────────────────────────────────────────────────────────┘")

    print("\n┌─────────────────────────────────────────────────────────┐")
    print("│                   ASYNC OPERATIONS                      │")
    print("│     Bulk Endpoints (Background Processing)              │")
    print("├─────────────────────────────────────────────────────────┤")
    print("│ GET    /api/contracts/bulk/?ids=...     → Multi-get     │")
    print("│ POST   /api/contracts/bulk/             → Create        │")
    print("│ PATCH  /api/contracts/bulk/             → Update/Upsert │")
    print("│ PUT    /api/contracts/bulk/             → Replace/Upsert│")
    print("│ DELETE /api/contracts/bulk/             → Delete        │")
    print("└─────────────────────────────────────────────────────────┘")

    print("\n✅ Key Benefits:")
    print("   • Single mixin (OperationsMixin) provides everything")
    print("   • Enhanced standard endpoints for immediate results")
    print("   • Clean /bulk/ endpoints for background processing")
    print("   • Intelligent routing based on dataset size")
    print("   • No confusing parallel endpoint structures")

    print("\n🔧 Usage:")
    print("   class ContractViewSet(OperationsMixin, viewsets.ModelViewSet):")
    print("       queryset = Contract.objects.all()")
    print("       serializer_class = ContractSerializer")


if __name__ == "__main__":
    # This can be run as a Django management command
    # or from a Django shell
    run_example()
