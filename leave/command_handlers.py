from django.http import JsonResponse
from .slack_utils import slack_client, get_or_create_user
from .models import LeaveRequest, UserRole, Department
from slack_sdk.errors import SlackApiError
import threading
import logging

logger = logging.getLogger(__name__)

def handle_apply_leave(request):
    """
    Handle apply leave command - supports both AI text and email-style form
    
    WORKFLOW:
    - If text provided: Process with AI and submit directly  
    - If no text: Open email-style form with To/Content fields
    """
    try:
        text = request.POST.get('text', '').strip()
        user_id = request.POST.get('user_id')
        trigger_id = request.POST.get('trigger_id')
        
        # AI PROCESSING PATH - if text is provided
        if text:
            logger.info(f"AI_APPLY_LEAVE: Processing AI request for user {user_id}: '{text}'")
            
            def process_ai_leave_request():
                """Background function to process AI leave request"""
                try:
                    from .leave_ai import extract_leave_details
                    import json
                    from datetime import datetime
                    from .leave_utils import get_leave_balance
                    
                    balance = get_leave_balance(user_id)
                    maternity=f"{balance['maternity']['remaining']} days available ({balance['maternity']['status']})"
                    paternity=f"{balance['paternity']['remaining']} days available ({balance['paternity']['status']})"
                    today_date = datetime.now().date()
                    ai_response = extract_leave_details(text, today_date, maternity, paternity)
                    
                    # Log AI response for debugging
                    logger.info(f"AI_APPLY_LEAVE_RESPONSE: {json.dumps(ai_response, indent=2, default=str)}")
                    
                    if ai_response.get('confusion_detected'):
                        confusion_reason = ai_response.get('confusion_reason', 'Request is unclear')
                        slack_client.chat_postMessage(
                            channel=user_id,
                            text=f"🤖 I can't understand your request.\n\n❓ *Why:* {confusion_reason}\n\n📝 *Try:* `I need sick leave tomorrow` or `/apply-leave` to open form."
                        )
                        return

                    if 'error' in ai_response:
                        slack_client.chat_postMessage(
                            channel=user_id,
                            text=f"❌ AI Error: {ai_response['error']}"
                        )
                        return

                    missing_info = ai_response.get('missing_info', [])
                    if missing_info:
                        missing_text = ', '.join(missing_info).replace('_', ' ').title()
                        slack_client.chat_postMessage(
                            channel=user_id,
                            text=f"🤖 I need more details!\n\n❓ *Missing:* {missing_text}\n\n📝 *Example:* `I need casual leave tomorrow for doctor appointment`"
                        )
                        return

                    # For AI requests, prompt user to use form for manager selection
                    slack_client.chat_postMessage(
                        channel=user_id,
                        text=f"🤖 Great! I understood your leave request:\n\n*Leave Type:* {ai_response.get('leave_type', 'N/A')}\n*Dates:* {ai_response.get('start_date', 'N/A')} to {ai_response.get('end_date', 'N/A')}\n*Reason:* {ai_response.get('reason', 'N/A')}\n\nNow please use `/apply-leave` (without text) to select managers and submit the request."
                    )
                        
                except Exception as e:
                    logger.error(f"AI_APPLY_LEAVE_EXCEPTION: {str(e)}")
                    slack_client.chat_postMessage(
                        channel=user_id,
                        text=f"❌ Error processing AI request: {str(e)}. Please use `/apply-leave` without text to open the form."
                    )
            
            # Start background processing
            thread = threading.Thread(target=process_ai_leave_request)
            thread.daemon = True
            thread.start()
            
            return JsonResponse({'text': '🤖 Processing your leave request with AI...'})
        
        # EMAIL-STYLE FORM PATH - NEW FORMAT
        else:
            def get_balance_and_open_email_modal():
                """Background function to get balance and open email-style modal"""
                try:
                    from .leave_utils import get_leave_balance
                    balance = get_leave_balance(user_id)
                    
                    # Email-style form with just To and Content fields
                    # email_blocks = [
                    #     {
                    #         "type": "section",
                    #         "text": {
                    #             "type": "mrkdwn",
                    #             "text": (
                    #                 f"📧 *Leave Request Email*\n\n"
                    #                 f"*📊 Your Current Balance:*\n\n"
                    #                 f"• 🏖️   Casual: {balance['casual']['remaining']} days left\n"
                    #                 f"• 🏥   Sick: {balance['sick']['remaining']} days left\n"
                    #                 f"• 🤱   Maternity: {balance['maternity']['remaining']} days ({balance['maternity']['status']})\n"
                    #                 f"• 👨‍👶 Paternity: {balance['paternity']['remaining']} days ({balance['paternity']['status']})\n\n"
                    #             )
                    #         }
                    #     },
                    #     {
                    #         "type": "divider"
                    #     },
                    #     {
                    #         "type": "input",
                    #         "block_id": "email_to",
                    #         "element": {
                    #             "type": "multi_users_select",
                    #             "action_id": "managers_select",
                    #             "placeholder": {"type": "plain_text", "text": "Select managers to notify"},
                    #             "max_selected_items": 5
                    #         },
                    #         "label": {"type": "plain_text", "text": "📋 To: (Select Managers)"}
                    #     },
                    #     {
                    #         "type": "input",
                    #         "block_id": "email_content",
                    #         "element": {
                    #             "type": "plain_text_input",
                    #             "action_id": "content_input",
                    #             "multiline": True,
                    #             "placeholder": {
                    #                 "type": "plain_text", 
                    #                 "text": "Example: I need 2 days casual leave on Friday and Monday for a family wedding. My colleague John will handle my tasks."
                    #             }
                    #         },
                    #         "label": {"type": "plain_text", "text": "📝 Content: (Describe your leave request)"}
                    #     },
                        
                    # ]

                    # view = {
                    #     "type": "modal",
                    #     "callback_id": "email_leave_request_modal",
                    #     "title": {"type": "plain_text", "text": "📧 Leave Request Email"},
                    #     "submit": {"type": "plain_text", "text": "Send Request"},
                    #     "blocks": email_blocks
                    # }
                    # Replace the email_blocks section in handle_apply_leave function

                    email_blocks = [
    # Clean Header - Apple style minimal
    {
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": "Leave Request"
        }
    },
    {
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": "Submit your leave request with ease"
            }
        ]
    },
    
    # Elegant Balance Display - Cards style
    {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": "*Your Leave Balance*"
        }
    },
    {
        "type": "section",
        "fields": [
            {
                "type": "mrkdwn",
                "text": f"*Casual*\n{balance['casual']['remaining']} days left"
            },
            {
                "type": "mrkdwn",
                "text": f"*Sick*\n{balance['sick']['remaining']} days left"
            }
        ]
    },
    {
        "type": "section",
        "fields": [
            {
                "type": "mrkdwn",
                "text": f"*Maternity*\n{balance['maternity']['remaining']} days\n_{balance['maternity']['status']}_"
            },
            {
                "type": "mrkdwn",
                "text": f"*Paternity*\n{balance['paternity']['remaining']} days\n_{balance['paternity']['status']}_"
            }
        ]
    },
    
    # Clean Divider
    {
        "type": "divider"
    },
    
    # Minimal Input Fields - Apple style
    {
        "type": "input",
        "block_id": "email_to",
        "element": {
            "type": "multi_users_select",
            "action_id": "managers_select",
            "placeholder": {"type": "plain_text", "text": "Select managers"},
            "max_selected_items": 5
        },
        "label": {"type": "plain_text", "text": "To"}
    },
    {
        "type": "input",
        "block_id": "email_content",
        "element": {
            "type": "plain_text_input",
            "action_id": "content_input",
            "multiline": True,
            "placeholder": {
                "type": "plain_text", 
                "text": "I need 2 days casual leave on March 15-16 for a family event. My colleague will cover my responsibilities."
            }
        },
        "label": {"type": "plain_text", "text": "Message"}
    }
]

                    view = {
                        "type": "modal",
                        "callback_id": "email_leave_request_modal",
                        "title": {"type": "plain_text", "text": "Leave Request"},
                        "submit": {"type": "plain_text", "text": "Send"},
                        "close": {"type": "plain_text", "text": "Cancel"},
                        "blocks": email_blocks
                    }
                    slack_client.views_open(
                        trigger_id=trigger_id,
                        view=view
                    )
                except Exception as e:
                    logger.error(f"Background error opening email form: {e}")
                    try:
                        slack_client.chat_postMessage(
                            channel=user_id,
                            text=f"❌ Error opening email form: {str(e)}"
                        )
                    except:
                        pass
        
            # Start background thread
            thread = threading.Thread(target=get_balance_and_open_email_modal)
            thread.daemon = True
            thread.start()
            
            # Return immediate response
            return JsonResponse({'text': '⏳ Loading leave request email form...'})
        
    except Exception as e:
        logger.error(f"Error opening form: {e}")
        return JsonResponse({'text': 'Error opening form'}, status=200)

