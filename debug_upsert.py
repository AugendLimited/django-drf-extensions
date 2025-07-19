#!/usr/bin/env python3
"""
Debug script to test the upsert validation logic
"""

import json

import requests

token = "ba868c4db48bcf30ce6ba6df45b2750a1f41222b"
headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}

# Test with an invalid partial_success value to see if it's being parsed
print("=== Test 1: Invalid partial_success value ===")
url_with_params = "http://localhost:8000/api/loan-accounts/?unique_fields=account_number&partial_success=invalid"
data = [
    {"account_number": "string3", "business": 1, "status": "Active"},
    {"account_number": "string2", "business": 1},
    {"business": 1},  # Missing account_number
]
response = requests.patch(url_with_params, headers=headers, json=data)

print(f"Status: {response.status_code}")
try:
    response_json = response.json()
    print(f"Response: {json.dumps(response_json, indent=2)}")
except Exception as e:
    print(f"Response (raw): {response.text}")

print("\n=== Test 2: partial_success=false (should fail) ===")
url_with_params = "http://localhost:8000/api/loan-accounts/?unique_fields=account_number&partial_success=false"
response = requests.patch(url_with_params, headers=headers, json=data)

print(f"Status: {response.status_code}")
try:
    response_json = response.json()
    print(f"Response: {json.dumps(response_json, indent=2)}")
except Exception as e:
    print(f"Response (raw): {response.text}")

print("\n=== Test 3: partial_success=true (should return 207) ===")
url_with_params = "http://localhost:8000/api/loan-accounts/?unique_fields=account_number&partial_success=true"
response = requests.patch(url_with_params, headers=headers, json=data)

print(f"Status: {response.status_code}")
try:
    response_json = response.json()
    print(f"Response: {json.dumps(response_json, indent=2)}")
except Exception as e:
    print(f"Response (raw): {response.text}")
