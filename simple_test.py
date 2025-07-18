#!/usr/bin/env python3
import requests

# Check what methods are allowed first
token = "19351ba078375ba46b49de4deedcbba0e2399acb"
url = "http://localhost:8000/api/loan-accounts/"

headers = {'Authorization': f'Token {token}', 'Content-Type': 'application/json'}

# Check allowed methods
options_response = requests.options(url, headers=headers)
print(f"Allowed methods: {options_response.headers.get('Allow', 'Not specified')}")

url_with_params = "http://localhost:8000/api/loan-accounts/?unique_fields=account_number"
data = [{"account_number": "string", "business": 1, "status": "Active"}]
response = requests.patch(url_with_params, headers=headers, json=data)

print(f"PATCH Upsert Status: {response.status_code}")
try:
    print(f"Response: {response.json()}")
except:
    print(f"Response (raw): {response.text}")