def handle_my_leaves(request):
    """Handle my leaves command - show user's leave history"""
    try:
        slack_user_id = request.POST.get('user_id')
        
        # IMMEDIATE RESPONSE - Return success first to avoid timeout
        def get_leaves_and_respond():
            """Background function to get leaves and send response"""
            try:
                user = get_or_create_user(slack_user_id)
                leaves = LeaveRequest.objects.filter(employee=user).order_by('-start_date')
                
                if not leaves:
                    # Send follow-up message
                    try:
                        slack_client.chat_postMessage(
                            channel=slack_user_id,
                            text='📋 No leave history found.'
                        )
                    except SlackApiError:
                        # Fallback to leave_app channel
                        slack_client.chat_postMessage(
                            channel='leave_app',
                            text=f'📋 <@{slack_user_id}> - No leave history found.'
                        )
                    return
                    
                blocks = [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*Your Leave History*"
                        }
                    }
                ]
                
                for leave in leaves:
                    days = (leave.end_date - leave.start_date).days + 1
                    status_emoji = "✅" if leave.status == 'APPROVED' else "❌" if leave.status == 'REJECTED' else "⏳"
                    
                    blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"*{leave.get_leave_type_display()}* ({days} days)\n"
                                f"*Dates:* {leave.start_date} to {leave.end_date}\n"
                                f"*Status:* {status_emoji} {leave.status}\n"
                                f"*Comment:* {leave.supervisor_comment or 'No comment'}"
                            )
                        }
                    })
                
                # Send follow-up message with results
                try:
                    slack_client.chat_postMessage(
                        channel=slack_user_id,
                        blocks=blocks,
                        text="Your leave history"
                    )
                except SlackApiError:
                    # Fallback to leave_app channel
                    slack_client.chat_postMessage(
                        channel='leave_app',
                        blocks=[{
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"📋 *Leave History for <@{slack_user_id}>:*"
                            }
                        }] + blocks[1:],  # Skip the first header block
                        text=f"Leave history for <@{slack_user_id}>"
                    )
                    
            except Exception as e:
                logger.error(f"Background error fetching leave history: {e}")
                try:
                    slack_client.chat_postMessage(
                        channel=slack_user_id,
                        text=f'❌ Error fetching leave history: {str(e)}'
                    )
                except SlackApiError:
                    slack_client.chat_postMessage(
                        channel='leave_app',
                        text=f'❌ <@{slack_user_id}> - Error fetching leave history: {str(e)}'
                    )
        
        # Start background thread
        thread = threading.Thread(target=get_leaves_and_respond)
        thread.daemon = True
        thread.start()
        
        # Return immediate response
        return JsonResponse({'text': '⏳ Fetching your leave history...'})
        
    except Exception as e:
        logger.error(f"Error fetching leave history: {e}")
        return JsonResponse({'text': 'Error fetching leave history'}, status=200)

