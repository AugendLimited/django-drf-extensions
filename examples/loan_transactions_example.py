#!/usr/bin/env python3
import requests


token = "e7fb63f615fdaa43f3abaa6d9ea90cf4e3095728"
headers = {
    "Authorization": f"Token {token}",
    "accept": "application/json",
    "Content-Type": "application/json",
}

endpoint = "http://localhost:8000/api/loan-transactions/?unique_fields=loan_account,amount,type,posting_date"
data = [
    {"amount": 100, "loan_account": 2, "type": "Disbursement", "status": "Complete", "posting_date": "2025-01-01"},
    {"amount": 10, "loan_account": 2, "type": "Revenue Repayment", "status": "Complete", "posting_date": "2025-01-01"},
]
response = requests.patch(endpoint, headers=headers, json=data)

print(f"PATCH Upsert Status: {response.status_code}")
try:
    print(f"Response: {response.json()}")
except Exception:
    print(f"Response (raw): {response.text}")
