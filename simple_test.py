#!/usr/bin/env python3
import requests

# Check what methods are allowed first
token = "ba868c4db48bcf30ce6ba6df45b2750a1f41222b"
headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}

url_with_params = (
    "http://localhost:8000/api/loan-accounts/?unique_fields=account_number"
)
data = [
    {"account_number": "string3", "business": 1, "status": "Active"},
    {"account_number": "string2", "business": 1, "status": "Active"},
]
response = requests.patch(url_with_params, headers=headers, json=data)

print(f"PATCH Upsert Status: {response.status_code}")
try:
    print(f"Response: {response.json()}")
except Exception:
    print(f"Response (raw): {response.text}")
