# from django.http import JsonResponse
# from .slack_utils import slack_client, get_or_create_user, is_manager, is_in_manager_channel
# from .models import Department
# from datetime import datetime, timedelta
# from slack_sdk.errors import SlackApiError
# import threading
# import logging
# import logging
# import threading

# logger = logging.getLogger(__name__)

# def handle_team_calendar(request):
#     """Handle team calendar display (manager only) - Interactive form for filtering"""
#     try:
#         # Open interactive modal form for managers to specify what they want
#         user_id = request.POST.get('user_id')
        
#         # Get list of departments for dropdown
#         departments = Department.objects.all()
#         department_options = [
#             {"text": {"type": "plain_text", "text": "All Departments"}, "value": "ALL"}
#         ]
#         for dept in departments:
#             department_options.append({
#                 "text": {"type": "plain_text", "text": dept.name}, 
#                 "value": str(dept.id)
#             })
        
#         # Get current date info for default values
#         today = datetime.now().date()
        
#         view = {
#             "type": "modal",
#             "callback_id": "team_calendar_filter",
#             "title": {"type": "plain_text", "text": "Team Calendar Filter"},
#             "submit": {"type": "plain_text", "text": "Generate Calendar"},
#             "blocks": [
#                 {
#                     "type": "header",
#                     "text": {
#                         "type": "plain_text",
#                         "text": "📅 Customize Your Team Calendar",
#                         "emoji": True
#                     }
#                 },
#                 {
#                     "type": "section",
#                     "text": {
#                         "type": "mrkdwn",
#                         "text": "Select the filters below to generate a customized team calendar view:\n\n✅ *All matching records will be displayed (no limits)*\n🔍 Use filters to narrow down results for specific needs"
#                     }
#                 },
#                 {
#                     "type": "divider"
#                 },
#                 {
#                     "type": "input",
#                     "block_id": "calendar_month",
#                     "element": {
#                         "type": "static_select",
#                         "action_id": "month_select",
#                         "placeholder": {"type": "plain_text", "text": "Select month to view"},
#                         "initial_option": {
#                             "text": {"type": "plain_text", "text": today.strftime('%B %Y')}, 
#                             "value": today.strftime('%Y-%m')
#                         },
#                         "options": [
#                             # Current year months
#                             {"text": {"type": "plain_text", "text": f"January {today.year}"}, "value": f"{today.year}-01"},
#                             {"text": {"type": "plain_text", "text": f"February {today.year}"}, "value": f"{today.year}-02"},
#                             {"text": {"type": "plain_text", "text": f"March {today.year}"}, "value": f"{today.year}-03"},
#                             {"text": {"type": "plain_text", "text": f"April {today.year}"}, "value": f"{today.year}-04"},
#                             {"text": {"type": "plain_text", "text": f"May {today.year}"}, "value": f"{today.year}-05"},
#                             {"text": {"type": "plain_text", "text": f"June {today.year}"}, "value": f"{today.year}-06"},
#                             {"text": {"type": "plain_text", "text": f"July {today.year}"}, "value": f"{today.year}-07"},
#                             {"text": {"type": "plain_text", "text": f"August {today.year}"}, "value": f"{today.year}-08"},
#                             {"text": {"type": "plain_text", "text": f"September {today.year}"}, "value": f"{today.year}-09"},
#                             {"text": {"type": "plain_text", "text": f"October {today.year}"}, "value": f"{today.year}-10"},
#                             {"text": {"type": "plain_text", "text": f"November {today.year}"}, "value": f"{today.year}-11"},
#                             {"text": {"type": "plain_text", "text": f"December {today.year}"}, "value": f"{today.year}-12"},
#                             # Next year months (first 6 months)
#                             {"text": {"type": "plain_text", "text": f"January {today.year + 1}"}, "value": f"{today.year + 1}-01"},
#                             {"text": {"type": "plain_text", "text": f"February {today.year + 1}"}, "value": f"{today.year + 1}-02"},
#                             {"text": {"type": "plain_text", "text": f"March {today.year + 1}"}, "value": f"{today.year + 1}-03"},
#                             {"text": {"type": "plain_text", "text": f"April {today.year + 1}"}, "value": f"{today.year + 1}-04"},
#                             {"text": {"type": "plain_text", "text": f"May {today.year + 1}"}, "value": f"{today.year + 1}-05"},
#                             {"text": {"type": "plain_text", "text": f"June {today.year + 1}"}, "value": f"{today.year + 1}-06"},
#                             # Previous year months (last 6 months)
#                             {"text": {"type": "plain_text", "text": f"July {today.year - 1}"}, "value": f"{today.year - 1}-07"},
#                             {"text": {"type": "plain_text", "text": f"August {today.year - 1}"}, "value": f"{today.year - 1}-08"},
#                             {"text": {"type": "plain_text", "text": f"September {today.year - 1}"}, "value": f"{today.year - 1}-09"},
#                             {"text": {"type": "plain_text", "text": f"October {today.year - 1}"}, "value": f"{today.year - 1}-10"},
#                             {"text": {"type": "plain_text", "text": f"November {today.year - 1}"}, "value": f"{today.year - 1}-11"},
#                             {"text": {"type": "plain_text", "text": f"December {today.year - 1}"}, "value": f"{today.year - 1}-12"}
#                         ]
#                     },
#                     "label": {"type": "plain_text", "text": "📅 Select Month"}
#                 },
#                 {
#                     "type": "input",
#                     "block_id": "custom_start_date",
#                     "optional": True,
#                     "element": {
#                         "type": "datepicker",
#                         "action_id": "start_date_select",
#                         "initial_date": today.strftime('%Y-%m-%d'),
#                         "placeholder": {"type": "plain_text", "text": "Select start date"}
#                     },
#                     "label": {"type": "plain_text", "text": "📅 Custom Start Date (Optional - overrides month selection)"}
#                 },
#                 {
#                     "type": "input",
#                     "block_id": "custom_end_date",
#                     "optional": True,
#                     "element": {
#                         "type": "datepicker",
#                         "action_id": "end_date_select",
#                         "initial_date": today.strftime('%Y-%m-%d'),
#                         "placeholder": {"type": "plain_text", "text": "Select end date"}
#                     },
#                     "label": {"type": "plain_text", "text": "📅 Custom End Date (Optional - overrides month selection)"}
#                 },
#                 {
#                     "type": "input",
#                     "block_id": "department_filter",
#                     "element": {
#                         "type": "static_select",
#                         "action_id": "department_select",
#                         "placeholder": {"type": "plain_text", "text": "Choose department"},
#                         "initial_option": department_options[0],
#                         "options": department_options
#                     },
#                     "label": {"type": "plain_text", "text": "🏢 Department Filter"}
#                 },
#                 {
#                     "type": "input",
#                     "block_id": "status_filter",
#                     "element": {
#                         "type": "checkboxes",
#                         "action_id": "status_select",
#                         "initial_options": [
#                             {"text": {"type": "plain_text", "text": "Pending Approval"}, "value": "PENDING"},
#                             {"text": {"type": "plain_text", "text": "Approved"}, "value": "APPROVED"}
#                         ],
#                         "options": [
#                             {"text": {"type": "plain_text", "text": "Pending Approval"}, "value": "PENDING"},
#                             {"text": {"type": "plain_text", "text": "Approved"}, "value": "APPROVED"},
#                             {"text": {"type": "plain_text", "text": "Rejected"}, "value": "REJECTED"},
#                             {"text": {"type": "plain_text", "text": "Document Required"}, "value": "DOCS"},
#                             {"text": {"type": "plain_text", "text": "Cancelled"}, "value": "CANCELLED"}
#                         ]
#                     },
#                     "label": {"type": "plain_text", "text": "📊 Leave Status (Select all that apply)"}
#                 },
#                 {
#                     "type": "input",
#                     "block_id": "leave_type_filter",
#                     "optional": True,
#                     "element": {
#                         "type": "checkboxes",
#                         "action_id": "leave_type_select",
#                         "options": [
#                             {"text": {"type": "plain_text", "text": "Casual Leave"}, "value": "CASUAL"},
#                             {"text": {"type": "plain_text", "text": "Sick Leave"}, "value": "SICK"},
#                             {"text": {"type": "plain_text", "text": "Maternity Leave"}, "value": "MATERNITY"},
#                             {"text": {"type": "plain_text", "text": "Paternity Leave"}, "value": "PATERNITY"}
#                         ]
#                     },
#                     "label": {"type": "plain_text", "text": "📋 Leave Types (Optional - leave empty for all types)"}
#                 },
#                 {
#                     "type": "input",
#                     "block_id": "display_options",
#                     "optional": True,
#                     "element": {
#                         "type": "checkboxes",
#                         "action_id": "display_select",
#                         "options": [
#                             {"text": {"type": "plain_text", "text": "Show employee details"}, "value": "SHOW_DETAILS"},
#                             {"text": {"type": "plain_text", "text": "Show leave reasons"}, "value": "SHOW_REASONS"},
#                             {"text": {"type": "plain_text", "text": "Show conflict analysis"}, "value": "SHOW_CONFLICTS"},
#                             {"text": {"type": "plain_text", "text": "Group by department"}, "value": "GROUP_DEPT"}
#                         ]
#                     },
#                     "label": {"type": "plain_text", "text": "⚙️ Display Options (Optional)"}
#                 },
#                 {
#                     "type": "input",
#                     "block_id": "sort_option",
#                     "optional": True,
#                     "element": {
#                         "type": "static_select",
#                         "action_id": "sort_select",
#                         "placeholder": {"type": "plain_text", "text": "Choose sorting order"},
#                         "initial_option": {"text": {"type": "plain_text", "text": "Date (Earliest First)"}, "value": "DATE_ASC"},
#                         "options": [
#                             {"text": {"type": "plain_text", "text": "Date (Earliest First)"}, "value": "DATE_ASC"},
#                             {"text": {"type": "plain_text", "text": "Date (Latest First)"}, "value": "DATE_DESC"},
#                             {"text": {"type": "plain_text", "text": "Employee Name (A-Z)"}, "value": "EMPLOYEE_ASC"},
#                             {"text": {"type": "plain_text", "text": "Employee Name (Z-A)"}, "value": "EMPLOYEE_DESC"},
#                             {"text": {"type": "plain_text", "text": "Leave Type"}, "value": "TYPE"},
#                             {"text": {"type": "plain_text", "text": "Status (Pending First)"}, "value": "STATUS_PENDING"},
#                             {"text": {"type": "plain_text", "text": "Duration (Longest First)"}, "value": "DURATION_DESC"}
#                         ]
#                     },
#                     "label": {"type": "plain_text", "text": "📈 Sort Results By (Optional)"}
#                 }
#             ]
#         }
        
