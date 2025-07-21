#!/usr/bin/env python3
import requests


token = "620742c2cbaeec3e65180813b1558bed46f7bae3"
headers = {
    "Authorization": f"Token {token}",
    "accept": "application/json",
    "Content-Type": "application/json",
}

endpoint = "http://localhost:8000/api/loan-transactions/"
data = [
    {"amount": 100, "loan_account": 2, "type": "Disbursement", "status": "Complete"},
    {"amount": 10, "loan_account": 2, "type": "Revenue Repayment", "status": "Complete"},
]
response = requests.post(endpoint, headers=headers, json=data)

print(f"POST Upsert Status: {response.status_code}")
try:
    print(f"Response: {response.json()}")
except Exception:
    print(f"Response (raw): {response.text}")
