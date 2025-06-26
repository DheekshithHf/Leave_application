#!/usr/bin/env python3
"""
Test script to verify AI integration works properly
"""
import sys
import os

# Add the project path
sys.path.append('/Users/happyfox/Documents/HappyFox/Leave_application')

def test_ai_basic():
    """Test basic AI functionality"""
    print("🧪 Testing basic AI functionality...")
    try:
        from ai import test_ai
        result = test_ai()
        return result
    except Exception as e:
        print(f"❌ Basic AI test failed: {e}")
        return False

def test_leave_ai():
    """Test leave-specific AI functionality"""
    print("\n🧪 Testing leave AI functionality...")
    try:
        from leave_ai import leave_ai
        
        # Test leave extraction
        test_text = "I need 2 days off next week for vacation"
        result = leave_ai.extract_leave_details(test_text, {})
        
        print(f"✅ Leave AI extraction successful!")
        print(f"Result: {result}")
        return True
    except Exception as e:
        print(f"❌ Leave AI test failed: {e}")
        return False

def main():
    """Run all AI tests"""
    print("🚀 Starting AI Integration Tests...")
    
    basic_test = test_ai_basic()
    leave_test = test_leave_ai()
    
    if basic_test and leave_test:
        print("\n✅ All AI tests passed! Integration is working.")
    else:
        print("\n❌ Some AI tests failed. Check the errors above.")
        print("Make sure you have:")
        print("1. google-generativeai package installed")
        print("2. Valid API key")
        print("3. Proper file imports")

if __name__ == "__main__":
    main()