#         response = slack_client.views_open(
#             trigger_id=request.POST.get('trigger_id'),
#             view=view
#         )
#         return JsonResponse({'text': 'Opening team calendar filter...'})
        
#     except Exception as e:
#         logger.error(f"Error opening team calendar filter: {e}")
#         return JsonResponse({'text': 'Error opening calendar filter'}, status=200)



from django.http import JsonResponse
from .slack_utils import slack_client, get_or_create_user, is_manager, is_in_manager_channel
from .models import Department
from datetime import datetime, timedelta
from slack_sdk.errors import SlackApiError
import threading
import logging

logger = logging.getLogger(__name__)

def handle_team_calendar(request):
    """Handle team calendar display - supports both AI text and traditional form"""
    try:
        text = request.POST.get('text', '').strip()
        user_id = request.POST.get('user_id')
        trigger_id = request.POST.get('trigger_id')
        
        # AI PROCESSING PATH - if text is provided
        if text:
            logger.info(f"AI_TEAM_CALENDAR: Processing AI request for user {user_id}: '{text}'")
            
            def process_ai_calendar_request():
                """Background function to process AI calendar request"""
                try:
                    from .calendar_ai import extract_calendar_query
                    import json
                    from datetime import datetime
                    
                    today_date = datetime.now().date()
                    ai_response = extract_calendar_query(text, today_date)
                    
                    # Log AI response for debugging
                    logger.info(f"AI_TEAM_CALENDAR_RESPONSE: {json.dumps(ai_response, indent=2, default=str)}")
                    
                    if 'error' in ai_response:
                        slack_client.chat_postMessage(
                            channel=user_id,
                            text=f"❌ AI Error: {ai_response['error']}"
                        )
                        return
                    
                    # Use existing calendar processing logic
                    query_params = {
                        'user_id': user_id,
                        'start_date': ai_response['start_date'],
                        'end_date': ai_response['end_date'],
                        'leave_type': ai_response.get('leave_type', 'ALL'),
                        'status': ai_response.get('status', 'ALL'),
                        'employee_filter': ai_response.get('employee_filter'),
                        'department_filter': ai_response.get('department_filter'),
                        'team_filter': ai_response.get('team_filter'),
                        'display_options': ai_response.get('display_options', ['SHOW_DETAILS']),
                        'sort_option': ai_response.get('sort_option', 'DATE_ASC'),
                        'source': 'ai',
                        'query_description': ai_response.get('query_description', f'AI Calendar Query: {text}'),
                        'original_query': text
                    }
                    
                    result = process_team_calendar_query(query_params)
                    
                    # Send calendar results to the user's DM instead of a channel
                    if result.get('success'):
                        # Add AI indicator to response
                        ai_header = {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"🤖 *AI-Generated Team Calendar*\n📝 *Query:* {text}\n📊 *Period:* {ai_response['start_date']} to {ai_response['end_date']}"
                            }
                        }
                        
                        blocks = [ai_header] + result.get('blocks', [])
                        
                        # FIXED: Send to user's DM instead of a channel that might not exist
                        slack_client.chat_postMessage(
                            channel=user_id,
                            blocks=blocks,
                            text=f"🤖 AI Calendar Results: {ai_response.get('query_description', text)}"
                        )
                    else:
                        slack_client.chat_postMessage(
                            channel=user_id,
                            text=f"❌ {result.get('message', 'Error processing calendar request')}"
                        )
                        
                except Exception as e:
                    logger.error(f"AI_TEAM_CALENDAR_EXCEPTION: {str(e)}")
                    slack_client.chat_postMessage(
                        channel=user_id,
                        text=f"❌ Error processing AI calendar request: {str(e)}. Please use `/team-calendar` without text to open the form."
                    )
            
            # Start background processing
            thread = threading.Thread(target=process_ai_calendar_request)
            thread.daemon = True
            thread.start()
            
            return JsonResponse({'text': '🤖 Processing your calendar request with AI...'})
        
        # TRADITIONAL FORM PATH - IMMEDIATE MODAL OPENING (CRITICAL FIX)
        else:
            def open_calendar_modal_background():
                """Background function to open calendar modal"""
                try:
                    departments = Department.objects.all()
                    department_options = [
                        {"text": {"type": "plain_text", "text": "All Departments"}, "value": "ALL"}
                    ]
                    for dept in departments:
                        department_options.append({
                            "text": {"type": "plain_text", "text": dept.name}, 
                            "value": str(dept.id)
                        })
                    
                    today = datetime.now().date()
                
                # BUILD VIEW IMMEDIATELY
                    view = {
                "type": "modal",
                "callback_id": "team_calendar_filter",
                "title": {"type": "plain_text", "text": "Team Calendar Filter"},
                "submit": {"type": "plain_text", "text": "Generate Calendar"},
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": "📅 Customize Your Team Calendar",
                            "emoji": True
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "Select the filters below to generate a customized team calendar view:\n\n✅ *All matching records will be displayed (no limits)*\n🔍 Use filters to narrow down results for specific needs"
                        }
                    },
                    {
                        "type": "divider"
                    },
                    {
                        "type": "input",
                        "block_id": "calendar_month",
                        "element": {
                            "type": "static_select",
                            "action_id": "month_select",
                            "placeholder": {"type": "plain_text", "text": "Select month to view"},
                            "initial_option": {
                                "text": {"type": "plain_text", "text": today.strftime('%B %Y')}, 
                                "value": today.strftime('%Y-%m')
                            },
                            "options": [
                                # Current year months
                                {"text": {"type": "plain_text", "text": f"January {today.year}"}, "value": f"{today.year}-01"},
                                {"text": {"type": "plain_text", "text": f"February {today.year}"}, "value": f"{today.year}-02"},
                                {"text": {"type": "plain_text", "text": f"March {today.year}"}, "value": f"{today.year}-03"},
                                {"text": {"type": "plain_text", "text": f"April {today.year}"}, "value": f"{today.year}-04"},
                                {"text": {"type": "plain_text", "text": f"May {today.year}"}, "value": f"{today.year}-05"},
                                {"text": {"type": "plain_text", "text": f"June {today.year}"}, "value": f"{today.year}-06"},
                                {"text": {"type": "plain_text", "text": f"July {today.year}"}, "value": f"{today.year}-07"},
                                {"text": {"type": "plain_text", "text": f"August {today.year}"}, "value": f"{today.year}-08"},
                                {"text": {"type": "plain_text", "text": f"September {today.year}"}, "value": f"{today.year}-09"},
                                {"text": {"type": "plain_text", "text": f"October {today.year}"}, "value": f"{today.year}-10"},
                                {"text": {"type": "plain_text", "text": f"November {today.year}"}, "value": f"{today.year}-11"},
                                {"text": {"type": "plain_text", "text": f"December {today.year}"}, "value": f"{today.year}-12"},
                                # Next year months (first 6 months)
                                {"text": {"type": "plain_text", "text": f"January {today.year + 1}"}, "value": f"{today.year + 1}-01"},
                                {"text": {"type": "plain_text", "text": f"February {today.year + 1}"}, "value": f"{today.year + 1}-02"},
                                {"text": {"type": "plain_text", "text": f"March {today.year + 1}"}, "value": f"{today.year + 1}-03"},
                                {"text": {"type": "plain_text", "text": f"April {today.year + 1}"}, "value": f"{today.year + 1}-04"},
                                {"text": {"type": "plain_text", "text": f"May {today.year + 1}"}, "value": f"{today.year + 1}-05"},
                                {"text": {"type": "plain_text", "text": f"June {today.year + 1}"}, "value": f"{today.year + 1}-06"},
                                # Previous year months (last 6 months)
                                {"text": {"type": "plain_text", "text": f"July {today.year - 1}"}, "value": f"{today.year - 1}-07"},
                                {"text": {"type": "plain_text", "text": f"August {today.year - 1}"}, "value": f"{today.year - 1}-08"},
                                {"text": {"type": "plain_text", "text": f"September {today.year - 1}"}, "value": f"{today.year - 1}-09"},
                                {"text": {"type": "plain_text", "text": f"October {today.year - 1}"}, "value": f"{today.year - 1}-10"},
                                {"text": {"type": "plain_text", "text": f"November {today.year - 1}"}, "value": f"{today.year - 1}-11"},
                                {"text": {"type": "plain_text", "text": f"December {today.year - 1}"}, "value": f"{today.year - 1}-12"}
                            ]
                        },
                        "label": {"type": "plain_text", "text": "📅 Select Month"}
                    },
                    {
                        "type": "input",
                        "block_id": "custom_start_date",
                        "optional": True,
                        "element": {
                            "type": "datepicker",
                            "action_id": "start_date_select",
                            "initial_date": today.strftime('%Y-%m-%d'),
                            "placeholder": {"type": "plain_text", "text": "Select start date"}
                        },
                        "label": {"type": "plain_text", "text": "📅 Custom Start Date (Optional - overrides month selection)"}
                    },
                    {
                        "type": "input",
                        "block_id": "custom_end_date",
                        "optional": True,
                        "element": {
                            "type": "datepicker",
                            "action_id": "end_date_select",
                            "initial_date": today.strftime('%Y-%m-%d'),
                            "placeholder": {"type": "plain_text", "text": "Select end date"}
                        },
                        "label": {"type": "plain_text", "text": "📅 Custom End Date (Optional - overrides month selection)"}
                    },
                    {
                        "type": "input",
                        "block_id": "department_filter",
                        "element": {
                            "type": "static_select",
                            "action_id": "department_select",
                            "placeholder": {"type": "plain_text", "text": "Choose department"},
                            "initial_option": department_options[0],
                            "options": department_options
                        },
                        "label": {"type": "plain_text", "text": "🏢 Department Filter"}
                    },
                    {
                        "type": "input",
                        "block_id": "status_filter",
                        "element": {
                            "type": "checkboxes",
                            "action_id": "status_select",
                            "initial_options": [
                                {"text": {"type": "plain_text", "text": "Pending Approval"}, "value": "PENDING"},
                                {"text": {"type": "plain_text", "text": "Approved"}, "value": "APPROVED"}
                            ],
                            "options": [
                                {"text": {"type": "plain_text", "text": "Pending Approval"}, "value": "PENDING"},
                                {"text": {"type": "plain_text", "text": "Approved"}, "value": "APPROVED"},
                                {"text": {"type": "plain_text", "text": "Rejected"}, "value": "REJECTED"},
                                {"text": {"type": "plain_text", "text": "Document Required"}, "value": "DOCS"},
                                {"text": {"type": "plain_text", "text": "Cancelled"}, "value": "CANCELLED"}
                            ]
                        },
                        "label": {"type": "plain_text", "text": "📊 Leave Status (Select all that apply)"}
                    },
                    {
                        "type": "input",
                        "block_id": "leave_type_filter",
                        "optional": True,
                        "element": {
                            "type": "checkboxes",
                            "action_id": "leave_type_select",
                            "options": [
                                {"text": {"type": "plain_text", "text": "Casual Leave"}, "value": "CASUAL"},
                                {"text": {"type": "plain_text", "text": "Sick Leave"}, "value": "SICK"},
                                {"text": {"type": "plain_text", "text": "Maternity Leave"}, "value": "MATERNITY"},
                                {"text": {"type": "plain_text", "text": "Paternity Leave"}, "value": "PATERNITY"}
                            ]
                        },
                        "label": {"type": "plain_text", "text": "📋 Leave Types (Optional - leave empty for all types)"}
                    },
                    {
                        "type": "input",
                        "block_id": "display_options",
                        "optional": True,
                        "element": {
                            "type": "checkboxes",
                            "action_id": "display_select",
                            "options": [
                                {"text": {"type": "plain_text", "text": "Show employee details"}, "value": "SHOW_DETAILS"},
                                {"text": {"type": "plain_text", "text": "Show leave reasons"}, "value": "SHOW_REASONS"},
                                {"text": {"type": "plain_text", "text": "Show conflict analysis"}, "value": "SHOW_CONFLICTS"},
                                {"text": {"type": "plain_text", "text": "Group by department"}, "value": "GROUP_DEPT"}
                            ]
                        },
                        "label": {"type": "plain_text", "text": "⚙️ Display Options (Optional)"}
                    },
                    {
                        "type": "input",
                        "block_id": "sort_option",
                        "optional": True,
                        "element": {
                            "type": "static_select",
                            "action_id": "sort_select",
                            "placeholder": {"type": "plain_text", "text": "Choose sorting order"},
                            "initial_option": {"text": {"type": "plain_text", "text": "Date (Earliest First)"}, "value": "DATE_ASC"},
                            "options": [
                                {"text": {"type": "plain_text", "text": "Date (Earliest First)"}, "value": "DATE_ASC"},
                                {"text": {"type": "plain_text", "text": "Date (Latest First)"}, "value": "DATE_DESC"},
                                {"text": {"type": "plain_text", "text": "Employee Name (A-Z)"}, "value": "EMPLOYEE_ASC"},
                                {"text": {"type": "plain_text", "text": "Employee Name (Z-A)"}, "value": "EMPLOYEE_DESC"},
                                {"text": {"type": "plain_text", "text": "Leave Type"}, "value": "TYPE"},
                                {"text": {"type": "plain_text", "text": "Status (Pending First)"}, "value": "STATUS_PENDING"},
                                {"text": {"type": "plain_text", "text": "Duration (Longest First)"}, "value": "DURATION_DESC"}
                            ]
                        },
                        "label": {"type": "plain_text", "text": "📈 Sort Results By (Optional)"}
                    }
                ]
            }             
                    slack_client.views_open(
                trigger_id=trigger_id,
                view=view
            )
            
                except SlackApiError as e:
                    if 'expired_trigger_id' in str(e):
                        logger.error(f"Trigger ID expired for team calendar: {e}")
                        try:
                            slack_client.chat_postMessage(
                                channel=user_id,
                                text="⚠️ The team calendar form couldn't open (request timed out). Please try the command again.\n\n**Alternative:** Use AI text mode like: `/team-calendar show me this week's leaves`"
                            )
                        except Exception as fallback_error:
                            logger.error(f"Fallback message failed: {fallback_error}")
                    else:
                        logger.error(f"Slack API error: {e}")
                        try:
                            slack_client.chat_postMessage(
                                channel=user_id,
                                text=f"❌ Error opening calendar form. Please try again."
                            )
                        except:
                            pass
                except Exception as e:
                    logger.error(f"Error opening calendar modal: {e}")
                    try:
                        slack_client.chat_postMessage(
                            channel='leave_app',
                            text="❌ Error opening calendar form. Please try again."
                        )
                    except:
                        pass

        # Start background thread for modal opening
        thread = threading.Thread(target=open_calendar_modal_background)
        thread.daemon = True
        thread.start()

        # Return immediate response (prevents timeout)
        return JsonResponse({'text': '⏳ Opening team calendar form...'})
    except Exception as e:
        logger.error(f"Error in handle_team_calendar: {e}")
        return JsonResponse({'text': 'Error processing team calendar request'}, status=200)

