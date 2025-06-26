import google.generativeai as genai
import json
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Configure the AI
api_key = "AIzaSyCFz8nLkOQH6sDYYMQOoGHSZk0xjeTE2ok"
genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-2.0-flash-lite')

def extract_calendar_query(text, today_date):
    """Extract calendar query parameters from natural language text using AI"""
    try:
        template = f"""
You are an HR assistant. Extract calendar query parameters from the user's text and return JSON.

IMPORTANT RULES:
1. Extract date ranges (start_date and end_date in YYYY-MM-DD format)
2. Extract leave types: CASUAL, SICK, MATERNITY, PATERNITY, ALL
3. Extract status filter: APPROVED, PENDING, REJECTED, ALL
4. Extract team/department filter if mentioned and match with existing teams/departments exact name.
List of existing departments name :[
            'Product-Engineer',
            'Quality Assurance', 
            'DevOps',
            'Frontend Development',
            'Backend Development',
            'Mobile Development',
            'Data Science',
            'Machine Learning',
            'UI/UX Design',
            'Product Management',
            'Human Resources',
            'Finance',
            'Marketing',
            'Sales',
            'Customer Support',
            'Operations',
            'Security',
            'Business Analytics'
        ]

5. Today is {today_date}, calculate relative dates from this
6. Extract display options if provided like to show employee details or their leave reasons or their conflict analysis or to group by department.
Map options with exact names. List of existing display options exact names: 
['SHOW_DETAILS', 'SHOW_REASONS', 'SHOW_CONFLICTS', 'GROUP_DEPT'] 
7. Extract sort options if provided like to sort by date(ASC or DESC), employee name(ASC OR DESC), leave type, status, etc.
Map matching options with exact names. List of existing sort options exact names:
['DATE_ASC', 'DATE_DESC', 'EMPLOYEE_ASC', 'EMPLOYEE_DESC', 'TYPE', 'STATUS_PENDING', 'DURATION_DESC']

User text: "{text}"

Return this exact JSON structure:
{{
    "start_date": "YYYY-MM-DD",
    "end_date": "YYYY-MM-DD", 
    "leave_type": "CASUAL|SICK|MATERNITY|PATERNITY|ALL",
    "status": "APPROVED|PENDING|REJECTED|ALL",
    "team_filter": "team name or null",
    "department_filter": "department name or null",
    "employee_filter": "employee name or null",
    "display_options": ["SHOW_DETAILS", "SHOW_REASONS", "SHOW_CONFLICTS", "GROUP_DEPT"],
    "sort_option": "DATE_ASC|DATE_DESC|EMPLOYEE_ASC|EMPLOYEE_DESC|TYPE|STATUS_PENDING|DURATION_DESC",
    "confidence_score": 0-100,
    "query_description": "human readable description of the query",
    "time_period": "this week|next week|this month|next month|specific dates"
}}

DISPLAY OPTIONS EXTRACTION RULES:
- "with details", "show details", "employee info" → include "SHOW_DETAILS"
- "with reasons", "show reasons", "why they took" → include "SHOW_REASONS"
- "conflicts", "overlapping", "conflict analysis" → include "SHOW_CONFLICTS"
- "group by department", "department wise", "by department" → include "GROUP_DEPT"

SORT OPTIONS EXTRACTION RULES:
- "latest first", "recent first", "newest" → "DATE_DESC"
- "earliest first", "oldest first", "chronological" → "DATE_ASC"
- "alphabetical", "by name", "employee wise" → "EMPLOYEE_ASC"
- "reverse alphabetical" → "EMPLOYEE_DESC"
- "by type", "leave type wise" → "TYPE"
- "pending first", "pending on top" → "STATUS_PENDING"
- "longest first", "duration wise", "by length" → "DURATION_DESC"

Examples:
- "show me leaves this week with details" → display_options: ["SHOW_DETAILS"]
- "approved leaves grouped by department with reasons" → display_options: ["GROUP_DEPT", "SHOW_REASONS"]
- "sick leaves sorted by employee name" → sort_option: "EMPLOYEE_ASC"
- "latest leaves first with conflicts" → sort_option: "DATE_DESC", display_options: ["SHOW_CONFLICTS"]
"""

        response = model.generate_content(
            template,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=600,
                temperature=0.2
            )
        )
        
        # Parse JSON response
        response_text = response.text.strip()
        if '```json' in response_text:
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            json_text = response_text[json_start:json_end]
        else:
            json_text = response_text
            
        result = json.loads(json_text)
        
        # Validate and set defaults
        required_fields = ['start_date', 'end_date', 'leave_type', 'status']
        for field in required_fields:
            if field not in result:
                result[field] = 'ALL' if field in ['leave_type', 'status'] else None
        
        # Process display options - ensure it's always a list
        if 'display_options' not in result or not result['display_options']:
            result['display_options'] = ['SHOW_DETAILS', 'SHOW_REASONS']  # Default options
        elif isinstance(result['display_options'], str):
            # Convert single string to list
            result['display_options'] = [result['display_options']]
        elif not isinstance(result['display_options'], list):
            result['display_options'] = ['SHOW_DETAILS', 'SHOW_REASONS']  # Fallback
        
        # Validate display options
        valid_display_options = ['SHOW_DETAILS', 'SHOW_REASONS', 'SHOW_CONFLICTS', 'GROUP_DEPT']
        result['display_options'] = [opt for opt in result['display_options'] if opt in valid_display_options]
        
        # Ensure at least one display option
        if not result['display_options']:
            result['display_options'] = ['SHOW_DETAILS']
        
        # Process sort option
        if 'sort_option' not in result or not result['sort_option']:
            result['sort_option'] = 'DATE_ASC'  # Default sort
        
        # Validate sort option
        valid_sort_options = ['DATE_ASC', 'DATE_DESC', 'EMPLOYEE_ASC', 'EMPLOYEE_DESC', 'TYPE', 'STATUS_PENDING', 'DURATION_DESC']
        if result['sort_option'] not in valid_sort_options:
            result['sort_option'] = 'DATE_ASC'  # Fallback
        
        if 'confidence_score' not in result:
            result['confidence_score'] = 70
            
        if 'query_description' not in result:
            result['query_description'] = f"Calendar query for {text}"
            
        # Set default time period
        if 'time_period' not in result:
            result['time_period'] = 'specific dates'
        
        logger.info(f"Calendar AI extracted: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Calendar AI processing error: {e}")
        return {
            "error": "Could not process your calendar query. Please try again with more specific details.",
            "confidence_score": 0
        }

