#!/usr/bin/env python3
import requests

token = "0718bce74f66b18547b54059a7a1081133ac3b7d"
headers = {
    "Authorization": f"Token {token}",
    "accept": "application/json",
    "Content-Type": "application/json",
}

endpoint = "https://sit-sg.augend.io/api/loan-transactions/?unique_fields=loan_account,amount,type,posting_date"
data = [
    {
        "amount": 100,
        "loan_account": 11,
        "type": "Disbursement",
        "status": "Complete",
        "posting_date": "2025-01-01",
    },
    {
        "amount": 10,
        "loan_account": 11,
        "type": "Revenue Repayment",
        "status": "Complete",
        "posting_date": "2025-01-01",
    },
]
response = requests.patch(endpoint, headers=headers, json=data)

print(f"PATCH Upsert Status: {response.status_code}")
try:
    print(f"Response: {response.json()}")
except Exception:
    print(f"Response (raw): {response.text}")
