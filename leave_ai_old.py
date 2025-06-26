import google.generativeai as genai
import json
import re
from datetime import datetime, timedelta

# For Django integration
try:
    from django.contrib.auth.models import User
    DJANGO_AVAILABLE = True
except ImportError:
    DJANGO_AVAILABLE = False

class LeaveAI:
    def __init__(self):
        api_key = "AIzaSyCFz8nLkOQH6sDYYMQOoGHSZk0xjeTE2ok"
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash-lite')

    def extract_leave_details(self, user_message, user_balance=None):
        """Extract leave details from natural language input"""
        
        template = f"""
You are a friendly leave management assistant. Extract leave request details from the user's message.

User Message: "{user_message}"

Current User Balance (if available): {user_balance}

Extract the following information and respond in JSON format:

1. leave_type: "CASUAL", "SICK", "MATERNITY", or "PATERNITY" (infer from context)
2. start_date: YYYY-MM-DD format (if mentioned, otherwise null)
3. end_date: YYYY-MM-DD format (if mentioned, otherwise null) 
4. duration_days: number of days (if mentioned, otherwise null)
5. reason: brief reason mentioned by user (if no reason given, use "Personal leave" as default)
6. backup_person: name of backup person if mentioned
7. confidence_score: 0-100 (how confident you are about the extraction)
8. missing_info: list of missing required information
9. friendly_response: A casual, friendly response acknowledging their request

Guidelines:
- If user says "tomorrow", "next week", calculate approximate dates
- If they mention "a few days", "couple of days", estimate duration
- Be smart about inferring leave type from context (sick=medical, vacation=casual, baby=maternity/paternity)
- Today's date for reference: {datetime.now().strftime('%Y-%m-%d')}

Example Output:
```json
{{
    "leave_type": "CASUAL",
    "start_date": "2024-01-15", 
    "end_date": "2024-01-17",
    "duration_days": 3,
    "reason": "family vacation",
    "backup_person": null,
    "confidence_score": 85,
    "missing_info": ["backup_person"],
    "friendly_response": "Got it! You want 3 days off for a family vacation from Jan 15-17. Let me help you submit this request!"
}}
```
"""

        try:
            response = self.model.generate_content(template)
            cleaned_text = response.text.strip().replace('```json', '').replace('```', '')
            result = json.loads(cleaned_text)
            
            # FIXED: Ensure reason is never None
            if not result.get('reason'):
                result['reason'] = 'Personal leave'
            
            return result
        except Exception as e:
            return {
                "error": f"Failed to process request: {str(e)}",
                "friendly_response": "Sorry, I had trouble understanding your request. Could you try rephrasing it?"
            }

    def generate_leave_summary(self, leave_request, conflicts=None, balance_info=None):
        """Generate a friendly summary of the leave request for managers"""
        
        # Convert leave_request object to dict-like for template
        leave_info = {
            'employee_username': leave_request.employee.username,
            'leave_type': leave_request.get_leave_type_display(),
            'start_date': str(leave_request.start_date),
            'end_date': str(leave_request.end_date),
            'reason': leave_request.reason,
            'backup_person': leave_request.backup_person or 'Not specified',
            'duration': (leave_request.end_date - leave_request.start_date).days + 1
        }
        
        template = f"""
You are a helpful assistant summarizing a leave request for managers. Make it conversational and highlight important information.

Leave Request Details:
- Employee: {leave_info['employee_username']}
- Leave Type: {leave_info['leave_type']}
- Start Date: {leave_info['start_date']}
- End Date: {leave_info['end_date']}
- Duration: {leave_info['duration']} days
- Reason: {leave_info['reason']}
- Backup Person: {leave_info['backup_person']}

Balance Information: {balance_info}
Conflicts: {conflicts}

Create a friendly, professional summary that:
1. Introduces the request naturally
2. Highlights any balance issues or conflicts
3. Suggests appropriate actions for managers
4. Uses emojis appropriately
5. Keeps a helpful, conversational tone

Return as JSON with 'summary' field containing the formatted text.
"""

        try:
            response = self.model.generate_content(template)
            cleaned_text = response.text.strip().replace('```json', '').replace('```', '')
            result = json.loads(cleaned_text)
            return result.get('summary', 'Leave request summary unavailable')
        except Exception as e:
            return f"📄 New leave request from {leave_info['employee_username']} for {leave_info['leave_type']}"

    def generate_response_message(self, action, leave_request, additional_info=None):
        """Generate friendly response messages for different actions"""
        
        # Convert leave_request object to dict-like for template
        leave_info = {
            'leave_type': leave_request.get_leave_type_display(),
            'start_date': str(leave_request.start_date),
            'end_date': str(leave_request.end_date)
        }
        
        template = f"""
You are a friendly leave management assistant. Generate a warm, helpful response message.

Action: {action}
Leave Request: {leave_info['leave_type']} from {leave_info['start_date']} to {leave_info['end_date']}
Additional Info: {additional_info}

Generate appropriate response for these actions:
- "approved": Congratulatory message
- "rejected": Sympathetic but professional
- "document_requested": Helpful guidance
- "compensatory_offered": Explain options clearly
- "unpaid_offered": Explain what this means
- "submitted": Confirm submission

Keep it:
- Friendly and conversational
- Clear about next steps
- Encouraging and supportive
- Use emojis appropriately

Return as JSON with 'message' field.
"""

        try:
            response = self.model.generate_content(template)
            cleaned_text = response.text.strip().replace('```json', '').replace('```', '')
            result = json.loads(cleaned_text)
            return result.get('message', 'Your leave request has been processed.')
        except Exception as e:
            return 'Your leave request has been processed.'

    def chat_with_user(self, user_message, context=None):
        """General chat function for leave-related queries"""
        
        template = f"""
You are a friendly leave management assistant. Respond to the user's query about leaves, policies, or procedures.

User Message: "{user_message}"
Context: {context}

Guidelines:
- Be conversational and helpful
- If they're asking about leave policies, explain clearly
- If they want to check balance, guide them to use /leave-balance
- If they want to apply for leave, guide them through the process
- Use simple language and emojis
- Be encouraging and supportive

Return as JSON with 'response' field containing your friendly response.
"""

        try:
            response = self.model.generate_content(template)
            cleaned_text = response.text.strip().replace('```json', '').replace('```', '')
            result = json.loads(cleaned_text)
            return result.get('response', 'I\'m here to help with your leave-related questions!')
        except Exception as e:
            return 'I\'m here to help with your leave-related questions!'

# Global instance
leave_ai = LeaveAI()