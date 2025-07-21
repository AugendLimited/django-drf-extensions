#!/usr/bin/env python3
import requests

# Check what methods are allowed first
token = "0718bce74f66b18547b54059a7a1081133ac3b7d"
headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}

url_with_params = (
    "https://sit-sg.augend.io/api/businesses/?unique_fields=cif_number"
)
data = [
    { "name": "string123", "cif_number": "string123" },
    { "name": "stringabc", "cif_number": "stringabc" }
]
response = requests.patch(url_with_params, headers=headers, json=data)

print(f"PATCH Upsert Status: {response.status_code}")
try:
    print(f"Response: {response.json()}")
except Exception:
    print(f"Response (raw): {response.text}")