def handle_leave_balance(request):
    """Handle leave balance command - show user's current balance"""
    try:
        slack_user_id = request.POST.get('user_id')
        
        # IMMEDIATE RESPONSE - Return success first to avoid timeout
        def get_balance_and_respond():
            """Background function to get balance and send response"""
            try:
                from .leave_utils import get_leave_balance
                balance = get_leave_balance(slack_user_id)
                
                balance_text = (
                    f"*Leave Balance*\n"
                    f"• Casual Leave: Used {balance['casual']['used']} of 2 days; {balance['casual']['remaining']} days remain\n"
                    f"• Sick Leave: Used {balance['sick']['used']} of 5 days; {balance['sick']['remaining']} days remain"
                )
                
                # Send follow-up message with balance
                try:
                    slack_client.chat_postMessage(
                        channel=slack_user_id,
                        text=balance_text
                    )
                except SlackApiError:
                    # Fallback to leave_app channel
                    slack_client.chat_postMessage(
                        channel='leave_app',
                        text=f"📊 *Balance for <@{slack_user_id}>:*\n{balance_text}"
                    )
                    
            except Exception as e:
                logger.error(f"Background error fetching balance: {e}")
                try:
                    slack_client.chat_postMessage(
                        channel=slack_user_id,
                        text=f'❌ Error fetching balance: {str(e)}'
                    )
                except SlackApiError:
                    slack_client.chat_postMessage(
                        channel='leave_app',
                        text=f'❌ <@{slack_user_id}> - Error fetching balance: {str(e)}'
                    )
        
        # Start background thread
        thread = threading.Thread(target=get_balance_and_respond)
        thread.daemon = True
        thread.start()
        
        # Return immediate response
        return JsonResponse({'text': '⏳ Fetching your leave balance...'})
        
    except Exception as e:
        logger.error(f"Error fetching balance: {e}")
        return JsonResponse({'text': 'Error fetching balance'}, status=200)

