#!/usr/bin/env python3

"""
Run this script to apply the migration and fix the LeaveBalance model
"""

import os
import sys
import django

# Add the project directory to Python path
project_dir = '/Users/happyfox/Documents/HappyFox/Leave_application'
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

# Set Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Leave_application.settings')

# Setup Django
django.setup()

from django.core.management import execute_from_command_line

if __name__ == '__main__':
    print("Running migration to add sick_used and casual_used fields...")
    try:
        # Make migrations
        execute_from_command_line(['manage.py', 'makemigrations', 'leave'])
        print("✅ Migrations created successfully")
        
        # Apply migrations
        execute_from_command_line(['manage.py', 'migrate'])
        print("✅ Migrations applied successfully")
        
        # Update existing LeaveBalance objects to have the new fields
        from leave.models import LeaveBalance
        print("Updating existing LeaveBalance objects...")
        
        updated_count = 0
        for balance in LeaveBalance.objects.all():
            if not hasattr(balance, 'casual_used') or not hasattr(balance, 'sick_used'):
                balance.casual_used = 0
                balance.sick_used = 0
                balance.save()
                updated_count += 1
        
        print(f"✅ Updated {updated_count} LeaveBalance objects")
        print("🎉 Migration completed successfully!")
        
    except Exception as e:
        print(f"❌ Error during migration: {e}")
        sys.exit(1)