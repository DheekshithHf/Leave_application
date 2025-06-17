from django.http import JsonResponse
from .slack_utils import slack_client, get_or_create_user
from .models import LeaveRequest, UserRole, Department
from slack_sdk.errors import SlackApiError
import threading
import logging

logger = logging.getLogger(__name__)

def handle_apply_leave(request):
    """
    Handle apply leave command - open the leave application modal
    
    WORKFLOW:
    1. Gets user's current leave balance (with maternity/paternity count tracking)
    2. Creates modal form with balance display at top
    3. Opens modal in background thread to avoid timeout
    4. Form submission is handled by modal_handlers.py
    """
    try:
        user_id = request.POST.get('user_id')
        
        # IMMEDIATE RESPONSE - Return success first to avoid timeout
        def get_balance_and_open_modal():
            """Background function to get balance and open modal"""
            try:
                from .leave_utils import get_leave_balance
                balance = get_leave_balance(user_id)
                
                # Base blocks for the form - SHOWS USER'S CURRENT LEAVE BALANCE
                base_blocks = [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"*📊 Your Leave Balance:*\n\n"
                                f"*Monthly Leaves:*\n"
                                f"• 🏖️ Casual Leave: {balance['casual']['remaining']} days remaining (Used: {balance['casual']['used']})\n"
                                f"• 🏥 Sick Leave: {balance['sick']['remaining']} days remaining (Used: {balance['sick']['used']})\n\n"
                                f"*Special Leaves:*\n"
                                f"• 🤱 Maternity: {balance['maternity']['remaining']} days available ({balance['maternity']['status']})\n"
                                f"• 👨‍👶 Paternity: {balance['paternity']['remaining']} days available ({balance['paternity']['status']})"
                            )
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "leave_type",
                        "element": {
                            "type": "static_select",
                            "action_id": "leave_type_select",
                            "placeholder": {"type": "plain_text", "text": "Select leave type"},
                            "options": [
                                {"text": {"type": "plain_text", "text": "Casual Leave"}, "value": "CASUAL"},
                                {"text": {"type": "plain_text", "text": "Sick Leave"}, "value": "SICK"},
                                {"text": {"type": "plain_text", "text": "Maternity Leave"}, "value": "MATERNITY"},
                                {"text": {"type": "plain_text", "text": "Paternity Leave"}, "value": "PATERNITY"}
                            ]
                        },
                        "label": {"type": "plain_text", "text": "Leave Type"}
                    },
                    {
                        "type": "input",
                        "block_id": "start_date",
                        "element": {
                            "type": "datepicker",
                            "action_id": "start_date_select"
                        },
                        "label": {"type": "plain_text", "text": "Start Date"}
                    },
                    {
                        "type": "input",
                        "block_id": "end_date",
                        "element": {
                            "type": "datepicker",
                            "action_id": "end_date_select"
                        },
                        "label": {"type": "plain_text", "text": "End Date"}
                    },
                    {
                        "type": "input",
                        "block_id": "reason",
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "reason_input",
                            "multiline": True
                        },
                        "label": {"type": "plain_text", "text": "Reason"}
                    },
                    {
                        "type": "input",
                        "block_id": "backup_person",
                        "optional": True,
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "backup_person_input"
                        },
                        "label": {"type": "plain_text", "text": "Backup Person (Optional)"}
                    }
                ]

                view = {
                    "type": "modal",
                    "callback_id": "leave_request_modal",
                    "title": {"type": "plain_text", "text": "Apply for Leave"},
                    "submit": {"type": "plain_text", "text": "Submit"},
                    "blocks": base_blocks
                }
                
                slack_client.views_open(
                    trigger_id=request.POST.get('trigger_id'),
                    view=view
                )
            except Exception as e:
                logger.error(f"Background error opening form: {e}")
        
        # Start background thread
        thread = threading.Thread(target=get_balance_and_open_modal)
        thread.daemon = True
        thread.start()
        
        # Return immediate response
        return JsonResponse({'text': '⏳ Loading leave application form...'})
        
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
                
                # Update user's department
                user_role, role_created = UserRole.objects.get_or_create(user=user)
                old_department = user_role.department.name if user_role.department else "None"
                user_role.department = department
                user_role.save()
                
                success_text = (
                    f"✅ *Department Assignment Successful*\n\n"
                    f"*User:* <@{user.username}>\n"
                    f"*Previous Department:* {old_department}\n"
                    f"*New Department:* {matched_department}\n"
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
        return JsonResponse({'text': '⏳ Processing department assignment...'})
            
    except Exception as e:
        logger.error(f"Error handling department command: {e}")
        return JsonResponse({'text': f'Error assigning department: {str(e)}'}, status=200)