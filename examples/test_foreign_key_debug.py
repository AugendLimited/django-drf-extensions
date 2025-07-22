#!/usr/bin/env python3
"""
Debug script to test foreign key handling in Django ORM
"""
import os
import sys
import django

# Add the Django project to the Python path
sys.path.append('/path/to/your/django/project')  # You'll need to update this path

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'your_project.settings')  # Update this too
django.setup()

from django.db import models

# Import your models (update these imports based on your actual project structure)
try:
    from augend.monthly_financial_forecasts.models import MonthlyFinancialForecast
    from augend.monthly_revenue_forecasts.models import MonthlyRevenueForecast
    from augend.financial_accounts.models import FinancialAccount
    
    print("✅ Models imported successfully")
    
    # Test 1: Check if MonthlyFinancialForecast can be created with foreign key ID
    print("\n🔍 Test 1: MonthlyFinancialForecast with financial_account ID")
    try:
        # Try to create a MonthlyFinancialForecast with a financial_account ID
        forecast = MonthlyFinancialForecast.objects.create(
            financial_account_id=1,  # Using _id suffix
            year=2025,
            month=7
        )
        print(f"✅ Created: {forecast}")
        forecast.delete()  # Clean up
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test 2: Check if MonthlyFinancialForecast can be created with foreign key instance
    print("\n🔍 Test 2: MonthlyFinancialForecast with financial_account instance")
    try:
        # Try to get a financial account first
        financial_account = FinancialAccount.objects.first()
        if financial_account:
            forecast = MonthlyFinancialForecast.objects.create(
                financial_account=financial_account,  # Using instance
                year=2025,
                month=8
            )
            print(f"✅ Created: {forecast}")
            forecast.delete()  # Clean up
        else:
            print("⚠️ No FinancialAccount found in database")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test 3: Check if MonthlyRevenueForecast can be created with foreign key ID
    print("\n🔍 Test 3: MonthlyRevenueForecast with monthly_financial_forecast ID")
    try:
        # Try to create a MonthlyRevenueForecast with a monthly_financial_forecast ID
        revenue_forecast = MonthlyRevenueForecast.objects.create(
            monthly_financial_forecast_id=1,  # Using _id suffix
            year=2025,
            month=7,
            amount=10000
        )
        print(f"✅ Created: {revenue_forecast}")
        revenue_forecast.delete()  # Clean up
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test 4: Check if MonthlyRevenueForecast can be created with foreign key instance
    print("\n🔍 Test 4: MonthlyRevenueForecast with monthly_financial_forecast instance")
    try:
        # Try to get a monthly financial forecast first
        monthly_forecast = MonthlyFinancialForecast.objects.first()
        if monthly_forecast:
            revenue_forecast = MonthlyRevenueForecast.objects.create(
                monthly_financial_forecast=monthly_forecast,  # Using instance
                year=2025,
                month=8,
                amount=10000
            )
            print(f"✅ Created: {revenue_forecast}")
            revenue_forecast.delete()  # Clean up
        else:
            print("⚠️ No MonthlyFinancialForecast found in database")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test 5: Check update_or_create behavior
    print("\n🔍 Test 5: update_or_create with foreign key ID")
    try:
        # Test update_or_create with ID
        instance, created = MonthlyRevenueForecast.objects.update_or_create(
            monthly_financial_forecast_id=1,
            year=2025,
            month=9,
            defaults={'amount': 15000}
        )
        print(f"✅ update_or_create result: created={created}, instance={instance}")
        instance.delete()  # Clean up
    except Exception as e:
        print(f"❌ Error: {e}")
        
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Please update the import paths and Django settings in this script")
except Exception as e:
    print(f"❌ Unexpected error: {e}") 