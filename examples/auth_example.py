#!/usr/bin/env python3
import requests

headers = {"accept": "application/json", "Content-Type": "application/json"}

endpoint = ("http://localhost:8000/api/auth-token/")
data = {"username": "konrad.beck@merchantcapital.co.za", "password": "PASSWORD"}
response = requests.post(endpoint, headers=headers, json=data)

print(f"POST Upsert Status: {response.status_code}")
try:
    print(f"Response: {response.json()}")
except Exception:
    print(f"Response (raw): {response.text}")
