#!/usr/bin/env python3
import requests

# Check what methods are allowed first
token = "19351ba078375ba46b49de4deedcbba0e2399acb"
headers = {'Authorization': f'Token {token}', 'Content-Type': 'application/json'}

url_with_params = "http://localhost:8000/api/loan-accounts/?unique_fields=account_number"
data = [{"account_number": "string3", "business": 1, "status": "Active"}, {"account_number": "string2", "business": 1, "status": "Active"}]
response = requests.patch(url_with_params, headers=headers, json=data)

print(f"PATCH Upsert Status: {response.status_code}")
try:
    print(f"Response: {response.json()}")
except Exception:
    print(f"Response (raw): {response.text}")