def process_team_calendar_query(query_params):
    """Process team calendar query and return formatted results"""
    try:
        from .models import LeaveRequest, UserRole, Department, Team
        from .leave_utils import create_leave_block
        
        # Extract parameters
        start_date = query_params.get('start_date')
        end_date = query_params.get('end_date')
        
        # Build base query for date range
        query = LeaveRequest.objects.filter(
            start_date__lte=end_date,
            end_date__gte=start_date
        )
        
        # Apply leave type filter
        leave_type = query_params.get('leave_type', 'ALL')
        if leave_type != 'ALL':
            if leave_type == 'CASUAL':
                query = query.filter(leave_type='CASUAL')
            elif leave_type == 'SICK':
                query = query.filter(leave_type='SICK')
            elif leave_type == 'MATERNITY':
                query = query.filter(leave_type='MATERNITY')
            elif leave_type == 'PATERNITY':
                query = query.filter(leave_type='PATERNITY')
        
        # Apply status filter - FIXED to handle all status variations
        status = query_params.get('status', 'ALL')
        if status != 'ALL':
            if status == 'PENDING':
                query = query.filter(status__in=['PENDING', 'PENDING_DOCS', 'DOCS_SUBMITTED', 'DOCS_PENDING_LATER'])
            elif status == 'APPROVED':
                query = query.filter(status__in=['APPROVED', 'APPROVED_UNPAID', 'APPROVED_COMPENSATORY'])
            elif status == 'REJECTED':
                query = query.filter(status='REJECTED')
            else:
                query = query.filter(status=status)
        
        # Apply department filter - FIXED to handle department name properly
        department_filter = query_params.get('department_filter')
        if department_filter and department_filter != 'ALL':
            try:
                # Try to find department by name (case-insensitive)
                dept = Department.objects.filter(name__icontains=department_filter).first()
                if dept:
                    query = query.filter(employee__userrole__department=dept)
                else:
                    # If no department found, try exact match
                    query = query.filter(employee__userrole__department__name__iexact=department_filter)
            except Department.DoesNotExist:
                # If department doesn't exist, return empty result
                query = query.none()
        
        # Apply employee filter - NEWLY ADDED
        employee_filter = query_params.get('employee_filter')
        if employee_filter:
            # Filter by employee name (partial match)
            query = query.filter(employee__username__icontains=employee_filter)
        
        # Apply team filter - FIXED to use correct relationship
        team_filter = query_params.get('team_filter')
        if team_filter:
            try:
                # Find team by name (case-insensitive)
                team = Team.objects.filter(name__icontains=team_filter).first()
                if team:
                    # Filter by users who are members OR admins of this team
                    team_user_ids = list(team.members.values_list('id', flat=True)) + list(team.admins.values_list('id', flat=True))
                    query = query.filter(employee_id__in=team_user_ids)
                else:
                    # If no team found, return empty result
                    query = query.none()
            except Team.DoesNotExist:
                # If team doesn't exist, return empty result
                query = query.none()
        
        # Apply sorting
        sort_option = query_params.get('sort_option', 'DATE_ASC')
        if sort_option == 'DATE_ASC':
            leaves = query.order_by('start_date', 'employee__username')
        elif sort_option == 'DATE_DESC':
            leaves = query.order_by('-start_date', 'employee__username')
        elif sort_option == 'EMPLOYEE_ASC':
            leaves = query.order_by('employee__username', 'start_date')
        elif sort_option == 'EMPLOYEE_DESC':
            leaves = query.order_by('-employee__username', 'start_date')
        elif sort_option == 'TYPE':
            leaves = query.order_by('leave_type', 'start_date')
        elif sort_option == 'STATUS_PENDING':
            # Put pending statuses first
            leaves = query.extra(
                select={
                    'status_priority': """
                        CASE 
                            WHEN status LIKE 'PENDING%' THEN 1 
                            WHEN status LIKE 'DOCS%' THEN 2 
                            WHEN status LIKE 'APPROVED%' THEN 3
                            ELSE 4 
                        END
                    """
                }
            ).order_by('status_priority', 'start_date')
        elif sort_option == 'DURATION_DESC':
            leaves = query.extra(
                select={'duration': '(end_date - start_date + 1)'}
            ).order_by('-duration', 'start_date')
        else:
            leaves = query.order_by('start_date', 'employee__username')
        
        # Build response blocks
        blocks = []
        display_options = query_params.get('display_options', ['SHOW_DETAILS'])
        
        if not leaves.exists():
            # No results found
            no_results_text = f"🔍 *No leaves found matching your criteria*\n\n"
            no_results_text += f"**Filters Applied:**\n"
            no_results_text += f"• Period: {start_date} to {end_date}\n"
            if department_filter and department_filter != 'ALL':
                no_results_text += f"• Department: {department_filter}\n"
            if leave_type != 'ALL':
                no_results_text += f"• Leave Type: {leave_type}\n"
            if status != 'ALL':
                no_results_text += f"• Status: {status}\n"
            if employee_filter:
                no_results_text += f"• Employee: {employee_filter}\n"
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": no_results_text
                }
            })
        else:
            # FIXED: Implement pagination to respect Slack's 50-block limit
            MAX_BLOCKS = 45  # Leave room for header and summary blocks
            
            # Group leaves by employee for cleaner display
            employee_groups = {}
            for leave in leaves:
                employee_key = leave.employee.username
                if employee_key not in employee_groups:
                    employee_groups[employee_key] = {
                        'employee': leave.employee,
                        'leaves': [],
                        'department': None
                    }
                    # Get department info
                    user_role = UserRole.objects.filter(user=leave.employee).first()
                    employee_groups[employee_key]['department'] = user_role.department.name if user_role and user_role.department else 'No Department'
                
                employee_groups[employee_key]['leaves'].append(leave)
            
            # Calculate how many entries we can show
            total_employees = len(employee_groups)
            blocks_used = 0
            employees_shown = 0
            
            # Check if grouping by department is requested
            if 'GROUP_DEPT' in display_options:
                # Group by department first, then by employee
                dept_groups = {}
                for emp_key, emp_data in employee_groups.items():
                    dept_name = emp_data['department']
                    if dept_name not in dept_groups:
                        dept_groups[dept_name] = {}
                    dept_groups[dept_name][emp_key] = emp_data
                
                for dept_name, dept_employees in dept_groups.items():
                    if blocks_used >= MAX_BLOCKS:
                        break
                        
                    dept_header = {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"🏢 *{dept_name}* ({sum(len(emp['leaves']) for emp in dept_employees.values())} leaves)"
                        }
                    }
                    blocks.append(dept_header)
                    blocks_used += 1
                    
                    # Show employees in this department (with limit)
                    for emp_key, emp_data in sorted(dept_employees.items()):
                        if blocks_used >= MAX_BLOCKS:
                            break
                            
                        emp_blocks = create_employee_leave_blocks_limited(emp_data, display_options, max_leaves=3)
                        if blocks_used + len(emp_blocks) <= MAX_BLOCKS:
                            blocks.extend(emp_blocks)
                            blocks_used += len(emp_blocks)
                            employees_shown += 1
                        else:
                            break
                    
                    if blocks_used < MAX_BLOCKS:
                        blocks.append({"type": "divider"})
                        blocks_used += 1
            else:
                # Regular employee grouping with pagination
                for emp_key, emp_data in sorted(employee_groups.items()):
                    if blocks_used >= MAX_BLOCKS:
                        break
                        
                    emp_blocks = create_employee_leave_blocks_limited(emp_data, display_options, max_leaves=3)
                    if blocks_used + len(emp_blocks) <= MAX_BLOCKS:
                        blocks.extend(emp_blocks)
                        blocks_used += len(emp_blocks)
                        employees_shown += 1
                    else:
                        break
            
            # Add pagination info if we hit the limit
            if employees_shown < total_employees:
                remaining = total_employees - employees_shown
                pagination_block = {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"📄 *Showing {employees_shown} of {total_employees} employees ({remaining} more not shown)*\n💡 Use more specific filters to see all results."
                    }
                }
                blocks.append(pagination_block)
        
        # Add comprehensive summary (always include this)
        total_leaves = leaves.count()
        total_days = sum((leave.end_date - leave.start_date).days + 1 for leave in leaves)
        
        # Additional statistics
        pending_count = leaves.filter(status__in=['PENDING', 'PENDING_DOCS', 'DOCS_SUBMITTED']).count()
        approved_count = leaves.filter(status__in=['APPROVED', 'APPROVED_UNPAID', 'APPROVED_COMPENSATORY']).count()
        rejected_count = leaves.filter(status='REJECTED').count()
        
        summary_text = f"📊 *Complete Summary:*\n"
        summary_text += f"• *Total Records:* {total_leaves} leaves\n"
        summary_text += f"• *Total Days:* {total_days} days\n"
        summary_text += f"• *Pending:* {pending_count} | *Approved:* {approved_count} | *Rejected:* {rejected_count}\n"
        
        if total_leaves > 50:
            summary_text += f"\n💡 *Tip: Large dataset ({total_leaves} records). Use more specific filters to see all results.*"
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": summary_text
            }
        })
        
        return {
            'success': True,
            'blocks': blocks,
            'count': leaves.count() if leaves.exists() else 0,
            'summary': {
                'total_leaves': leaves.count() if leaves.exists() else 0,
                'total_days': sum((leave.end_date - leave.start_date).days + 1 for leave in leaves) if leaves.exists() else 0,
                'filters_applied': {
                    'department': department_filter,
                    'leave_type': leave_type,
                    'status': status,
                    'employee': employee_filter,
                    'date_range': f"{start_date} to {end_date}"
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Error processing team calendar query: {e}")
        return {
            'success': False,
            'message': f'Error processing calendar query: {str(e)}',
            'blocks': [{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"❌ *Error:* {str(e)}\n\nPlease try again or contact support."
                }
            }]
        }

def create_employee_leave_blocks_limited(emp_data, display_options, max_leaves=3):
    """Create limited blocks for a single employee's leaves to respect Slack limits"""
    employee = emp_data['employee']
    leaves = emp_data['leaves']
    department = emp_data['department']
    
    blocks = []
    
    # Employee header with summary
    total_leaves = len(leaves)
    total_days = sum((leave.end_date - leave.start_date).days + 1 for leave in leaves)
    
    # Count by status for this employee
    pending_count = sum(1 for leave in leaves if leave.status in ['PENDING', 'PENDING_DOCS', 'DOCS_SUBMITTED'])
    approved_count = sum(1 for leave in leaves if leave.status in ['APPROVED', 'APPROVED_UNPAID', 'APPROVED_COMPENSATORY'])
    rejected_count = sum(1 for leave in leaves if leave.status == 'REJECTED')
    
    # Status summary for header
    status_summary = []
    if pending_count > 0:
        status_summary.append(f"⏳ {pending_count} pending")
    if approved_count > 0:
        status_summary.append(f"✅ {approved_count} approved")
    if rejected_count > 0:
        status_summary.append(f"❌ {rejected_count} rejected")
    
    status_text = " | ".join(status_summary) if status_summary else "No leaves"
    
    header_text = f"👤 *<@{employee.username}>*"
    if 'SHOW_DETAILS' in display_options:
        header_text += f" ({department})"
    header_text += f"\n📊 *Summary:* {total_leaves} leaves, {total_days} days total\n📈 *Status:* {status_text}"
    
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": header_text
        }
    })
    
    # Sort leaves for this employee
    sorted_leaves = sorted(leaves, key=lambda x: x.start_date)
    
    # LIMIT: Show only first few leaves to avoid hitting block limit
    leaves_to_show = sorted_leaves[:max_leaves]
    
    # Create individual leave entries
    for leave in leaves_to_show:
        leave_block = create_individual_leave_block(leave, display_options, show_employee=False)
        blocks.append(leave_block)
    
    # Add info if there are more leaves
    if len(sorted_leaves) > max_leaves:
        remaining = len(sorted_leaves) - max_leaves
        more_block = {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"  📋 *... and {remaining} more leave(s) not shown*"
            }
        }
        blocks.append(more_block)
    
    # Add divider after each employee
    blocks.append({"type": "divider"})
    
    return blocks

