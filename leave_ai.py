import google.generativeai as genai
import json
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Configure the AI
api_key = "AIzaSyCFz8nLkOQH6sDYYMQOoGHSZk0xjeTE2ok"  # Your API key
genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-2.0-flash-lite')

def extract_leave_details(text, today_date):
    """Extract leave details from user text with validation"""
    try:
        template = f"""
You are an HR assistant. Extract leave request details from the user's text and return JSON.

IMPORTANT RULES:
1. Extract leave type: CASUAL, SICK, MATERNITY, PATERNITY
2. Extract dates (start_date and end_date in YYYY-MM-DD format)
3. Calculate duration in days
4. Extract reason for leave
5. Extract backup person if mentioned
6. Today is {today_date}, calculate relative dates from this
7. Return confidence score 0-100

User text: "{text}"

Return this exact JSON structure:
{{
    "leave_type": "CASUAL|SICK|MATERNITY|PATERNITY",
    "start_date": "YYYY-MM-DD",
    "end_date": "YYYY-MM-DD", 
    "duration_days": number,
    "reason": "extracted reason",
    "backup_person": "name or null",
    "confidence_score": 0-100,
    "missing_info": ["list of missing information"],
    "friendly_response": "human readable confirmation message"
}}

Examples:
- "I need 2 days off next week for vacation" → CASUAL leave
- "I'm feeling sick today" → SICK leave
- "I need maternity leave starting next month" → MATERNITY leave
- "Paternity leave for 2 weeks" → PATERNITY leave

DATE PARSING RULES:
- "today" → {today_date}
- "tomorrow" → {today_date + timedelta(days=1)}
- "next week" → start from next Monday
- "this week" → remaining days this week
- "next month" → first day of next month
"""

        response = model.generate_content(
            template,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=500,
                temperature=0.2
            )
        )
        
        # Log the AI model response
        logger.info(f"LEAVE_AI_RAW_RESPONSE: {response.text}")
        
        # Parse JSON response
        response_text = response.text.strip()
        if '```json' in response_text:
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            json_text = response_text[json_start:json_end]
        else:
            json_text = response_text
            
        result = json.loads(json_text)
        
        # Validate required fields
        required_fields = ['leave_type', 'start_date', 'end_date', 'reason']
        for field in required_fields:
            if field not in result or not result[field]:
                return {
                    'error': f'Could not extract {field} from your message. Please provide more details.',
                    'confidence_score': 0
                }
        
        # Validate leave type
        valid_types = ['CASUAL', 'SICK', 'MATERNITY', 'PATERNITY']
        if result['leave_type'] not in valid_types:
            result['leave_type'] = 'CASUAL'  # Default to casual
            
        # Ensure backup_person is not None for JSON serialization
        if result.get('backup_person') is None:
            result['backup_person'] = None
            
        # Set defaults for optional fields
        if 'duration_days' not in result:
            start = datetime.strptime(result['start_date'], '%Y-%m-%d').date()
            end = datetime.strptime(result['end_date'], '%Y-%m-%d').date()
            result['duration_days'] = (end - start).days + 1
            
        if 'confidence_score' not in result:
            result['confidence_score'] = 70
            
        if 'missing_info' not in result:
            result['missing_info'] = []
            
        if 'friendly_response' not in result:
            result['friendly_response'] = f"I've processed your {result['leave_type'].lower()} leave request for {result['duration_days']} days."
        
        # Log the final parsed result
        logger.info(f"LEAVE_AI_FINAL_RESULT: {json.dumps(result, indent=2, default=str)}")
        
        return result
        
    except Exception as e:
        logger.error(f"LEAVE_AI_ERROR: Error in AI processing: {e}")
        return {
            'error': f'AI processing failed: {str(e)}',
            'confidence_score': 0
        }

def test_leave_ai():
    """Test the leave AI integration"""
    test_cases = [
        "I need 2 days off next week for vacation",
        "I'm feeling sick today and tomorrow", 
        "I need maternity leave starting next month",
        "Paternity leave for 2 weeks from June 25th",
        "casual leave tomorrow for personal work"
    ]
    
    today = datetime.now().date()
    for test_text in test_cases:
        print(f"\nTesting: {test_text}")
        result = extract_leave_details(test_text, today)
        print(f"Result: {result}")

if __name__ == "__main__":
    test_leave_ai()