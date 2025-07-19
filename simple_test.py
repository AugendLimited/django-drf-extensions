#!/usr/bin/env python3
import json

import requests

# Check what methods are allowed first
token = "ba868c4db48bcf30ce6ba6df45b2750a1f41222b"
headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}

# Test 1: Just the problematic row
print("=== Test 1: Just the row missing account_number ===")
url_with_params = "http://localhost:8000/api/loan-accounts/?unique_fields=account_number&partial_success=false"
data = [{"business": 1}]  # Missing account_number
response = requests.patch(url_with_params, headers=headers, json=data)

print(f"PATCH Upsert Status: {response.status_code}")
try:
    response_json = response.json()
    print(f"Response: {json.dumps(response_json, indent=2)}")
except Exception as e:
    print(f"Response (raw): {response.text}")

print("\n=== Test 2: Original test with all 3 rows ===")
data = [
    {"account_number": "string3", "business": 1, "status": "Active"},
    {"account_number": "string2", "business": 1},
    {"business": 1},
]
response = requests.patch(url_with_params, headers=headers, json=data)

print(f"PATCH Upsert Status: {response.status_code}")
try:
    response_json = response.json()
    print(f"Response Type: {type(response_json)}")
    if isinstance(response_json, dict):
        print(f"Response Keys: {list(response_json.keys())}")
        if "success" in response_json:
            print(f"Success Count: {len(response_json['success'])}")
        if "errors" in response_json:
            print(f"Errors Count: {len(response_json['errors'])}")
            for error in response_json["errors"]:
                print(f"Error: {error}")
        if "summary" in response_json:
            print(f"Summary: {response_json['summary']}")
    elif isinstance(response_json, list):
        print(f"Response Array Length: {len(response_json)}")
    print(f"Full Response: {json.dumps(response_json, indent=2)}")
except Exception as e:
    print(f"Response parsing error: {e}")
    print(f"Response (raw): {response.text}")