def create_individual_leave_block(leave, display_options, show_employee=True):
    """Create a formatted block for a single leave entry"""
    days = (leave.end_date - leave.start_date).days + 1
    
    # Status emoji mapping
    status_emoji_map = {
        'PENDING': '⏳',
        'APPROVED': '✅',
        'REJECTED': '❌',
        'CANCELLED': '🚫',
        'PENDING_DOCS': '📄',
        'DOCS_SUBMITTED': '📋',
        'APPROVED_UNPAID': '💰',
        'APPROVED_COMPENSATORY': '🔄'
    }
    emoji = status_emoji_map.get(leave.status, '❓')
    
    # Build text with conditional employee name
    text = f"  {emoji} *{leave.get_leave_type_display()}* • {days} days"
    if show_employee:
        text = f"👤 *<@{leave.employee.username}>*\n" + text
    
    text += f"\n  📅 {leave.start_date.strftime('%b %d')} - {leave.end_date.strftime('%b %d')}"
    text += f"\n  📊 Status: {leave.status.replace('_', ' ').title()}"
    
    if 'SHOW_REASONS' in display_options and leave.reason:
        reason_preview = leave.reason[:80] + '...' if len(leave.reason) > 80 else leave.reason
        text += f"\n  💬 Reason: {reason_preview}"
    
    if 'SHOW_CONFLICTS' in display_options:
        from .leave_utils import get_conflicts_details
        # Check for conflicts with this leave
        conflicts = get_conflicts_details(leave.start_date, leave.end_date, leave.employee)
        if conflicts['approved_count'] > 0 or conflicts['pending_count'] > 0:
            text += f"\n  ⚠️ Conflicts with {conflicts['approved_count'] + conflicts['pending_count']} other leave(s)"
    
    return {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": text
        }
    }

