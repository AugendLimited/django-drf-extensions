#!/usr/bin/env python3
import requests

token = "0718bce74f66b18547b54059a7a1081133ac3b7d"
headers = {
    "Authorization": f"Token {token}",
    "accept": "application/json",
    "Content-Type": "application/json",
}

endpoint = "https://sit-sg.augend.io/api/businesses/?unique_fields=cif_number"
data = [{"name": "cif123", "cif_number": "cif123"}]
response = requests.patch(endpoint, headers=headers, json=data)

print(f"PATCH Upsert Status: {response.status_code}")
try:
    print(f"Response: {response.json()}")
except Exception:
    print(f"Response (raw): {response.text}")
