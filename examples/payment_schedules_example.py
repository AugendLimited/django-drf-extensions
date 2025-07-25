#!/usr/bin/env python3
import requests

token = "620742c2cbaeec3e65180813b1558bed46f7bae3"
headers = {
    "Authorization": f"Token {token}",
    "accept": "application/json",
    "Content-Type": "application/json",
}

endpoint = "https://sit-sg.augend.io/api/payment-schedules/"
data = [
    {
        "frequency": "0 0 * * MON-FRI",
        "loan_account": 2,
        "repayment_percentage": 10,
        "type": "Revenue Repayment",
    }
]
response = requests.post(endpoint, headers=headers, json=data)

print(f"POST Upsert Status: {response.status_code}")
try:
    print(f"Response: {response.json()}")
except Exception:
    print(f"Response (raw): {response.text}")