def handle_team_calendar_filter_submission(payload):
    """Process team calendar filter form submission and generate customized calendar"""
    try:
        # IMMEDIATE RESPONSE - Return success first to avoid timeout
        def build_and_send_filtered_calendar():
            """Background function to build and send filtered calendar"""
            try:
                from .models import LeaveRequest, UserRole
                from .leave_utils import create_leave_block
                from .slack_utils import SLACK_MANAGER_CHANNEL
                
                # Extract form values
                values = payload['view']['state']['values']
                
                # Check if custom dates are provided
                custom_start = None
                custom_end = None
                
                if ('custom_start_date' in values and values['custom_start_date']['start_date_select'].get('selected_date') and
                    'custom_end_date' in values and values['custom_end_date']['end_date_select'].get('selected_date')):
                    # Use custom date range
                    custom_start = datetime.strptime(
                        values['custom_start_date']['start_date_select']['selected_date'],
                        '%Y-%m-%d'
                    ).date()
                    custom_end = datetime.strptime(
                        values['custom_end_date']['end_date_select']['selected_date'],
                        '%Y-%m-%d'
                    ).date()
                    
                    # Ensure start date is not after end date
                    if custom_start > custom_end:
                        custom_start, custom_end = custom_end, custom_start
                    
                    start_of_month = custom_start
                    end_of_month = custom_end
                    date_source = "custom"
                    
                elif 'custom_start_date' in values and values['custom_start_date']['start_date_select'].get('selected_date'):
                    # Only start date provided - use start date to end of that month
                    custom_start = datetime.strptime(
                        values['custom_start_date']['start_date_select']['selected_date'],
                        '%Y-%m-%d'
                    ).date()
                    start_of_month = custom_start
                    end_of_month = (start_of_month.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
                    date_source = "start_only"
                    
                elif 'custom_end_date' in values and values['custom_end_date']['end_date_select'].get('selected_date'):
                    # Only end date provided - use start of that month to end date
                    custom_end = datetime.strptime(
                        values['custom_end_date']['end_date_select']['selected_date'],
                        '%Y-%m-%d'
                    ).date()
                    start_of_month = custom_end.replace(day=1)
                    end_of_month = custom_end
                    date_source = "end_only"
                    
                else:
                    # Use selected month from dropdown
                    selected_month_value = values['calendar_month']['month_select']['selected_option']['value']
                    year, month = selected_month_value.split('-')
                    start_of_month = datetime(int(year), int(month), 1).date()
                    end_of_month = (start_of_month + timedelta(days=32)).replace(day=1) - timedelta(days=1)
                    date_source = "month"
                
                # Get department filter
                dept_filter = values['department_filter']['department_select']['selected_option']['value']
                
                # Get status filters
                status_options = values['status_filter']['status_select']['selected_options']
                status_filters = []
                for option in status_options:
                    status_value = option['value']
                    if status_value == 'PENDING':
                        status_filters.extend(['PENDING', 'PENDING_DOCS', 'DOCS_SUBMITTED'])
                    elif status_value == 'APPROVED':
                        status_filters.extend(['APPROVED', 'APPROVED_UNPAID', 'APPROVED_COMPENSATORY'])
                    elif status_value == 'DOCS':
                        status_filters.extend(['PENDING_DOCS', 'DOCS_SUBMITTED', 'DOCS_PENDING_LATER'])
                    else:
                        status_filters.append(status_value)
                
                # Get leave type filters (optional)
                leave_type_filters = []
                if 'leave_type_filter' in values and values['leave_type_filter']['leave_type_select'].get('selected_options'):
                    leave_type_options = values['leave_type_filter']['leave_type_select']['selected_options']
                    leave_type_filters = [option['value'] for option in leave_type_options]
                
                # Get display options (optional)
                display_options = []
                if 'display_options' in values and values['display_options']['display_select'].get('selected_options'):
                    display_opts = values['display_options']['display_select']['selected_options']
                    display_options = [option['value'] for option in display_opts]
                
                # Get sort option (optional)
                sort_option = "DATE_ASC"  # Default
                if 'sort_option' in values and values['sort_option']['sort_select'].get('selected_option'):
                    sort_option = values['sort_option']['sort_select']['selected_option']['value']
                
                # Build query
                query = LeaveRequest.objects.filter(
                    start_date__lte=end_of_month,
                    end_date__gte=start_of_month,
                    status__in=status_filters
                )
                
                # Apply department filter
                if dept_filter != 'ALL':
                    query = query.filter(employee__userrole__department_id=dept_filter)
                
                # Apply leave type filter
                if leave_type_filters:
                    query = query.filter(leave_type__in=leave_type_filters)
                
                # Apply sorting
                if sort_option == "DATE_ASC":
                    leaves = query.order_by('start_date', 'employee__username')
                elif sort_option == "DATE_DESC":
                    leaves = query.order_by('-start_date', 'employee__username')
                elif sort_option == "EMPLOYEE_ASC":
                    leaves = query.order_by('employee__username', 'start_date')
                elif sort_option == "EMPLOYEE_DESC":
                    leaves = query.order_by('-employee__username', 'start_date')
                elif sort_option == "TYPE":
                    leaves = query.order_by('leave_type', 'start_date', 'employee__username')
                elif sort_option == "STATUS_PENDING":
                    # Custom sorting to put PENDING statuses first
                    leaves = query.extra(
                        select={
                            'status_priority': "CASE WHEN status LIKE 'PENDING%' THEN 1 WHEN status LIKE 'DOCS%' THEN 2 ELSE 3 END"
                        }
                    ).order_by('status_priority', 'start_date', 'employee__username')
                elif sort_option == "DURATION_DESC":
                    # Sort by duration (longest first)
                    leaves = query.extra(
                        select={
                            'duration': '(end_date - start_date + 1)'
                        }
                    ).order_by('-duration', 'start_date', 'employee__username')
                else:
                    leaves = query.order_by('start_date', 'employee__username')
                
                # Build calendar blocks with dynamic header
                if date_source == "custom":
                    if start_of_month == end_of_month:
                        header_text = f"📅 Filtered Team Calendar - {start_of_month.strftime('%B %d, %Y')}"
                    else:
                        header_text = f"📅 Filtered Team Calendar - {start_of_month.strftime('%b %d')} to {end_of_month.strftime('%b %d, %Y')}"
                elif date_source in ["start_only", "end_only"]:
                    header_text = f"📅 Filtered Team Calendar - {start_of_month.strftime('%b %d')} to {end_of_month.strftime('%b %d, %Y')}"
                else:
                    header_text = f"📅 Filtered Team Calendar - {start_of_month.strftime('%B %Y')}"
                
                blocks = [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": header_text,
                            "emoji": True
                        }
                    }
                ]
                
                # Add filter summary
                dept_name = "All Departments" if dept_filter == 'ALL' else Department.objects.get(id=dept_filter).name if dept_filter != 'ALL' else "All"
                status_names = [opt['text']['text'] for opt in status_options]
                leave_type_names = [opt['text']['text'] for opt in values.get('leave_type_filter', {}).get('leave_type_select', {}).get('selected_options', [])]
                
                filter_text = f"🔍 *Applied Filters:*\n"
                filter_text += f"• *Department:* {dept_name}\n"
                filter_text += f"• *Status:* {', '.join(status_names)}\n"
                if leave_type_names:
                    filter_text += f"• *Leave Types:* {', '.join(leave_type_names)}\n"
                
                # Add date range info to filter summary
                if date_source == "custom":
                    if start_of_month == end_of_month:
                        filter_text += f"• *Date:* {start_of_month.strftime('%B %d, %Y')}\n"
                    else:
                        filter_text += f"• *Date Range:* {start_of_month.strftime('%b %d')} to {end_of_month.strftime('%b %d, %Y')}\n"
                elif date_source in ["start_only", "end_only"]:
                    filter_text += f"• *Date Range:* {start_of_month.strftime('%b %d')} to {end_of_month.strftime('%b %d, %Y')}\n"
                else:
                    filter_text += f"• *Period:* {start_of_month.strftime('%B %Y')}\n"
                
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": filter_text
                    }
                })
                blocks.append({"type": "divider"})
                
                if not leaves.exists():
                    blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"🔍 *No leaves found matching your filters*"
                        }
                    })
                else:
                    # PAGINATION FOR FILTER RESULTS TOO
                    MAX_LEAVE_BLOCKS = 40  # Leave room for headers and summary
                    
                    if 'GROUP_DEPT' in display_options:
                        # Group leaves by department with limits
                        dept_groups = {}
                        for leave in leaves:
                            user_role = UserRole.objects.filter(user=leave.employee).first()
                            dept_name = user_role.department.name if user_role and user_role.department else 'No Department'
                            if dept_name not in dept_groups:
                                dept_groups[dept_name] = []
                            dept_groups[dept_name].append(leave)
                        
                        blocks_used = 0
                        for dept_name, dept_leaves in dept_groups.items():
                            if blocks_used >= MAX_LEAVE_BLOCKS:
                                break
                                
                            blocks.append({
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": f"🏢 *{dept_name}* ({len(dept_leaves)} leaves)"
                                }
                            })
                            blocks_used += 1
                            
                            # Show limited leaves in department
                            for i, leave in enumerate(dept_leaves):
                                if blocks_used >= MAX_LEAVE_BLOCKS:
                                    remaining = len(dept_leaves) - i
                                    blocks.append({
                                        "type": "section",
                                        "text": {
                                            "type": "mrkdwn",
                                            "text": f"📋 *... and {remaining} more leave(s) in {dept_name} not shown*"
                                        }
                                    })
                                    blocks_used += 1
                                    break
                                    
                                blocks.append(create_leave_block(leave, display_options))
                                blocks_used += 1
                            
                            if blocks_used < MAX_LEAVE_BLOCKS:
                                blocks.append({"type": "divider"})
                                blocks_used += 1
                    else:
                        # Regular list view with limits
                        leaves_shown = 0
                        for leave in leaves:
                            if leaves_shown >= MAX_LEAVE_BLOCKS:
                                remaining = leaves.count() - leaves_shown
                                blocks.append({
                                    "type": "section",
                                    "text": {
                                        "type": "mrkdwn",
                                        "text": f"📋 *... and {remaining} more leave(s) not shown. Use more specific filters to see all results.*"
                                    }
                                })
                                break
                                
                            blocks.append(create_leave_block(leave, display_options))
                            leaves_shown += 1
                
                # Add comprehensive summary
                total_leaves = leaves.count()
                total_days = sum((leave.end_date - leave.start_date).days + 1 for leave in leaves)
                
                # Additional statistics
                pending_count = leaves.filter(status__in=['PENDING', 'PENDING_DOCS', 'DOCS_SUBMITTED']).count()
                approved_count = leaves.filter(status__in=['APPROVED', 'APPROVED_UNPAID', 'APPROVED_COMPENSATORY']).count()
                rejected_count = leaves.filter(status='REJECTED').count()
                
                summary_text = f"📊 *Complete Summary:*\n"
                summary_text += f"• *Total Records:* {total_leaves} leaves\n"
                summary_text += f"• *Total Days:* {total_days} days\n"
                summary_text += f"• *Pending:* {pending_count} | *Approved:* {approved_count} | *Rejected:* {rejected_count}\n"
                
                if total_leaves > 50:
                    summary_text += f"\n💡 *Tip: Large dataset ({total_leaves} records). Use more specific filters to see all results.*"
                
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": summary_text
                    }
                })
                
                # Send to the leave_app channel instead of leave_app channel
                user_id = payload['user']['id']
                
                try:
                    slack_client.chat_postMessage(
                        channel=user_id,
                        blocks=blocks,
                        text=header_text
                    )
                except SlackApiError as e:
                    logger.error(f"Error sending filtered calendar: {e}")
                    # Send error message
                    slack_client.chat_postMessage(
                        channel=user_id,
                        text=f"⚠️ Error generating filtered calendar: {str(e)}"
                    )
                
            except Exception as e:
                logger.error(f"Background error building filtered calendar: {e}")
                try:
                    user_id = payload['user']['id']
                    slack_client.chat_postMessage(
                        channel=user_id,
                        text=f"⚠️ Error loading filtered calendar: {str(e)}"
                    )
                except Exception as slack_error:
                    logger.error(f"Failed to send error message: {slack_error}")
        
        # Start background thread for processing
        thread = threading.Thread(target=build_and_send_filtered_calendar)
        thread.daemon = True
        thread.start()
        
        # Return immediate response to clear modal (prevents timeout)
        return JsonResponse({"response_action": "clear"})
        
    except Exception as e:
        logger.error(f"Error in team calendar filter submission: {e}")
        return JsonResponse({
            "response_action": "errors",
            "errors": {
                "calendar_month": f"Error processing filter: {str(e)}"
            }
        })