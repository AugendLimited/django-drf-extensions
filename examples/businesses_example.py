#!/usr/bin/env python3
import requests


token = "bd250ba135df6691c1df709cd574e322d78fae5b"
headers = {
    "Authorization": f"Token {token}",
    "accept": "application/json",
    "Content-Type": "application/json",
}

endpoint = "http://localhost:8000/api/cimb-businesses/?unique_fields=cif_number"
data = [{"name": "cif123", "cif_number": "cif123"}, {"name": "cif456", "cif_number": "cif456"}]
response = requests.patch(endpoint, headers=headers, json=data)

print(f"PATCH Upsert Status: {response.status_code}")
try:
    print(f"Response: {response.json()}")
except Exception:
    print(f"Response (raw): {response.text}")
