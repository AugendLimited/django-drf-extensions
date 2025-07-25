#!/usr/bin/env python3
import requests

token = "b8c2ee3c5e210015c431a5b08109c253c18b3170"
headers = {
    "Authorization": f"Token {token}",
    "accept": "application/json",
    "Content-Type": "application/json",
}

endpoint = "https://sit-sg.augend.io/api/monthly-revenue-forecasts/?unique_fields=monthly_financial_forecast,year,month"
data = [
    {"monthly_financial_forecast": 1, "year": 2025, "month": 7, "amount": 10000},
    {"monthly_financial_forecast": 2, "year": 2025, "month": 7, "amount": 10000},
]
response = requests.patch(endpoint, headers=headers, json=data)

print(f"PATCH Upsert Status: {response.status_code}")
try:
    print(f"Response: {response.json()}")
except Exception:
    print(f"Response (raw): {response.text}")
