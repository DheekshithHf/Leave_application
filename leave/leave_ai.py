import google.generativeai as genai
import json
import re
from datetime import datetime, timedelta
import logging



#OLD PROMPT TEMPLATE 

# template = f"""
# You are a helpful HR assistant. Extract leave request details from the user's text and return them in JSON format.

# IMPORTANT RULES:
# 1. If no clear reason is provided, set reason to null
# 2. Always provide start_date and end_date in YYYY-MM-DD format.It is either directly specified in the text else indirectly said , understand it and calculate it.
# 3. Calculate duration_days as the number of working days between dates
# 4. Leave types: CASUAL, SICK, MATERNITY, PATERNITY.
# 5. For maternity and paternity leave, the current company policy is :
# • Maternity Leave: 26 weeks (182 days) for 1st & 2nd time, 12 weeks (84 days) for 3rd time onwards
# • Paternity Leave: 16 days per birth
# - Employees current leave balance for maternity and paternity leave is {maternity} and {paternity} respectively.Use these current balance to choose end date and duration with respect to the leave policy(maternity,paternity).
# 6. If dates are relative (tomorrow, next week), calculate actual dates based on today being {today_date}

# User text: "{text}"


# Return JSON with this exact structure:
# {{
#     "leave_type": "CASUAL|SICK|MATERNITY|PATERNITY",
#     "start_date": "YYYY-MM-DD",
#     "end_date": "YYYY-MM-DD", 
#     "duration_days": number of days requested directly or indirectly,
#     "reason": "For types like sick ,maternity and paternity take the reason as their leave type if specific reason is not provided in the context but for casual leave type if specific reason is not provided then set reason to null",
#     "backup_person": "name or null",
#     "confidence_score": 0-100,
#     "missing_info": ["list of missing required fields"],
#     "friendly_response": "conversational response to user"
    
# }}

# Examples:
# - "I need leave tomorrow" → reason should be null (not specific enough)
# - "I need leave for doctor appointment" → reason: "doctor appointment"
# - "family function" → reason: "family function"
# - "personal work" → reason: "personal work"
# """

logger = logging.getLogger(__name__)

# template_old=f"""
# You are a helpful HR assistant. Extract leave request details from the user's text and return them in JSON format.

# CONFUSION DETECTION :
# If the text is genuinely confusing, unclear, or doesn't make sense for a leave request, set "confusion_detected" to true and explain why.

# IMPORTANT RULES:
# 1. If no clear reason is provided, set reason to null
# 2. Always provide start_date and end_date in YYYY-MM-DD format.It is either directly specified in the text else indirectly said , understand it and calculate it.
# 3. Calculate duration_days as the number of working days between dates
# 4. Leave types: CASUAL, SICK, MATERNITY, PATERNITY.(Try to extract the leave type from the text by yourself if not specified explicitly in the text)
# 5. For maternity and paternity leave, the current company policy is :
# • Maternity Leave: 26 weeks (182 days) for 1st & 2nd time, 12 weeks (84 days) for 3rd time onwards
# • Paternity Leave: 16 days per birth
# - Employees current leave balance for maternity and paternity leave is {maternity} and {paternity} respectively.Use these current balance to choose end date and duration with respect to the leave policy(maternity,paternity).
# 6. If dates are relative (tomorrow, next week), calculate actual dates based on today being {today_date}
# 7.Try to extract the details as much as possible from the text better try to avoid this confusion detection unecessarily , only use it when the text is genuinely confusing or unclear.Like random words or random meaning that doesnt count for a sentence or leave request.
# User text: "{text}"


# Return JSON with this exact structure:
# {{
#     "confusion_detected": true/false,
#     "confusion_reason": "why this is confusing" OR null,
#     "leave_type": "CASUAL|SICK|MATERNITY|PATERNITY"(If leave type is not specifically mentioned, understand the text and know the situation of the user (for which he want the leave),then decide under which leave type it falls under),
#     "start_date": "YYYY-MM-DD",
#     "end_date": "YYYY-MM-DD", 
#     "duration_days": number of days requested directly or indirectly,
#     "reason": "For types like sick ,maternity and paternity take the reason as their leave type if specific reason is not provided in the context but for casual leave type try to get the reason from the user text itself as much as possible correctly , if its blank or there is no possiblity of extracting reason then set reason to null",
#     "backup_person": "name or null",
#     "confidence_score": 0-100,
#     "missing_info": ["list of missing required fields"],
#     "friendly_response": "conversational response to user"
    
# }}

# Examples:
# - "I need leave tomorrow" → reason should be null (not specific enough)
# - "I need leave for doctor appointment" → reason: "doctor appointment"
# - "family function" → reason: "family function"
# - "personal work" → reason: "personal work"

# """
# Configure the API
api_key = "AIzaSyCFz8nLkOQH6sDYYMQOoGHSZk0xjeTE2ok"
genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-2.0-flash-lite')