def handle_leave_policy(request):
    """Handle leave policy command - show company leave policy"""
    # This is static content, so we can return immediately
    return JsonResponse({
        'text': (
            "*Leave Policy*\n"
            "• Casual Leave: 2 days per month\n"
            "• Sick Leave: 5 days per month\n"
            "• Maternity Leave: 26 weeks (182 days) for 1st & 2nd time, 12 weeks (84 days) for 3rd time onwards\n"
            "• Paternity Leave: 16 days per birth\n\n"
            "_Note: Balances reset monthly for casual and sick leave. Maternity/Paternity leaves are per occurrence._"
        )
    })

def handle_department_command(request):
    """Handle department assignment command with predefined departments"""
    try:
        text = request.POST.get('text', '').strip()
        user_id = request.POST.get('user_id')
        
        # Predefined list of allowed departments
        PREDEFINED_DEPARTMENTS = [
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
        
        if not text:
            # IMMEDIATE RESPONSE - Return success first to avoid timeout
            def open_department_modal():
                """Background function to open department modal"""
                try:
                    department_options = []
                    for dept in PREDEFINED_DEPARTMENTS:
                        department_options.append({
                            "text": {"type": "plain_text", "text": dept}, 
                            "value": dept
                        })
                    
                    view = {
                        "type": "modal",
                        "callback_id": "department_selection",
                        "title": {"type": "plain_text", "text": "Select Department"},
                        "submit": {"type": "plain_text", "text": "Join Department"},
                        "blocks": [
                            {
                                "type": "header",
                                "text": {
                                    "type": "plain_text",
                                    "text": "🏢 Department Selection",
                                    "emoji": True
                                }
                            },
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": "Please select your department from the predefined list below:"
                                }
                            },
                            {
                                "type": "divider"
                            },
                            {
                                "type": "input",
                                "block_id": "department_select",
                                "element": {
                                    "type": "static_select",
                                    "action_id": "department_choice",
                                    "placeholder": {"type": "plain_text", "text": "Choose your department"},
                                    "options": department_options
                                },
                                "label": {"type": "plain_text", "text": "Department"}
                            }
                        ]
                    }
                    
                    slack_client.views_open(
                        trigger_id=request.POST.get('trigger_id'),
                        view=view
                    )
                except Exception as modal_error:
                    logger.error(f"Background error opening modal: {modal_error}")
                    # Send fallback text list
                    dept_list = '\n'.join([f"• {dept}" for dept in PREDEFINED_DEPARTMENTS])
                    try:
                        slack_client.chat_postMessage(
                            channel=user_id,
                            blocks=[
                                {
                                    "type": "header",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "🏢 Available Departments",
                                        "emoji": True
                                    }
                                },
                                {
                                    "type": "section",
                                    "text": {
                                        "type": "mrkdwn",
                                        "text": f"*Predefined Departments:*\n{dept_list}\n\n*Usage:* `/department [Department Name]`\n*Example:* `/department Product-Engineer`"
                                    }
                                }
                            ],
                            text="Available departments"
                        )
                    except SlackApiError:
                        slack_client.chat_postMessage(
                            channel='leave_app',
                            text=f"🏢 <@{user_id}> - Available departments:\n{dept_list}\n\nUsage: `/department [Department Name]`"
                        )
            
            # Start background thread
            thread = threading.Thread(target=open_department_modal)
            thread.daemon = True
            thread.start()
            
            # Return immediate response
            return JsonResponse({'text': '⏳ Opening department selection...'})
        
        # User specified a department name
        # IMMEDIATE RESPONSE for department assignment
        def assign_department():
            """Background function to assign department"""
            try:
                user = get_or_create_user(user_id)
                department_name = text.title()  # Capitalize first letter
                
                # Check if the specified department is in predefined list (case-insensitive)
                matched_department = None
                for predefined_dept in PREDEFINED_DEPARTMENTS:
                    if predefined_dept.lower() == department_name.lower():
                        matched_department = predefined_dept
                        break
                
                if not matched_department:
                    # Department not in predefined list
                    dept_list = '\n'.join([f"• {dept}" for dept in PREDEFINED_DEPARTMENTS])
                    error_text = (
                        f"❌ *Invalid Department: '{department_name}'*\n\n"
                        f"Please choose from the predefined departments:\n\n{dept_list}\n\n"
                        f"*Usage:* `/department [Department Name] or just /department and click enter `\n"
                        f"*Example:* `/department Product-Engineer`"
                    )
                    
                    try:
                        slack_client.chat_postMessage(
                            channel=user_id,
                            text=error_text
                        )
                    except SlackApiError:
                        slack_client.chat_postMessage(
                            channel='leave_app',
                            text=f"🏢 <@{user_id}> - {error_text}"
                        )
                    return
                
                # Get or create the predefined department
                department, created = Department.objects.get_or_create(name=matched_department)
                
                # Update user's department AND assign manager role - ENHANCED
                user_role, role_created = UserRole.objects.get_or_create(user=user)
                old_department = user_role.department.name if user_role.department else "None"
                user_role.department = department
                
                # FIXED: Automatically assign manager role when joining department
                if not user_role.role or user_role.role == 'EMPLOYEE':
                    user_role.role = 'MANAGER'
                    user_role.is_admin = True
                    logger.info(f"DEPARTMENT: Assigned manager role to {user_id}")
                
                user_role.save()
                
                success_text = (
                    f"✅ *Department Assignment Successful*\n\n"
                    f"*User:* <@{user.username}>\n"
                    f"*Previous Department:* {old_department}\n"
                    f"*New Department:* {matched_department}\n"
                    f"*Role:* {user_role.role}\n"
                    f"*Manager Status:* {'Yes' if user_role.is_admin else 'No'}\n"
                    f"*Status:* Successfully assigned to {matched_department}"
                )
                
                try:
                    slack_client.chat_postMessage(
                        channel=user_id,
                        text=success_text
                    )
                except SlackApiError:
                    slack_client.chat_postMessage(
                        channel='leave_app',
                        text=f"🏢 <@{user_id}> - {success_text}"
                    )
                    
            except Exception as e:
                logger.error(f"Background error assigning department: {e}")
                try:
                    slack_client.chat_postMessage(
                        channel=user_id,
                        text=f'❌ Error assigning department: {str(e)}'
                    )
                except SlackApiError:
                    slack_client.chat_postMessage(
                        channel='leave_app',
                        text=f'❌ <@{user_id}> - Error assigning department: {str(e)}'
                    )
        
        # Start background thread
        thread = threading.Thread(target=assign_department)
        thread.daemon = True
        thread.start()
        # Return immediate response
        return JsonResponse({'text': '⏳ Opening team calendar form...'})
        
    except Exception as e:
        logger.error(f"Error handling team calendar: {e}")
        return JsonResponse({'text': 'Error opening team calendar'}, status=200) 

