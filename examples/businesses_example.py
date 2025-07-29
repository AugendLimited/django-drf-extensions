#!/usr/bin/env python3
import requests


token = "e7fb63f615fdaa43f3abaa6d9ea90cf4e3095728"
headers = {
    "Authorization": f"Token {token}",
    "accept": "application/json",
    "Content-Type": "application/json",
}

endpoint = "http://localhost:8000/api/businesses/?unique_fields=cif_number"
data = [{"name": "cif123", "cif_number": "cif123"}]
response = requests.patch(endpoint, headers=headers, json=data)

print(f"PATCH Upsert Status: {response.status_code}")
try:
    print(f"Response: {response.json()}")
except Exception:
    print(f"Response (raw): {response.text}")
