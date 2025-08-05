#!/usr/bin/env python3
import requests


token = "bd250ba135df6691c1df709cd574e322d78fae5b"
headers = {
    "Authorization": f"Token {token}",
    "accept": "application/json",
    "Content-Type": "application/json",
}

endpoint = "http://localhost:8000/api/loan-transactions/?unique_fields=loan_account,amount,type,posting_date"
data = [
    {"amount": 100, "loan_account": 6, "type": "Disbursement", "status": "Complete", "posting_date": "2025-08-05"},
    {"amount": 10, "loan_account": 6, "type": "Revenue Repayment", "status": "Complete", "posting_date": "2025-08-05"},
]
response = requests.patch(endpoint, headers=headers, json=data)

print(f"PATCH Upsert Status: {response.status_code}")
try:
    print(f"Response: {response.json()}")
except Exception:
    print(f"Response (raw): {response.text}")