def extract_leave_details(text, today_date, maternity, paternity):
    """Extract leave details from natural language text using AI"""
    try:
        # Enhanced prompt to ensure reason is always provided
        template = f"""You are a helpful HR assistant. Extract leave request details from the user's text and return them in JSON format.

CONFUSION DETECTION AND SCOPE:
Your primary role is to extract and classify information, not to judge the validity of an employee's personal life. Use "confusion_detected" as a last resort and only in the following specific cases:

1.  **Logical or Factual Impossibility:** The request contains a clear contradiction with real-world facts or the leave types themselves.
    *   **Example of TRUE confusion:** "I am a boy and I need maternity leave because I am pregnant." (This is a biological impossibility).
    *   **Example of TRUE confusion:** "I need sick leave starting yesterday because I feel great today." (This is a logical contradiction).

2.  **Nonsensical or Gibberish Text:** The user's text is a random string of words with no discernible meaning or intent related to a leave request.
    *   **Example of TRUE confusion:** "blue car running leave paper why."

**IMPORTANT: What is NOT considered confusing:**
*   **Unusual Personal Reasons:** Do not flag a request just because the reason is strange or unconventional. If someone needs leave to "take care of my friend's sick iguana" or "attend a UFO-watching festival," it is a valid personal reason.
*   **Your Action:** For any unusual but logically possible reason, classify the `leave_type` as **CASUAL** and extract the reason as given.

IMPORTANT RULES:
1. If no clear reason is provided, set reason to null.
2. Always provide start_date and end_date in YYYY-MM-DD format. Calculate it if it's specified indirectly.
3. Calculate duration_days as the number of working days between the start and end dates.
4. Leave types and their definitions:
   • PATERNITY: Applies ONLY to the birth or adoption of a NEW child.
   • MATERNITY: Applies ONLY to an employee giving birth or adopting a NEW child.
   • SICK: Applies when the employee or a direct family member (e.g., spouse, child, parent) is sick. If the reason involves caring for a sick person who is NOT a direct family member (e.g., a friend, friend's wife, neighbor), the leave type is CASUAL.
   • CASUAL: This is the default for all other personal reasons. This INCLUDES childcare when a spouse is unavailable, personal work, family functions, emergencies, and caring for others who are not direct family members (like a sick friend or relative).
5. For MATERNITY and PATERNITY leave, IF AND ONLY IF the leave type has been correctly identified based on Rule #4, apply the following company policy to calculate the end_date and duration:
   • Maternity Leave: 26 weeks (182 days) for 1st & 2nd time, 12 weeks (84 days) for 3rd time onwards.
   • Paternity Leave: 16 days per birth.
   • Use the employee's current leave balance: maternity={maternity}, paternity={paternity}.
6. If dates are relative (tomorrow, next week), calculate actual dates based on today being {today_date}.
7. Only use confusion detection when the text is genuinely nonsensical for a leave request.

User text: "{text}"

Examples:
- "I need leave tomorrow" → reason should be null.
- "I need leave for doctor appointment" → leave_type: "SICK", reason: "doctor appointment".
- "my wife is out of town and I need to be home for my daughter" → leave_type: "CASUAL", reason: "Childcare due to wife being out of town".
- "I'm having a baby next week and need to apply for leave" → leave_type: "PATERNITY".
- "I need to take care of my friend's wife who is sick" → leave_type: "CASUAL", reason: "Caring for a sick friend's wife".

Return JSON with this exact structure:
{{
    "confusion_detected": ...,
    "confusion_reason": ...,
    "leave_type": ...,
    "start_date": ..., 
    "end_date": ...,
    "duration_days": ...,
    "reason": ...,
    "backup_person": ...,
    "confidence_score": ...,
    "missing_info": ...,
    "friendly_response": ...
}}"""
        response = model.generate_content(
            template,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=500,
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
        
        # Validate required fields
        required_fields = ['leave_type', 'start_date', 'end_date', 'duration_days']
        for field in required_fields:
            if field not in result:
                result[field] = None
                
        # Ensure confidence score is present
        if 'confidence_score' not in result:
            result['confidence_score'] = 50
            
        # Add missing_info if not present
        if 'missing_info' not in result:
            result['missing_info'] = []
        
        missing_info_val = result.get('missing_info')
        if not isinstance(missing_info_val, list):
            # This is the most likely error case: the AI returned a single string.
            if isinstance(missing_info_val, str) and missing_info_val: # Check for non-empty string
                # Correct the flow: take the string and put it into a list.
                result['missing_info'] = [missing_info_val]
                logger.warning(f"AI returned 'missing_info' as a string. Coerced to list: {result['missing_info']}")
            else:
                # It was None, an empty string, or another invalid type. Reset to a safe empty list.
                result['missing_info'] = []
        # Check if reason is missing/null and add to missing_info
        if not result.get('reason') or result.get('reason') in ['null', '', None]:
            result['reason'] = None
            if 'reason' not in result['missing_info']:
                result['missing_info'].append('reason')
        
        logger.info(f"AI extracted leave details: {result}")
        return result
        
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing AI JSON response: {e}")
        return {
            "error": "Could not parse leave request. Please try again with clearer details.",
            "confidence_score": 0
        }
    except Exception as e:
        logger.error(f"Error in AI processing: {e}")
        return {
            "error": "AI processing failed. Please use the form instead.",
            "confidence_score": 0
        }

