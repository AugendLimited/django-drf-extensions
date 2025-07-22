#!/usr/bin/env python3
import requests


token = "b8c2ee3c5e210015c431a5b08109c253c18b3170"
headers = {
    "Authorization": f"Token {token}",
    "accept": "application/json",
    "Content-Type": "application/json",
}

endpoint = "http://localhost:8000/api/monthly-financial-forecasts/?unique_fields=financial_account,year,month"
data = [
    {"financial_account": 2, "year": 2025, "month": 7},
    {"financial_account": 3, "year": 2025, "month": 7},
]
response = requests.patch(endpoint, headers=headers, json=data)

print(f"PATCH Upsert Status: {response.status_code}")
try:
    print(f"Response: {response.json()}")
except Exception:
    print(f"Response (raw): {response.text}")
