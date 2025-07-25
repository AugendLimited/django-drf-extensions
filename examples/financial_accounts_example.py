#!/usr/bin/env python3
import requests

token = "b8c2ee3c5e210015c431a5b08109c253c18b3170"
headers = {
    "Authorization": f"Token {token}",
    "accept": "application/json",
    "Content-Type": "application/json",
}

endpoint = (
    "https://sit-sg.augend.io/api/financial-accounts/?unique_fields=account_number"
)
data = [
    {
        "account_number": 123,
        "business": 3,
        "type": "Bank",
        "financial_provider": "CIMB",
    },
    {
        "account_number": 456,
        "business": 3,
        "type": "Bank",
        "financial_provider": "CIMB",
    },
]
response = requests.patch(endpoint, headers=headers, json=data)

print(f"PATCH Upsert Status: {response.status_code}")
try:
    print(f"Response: {response.json()}")
except Exception:
    print(f"Response (raw): {response.text}")