def handle_team_calendar(request):
    """
    Handle team calendar command - supports both AI text and traditional form
    
    WORKFLOW:
    - If text provided: Process with AI and show results directly
    - If no text: Open traditional form modal
    """
    try:
        text = request.POST.get('text', '').strip()
        user_id = request.POST.get('user_id')
        trigger_id = request.POST.get('trigger_id')
        
        # CRITICAL FIX: Check manager status FIRST and return immediate response
        # This prevents timeout for non-managers
        from .slack_utils import is_manager
        if not is_manager(user_id):
            # IMMEDIATE RESPONSE for non-managers to prevent timeout
            return JsonResponse({'text': '❌ Sorry, only managers can access the team calendar.'})
        
        # AI PROCESSING PATH - if text is provided
        if text:
            logger.info(f"AI_TEAM_CALENDAR: Processing AI request for user {user_id}: '{text}'")
            
            def process_ai_calendar_request():
                """Background function to process AI calendar request"""
                try:
                    import sys
                    import os
                    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                    
                    from calendar_ai import extract_calendar_query
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
                    from .calendar_handlers import process_team_calendar_query
                    
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
                    
                    # Send calendar results to user's DM
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
                        
                        # FIXED: Send to user's DM instead of a channel
                        slack_client.chat_postMessage(
                            channel=user_id,
                            blocks=blocks,
                            text=f"🤖 AI Calendar Results: {ai_response.get('query_description', text)}"
                        )
                    else:
                        # FIXED: Send error to user's DM
                        slack_client.chat_postMessage(
                            channel=user_id,
                            text=f"❌ {result.get('message', 'Error processing calendar request')}"
                        )
                        
                except Exception as e:
                    logger.error(f"AI_TEAM_CALENDAR_EXCEPTION: {str(e)}")
                    # FIXED: Send error to user's DM
                    slack_client.chat_postMessage(
                        channel=user_id,
                        text=f"❌ Error processing AI calendar request: {str(e)}. Please use `/team-calendar` without text to open the form."
                    )
            
            # Start background processing
            thread = threading.Thread(target=process_ai_calendar_request)
            thread.daemon = True
            thread.start()
            
            return JsonResponse({'text': '🤖 Processing your calendar request with AI...'})
        
        # TRADITIONAL FORM PATH - existing code continues
        else:
            # IMMEDIATE RESPONSE - Return success first to avoid timeout
            def open_calendar_modal():
                """Background function to open calendar modal"""
                try:
                    from .models import Department
                    
                    # Get departments for filter options
                    departments = Department.objects.all()
                    dept_options = [{"text": {"type": "plain_text", "text": "All Departments"}, "value": "ALL"}]
                    for dept in departments:
                        dept_options.append({
                            "text": {"type": "plain_text", "text": dept.name},
                            "value": dept.name
                        })
                    
                    view = {
                        "type": "modal",
                        "callback_id": "team_calendar_modal",
                        "title": {"type": "plain_text", "text": "Team Calendar"},
                        "submit": {"type": "plain_text", "text": "View Calendar"},
                        "blocks": [
                            {
                                "type": "header",
                                "text": {
                                    "type": "plain_text",
                                    "text": "📅 Team Calendar Query",
                                    "emoji": True
                                }
                            },
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": "Configure your calendar view with the options below:"
                                }
                            },
                            {
                                "type": "input",
                                "block_id": "date_range",
                                "element": {
                                    "type": "static_select",
                                    "action_id": "date_range_select",
                                    "placeholder": {"type": "plain_text", "text": "Select date range"},
                                    "options": [
                                        {"text": {"type": "plain_text", "text": "This Week"}, "value": "this_week"},
                                        {"text": {"type": "plain_text", "text": "Next Week"}, "value": "next_week"},
                                        {"text": {"type": "plain_text", "text": "This Month"}, "value": "this_month"},
                                        {"text": {"type": "plain_text", "text": "Next Month"}, "value": "next_month"},
                                        {"text": {"type": "plain_text", "text": "Custom Range"}, "value": "custom"}
                                    ]
                                },
                                "label": {"type": "plain_text", "text": "Date Range"}
                            },
                            {
                                "type": "input",
                                "block_id": "leave_type_filter",
                                "element": {
                                    "type": "static_select",
                                    "action_id": "leave_type_select",
                                    "placeholder": {"type": "plain_text", "text": "All leave types"},
                                    "options": [
                                        {"text": {"type": "plain_text", "text": "All Types"}, "value": "ALL"},
                                        {"text": {"type": "plain_text", "text": "Casual Leave"}, "value": "CASUAL"},
                                        {"text": {"type": "plain_text", "text": "Sick Leave"}, "value": "SICK"},
                                        {"text": {"type": "plain_text", "text": "Maternity Leave"}, "value": "MATERNITY"},
                                        {"text": {"type": "plain_text", "text": "Paternity Leave"}, "value": "PATERNITY"}
                                    ]
                                },
                                "label": {"type": "plain_text", "text": "Leave Type Filter"},
                                "optional": True
                            },
                            {
                                "type": "input",
                                "block_id": "status_filter",
                                "element": {
                                    "type": "static_select",
                                    "action_id": "status_select",
                                    "placeholder": {"type": "plain_text", "text": "All statuses"},
                                    "options": [
                                        {"text": {"type": "plain_text", "text": "All Statuses"}, "value": "ALL"},
                                        {"text": {"type": "plain_text", "text": "Approved"}, "value": "APPROVED"},
                                        {"text": {"type": "plain_text", "text": "Pending"}, "value": "PENDING"},
                                        {"text": {"type": "plain_text", "text": "Rejected"}, "value": "REJECTED"}
                                    ]
                                },
                                "label": {"type": "plain_text", "text": "Status Filter"},
                                "optional": True
                            },
                            {
                                "type": "input",
                                "block_id": "department_filter",
                                "element": {
                                    "type": "static_select",
                                    "action_id": "department_select",
                                    "placeholder": {"type": "plain_text", "text": "All departments"},
                                    "options": dept_options
                                },
                                "label": {"type": "plain_text", "text": "Department Filter"},
                                "optional": True
                            }
                        ]
                    }
                    
                    slack_client.views_open(
                        trigger_id=trigger_id,
                        view=view
                    )
                except Exception as e:
                    logger.error(f"Background error opening calendar modal: {e}")
            
            # Start background thread
            thread = threading.Thread(target=open_calendar_modal)
            thread.daemon = True
            thread.start()
            
            # Return immediate response
            return JsonResponse({'text': '⏳ Opening team calendar form...'})
        
    except Exception as e:
        logger.error(f"Error handling team calendar: {e}")
        return JsonResponse({'text': 'Error opening team calendar'}, status=200)