"""
Django shell script to update LeaveBalance objects with the new fields
Run this in Django shell: python manage.py shell < update_leave_balance.py
"""

from leave.models import LeaveBalance
from django.db import models

print("Starting LeaveBalance update...")

# First, let's create the new fields if they don't exist
try:
    # Try to add the fields using raw SQL if they don't exist
    from django.db import connection
    cursor = connection.cursor()
    
    # Add casual_used field if it doesn't exist
    try:
        cursor.execute("ALTER TABLE leave_leavebalance ADD COLUMN casual_used INTEGER DEFAULT 0;")
        print("✅ Added casual_used field")
    except Exception as e:
        if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
            print("ℹ️ casual_used field already exists")
        else:
            print(f"Warning: {e}")
    
    # Add sick_used field if it doesn't exist
    try:
        cursor.execute("ALTER TABLE leave_leavebalance ADD COLUMN sick_used INTEGER DEFAULT 0;")
        print("✅ Added sick_used field")
    except Exception as e:
        if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
            print("ℹ️ sick_used field already exists")
        else:
            print(f"Warning: {e}")
    
    connection.commit()
    
except Exception as e:
    print(f"Error updating database structure: {e}")

# Now update existing objects
try:
    updated_count = 0
    for balance in LeaveBalance.objects.all():
        needs_update = False
        
        # Set default values for new fields
        if not hasattr(balance, 'casual_used') or balance.casual_used is None:
            balance.casual_used = 0
            needs_update = True
            
        if not hasattr(balance, 'sick_used') or balance.sick_used is None:
            balance.sick_used = 0
            needs_update = True
        
        if needs_update:
            balance.save()
            updated_count += 1
    
    print(f"✅ Updated {updated_count} LeaveBalance objects")
    print("🎉 Database update completed successfully!")
    
except Exception as e:
    print(f"❌ Error updating LeaveBalance objects: {e}")