def calculate_date_range(time_period):
    """Calculate actual dates based on time period"""
    today = datetime.now().date()
    
    if time_period == 'this week':
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)
    elif time_period == 'next week':
        start_date = today + timedelta(days=(7 - today.weekday()))
        end_date = start_date + timedelta(days=6)
    elif time_period == 'this month':
        start_date = today.replace(day=1)
        next_month = start_date.replace(month=start_date.month % 12 + 1, day=1)
        end_date = next_month - timedelta(days=1)
    elif time_period == 'next month':
        next_month = today.replace(month=today.month % 12 + 1, day=1)
        start_date = next_month
        following_month = next_month.replace(month=next_month.month % 12 + 1, day=1)
        end_date = following_month - timedelta(days=1)
    else:
        # Default to current week
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)
    
    return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')

def test_calendar_ai():
    """Test the calendar AI integration"""
    test_cases = [
        "show me leaves this week with details",
        "approved leaves grouped by department with reasons", 
        "sick leaves sorted by employee name",
        "latest leaves first with conflicts",
        "pending leaves with all details sorted by duration"
    ]
    
    today = datetime.now().date()
    for test_text in test_cases:
        print(f"\nTesting: {test_text}")
        result = extract_calendar_query(test_text, today)
        print(f"Result: {result}")

if __name__ == "__main__":
    test_calendar_ai()

