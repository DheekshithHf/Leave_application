from django.http import JsonResponse
from .slack_utils import slack_client, get_or_create_user, update_leave_thread, start_leave_request_thread
from .leave_utils import get_leave_balance, get_conflicts_details, get_department_conflicts, get_team_conflicts
from .models import LeaveRequest, UserRole, Department
from django.utils import timezone
from datetime import datetime
from slack_sdk.errors import SlackApiError
import logging
import threading

logger = logging.getLogger(__name__)

def handle_leave_request_modal_submission(payload):
    """
    Handle leave request modal submission with immediate response
    
    WORKFLOW OVERVIEW:
    1. Parse form data (dates, leave type, reason, backup person)
    2. Validate dates and calculate duration
    3. Check balance and conflicts (employee + department + team)
    4. Create leave request in database
    5. Send notification to managers with action buttons
    6. Send confirmation to employee
    
    LEAVE TYPE SPECIFIC LOGIC:
    - CASUAL: [Approve|Unpaid|Compensatory|Reject] buttons
    - SICK: Check if >1 day or insufficient balance → Medical cert option
    - MATERNITY: Always requires medical cert + shows count info
    - PATERNITY: Always requires birth cert + shows count info
    """
    try:
        # IMMEDIATE RESPONSE - Return success first to avoid timeout
        def process_leave_request_background():
            """Background function to process leave request"""
            try:
                values = payload['view']['state']['values']
                leave_type = values['leave_type']['leave_type_select']['selected_option']['value']
                start_date = datetime.strptime(values['start_date']['start_date_select']['selected_date'], '%Y-%m-%d').date()
                end_date = datetime.strptime(values['end_date']['end_date_select']['selected_date'], '%Y-%m-%d').date()
                reason = values['reason']['reason_input']['value']
                # Fix backup_person None value issue
                backup_person_value = values.get('backup_person', {}).get('backup_person_input', {}).get('value')
                backup_person = backup_person_value if backup_person_value is not None else ''
                
                # Validate dates
                if start_date > end_date:
                    start_date, end_date = end_date, start_date
                
                today = datetime.now().date()
                if start_date < today:
                    try:
                        slack_client.chat_postMessage(
                            channel=payload['user']['id'],
                            text='❌ Start date cannot be in the past. Please submit a new request with valid dates.'
                        )
                    except SlackApiError:
                        slack_client.chat_postMessage(
                            channel='leave_app',
                            text=f'❌ <@{payload["user"]["id"]}> - Start date cannot be in the past.'
                        )
                    return
                
                # Calculate duration
                duration = (end_date - start_date).days + 1
                
                # Check balance and conflicts
                from .leave_utils import get_leave_balance, get_conflicts_details
                user = get_or_create_user(payload['user']['id'])
                balance = get_leave_balance(payload['user']['id'])
                conflicts = get_conflicts_details(start_date, end_date, user)
                
                # Check balance but don't reject - send to managers with balance info
                balance_warning = ""
                if leave_type == 'CASUAL' and duration > balance['casual']['remaining']:
                    balance_warning = f"\n⚠️ *INSUFFICIENT BALANCE*: Employee has {balance['casual']['remaining']} casual days remaining but requested {duration} days (Shortfall: {duration - balance['casual']['remaining']} days)"
                elif leave_type == 'SICK' and duration > balance['sick']['remaining']:
                    balance_warning = f"\n⚠️ *INSUFFICIENT BALANCE*: Employee has {balance['sick']['remaining']} sick days remaining but requested {duration} days (Shortfall: {duration - balance['sick']['remaining']} days)"
                
                # Create leave request
                leave_request = LeaveRequest.objects.create(
                    employee=user,
                    leave_type=leave_type,
                    start_date=start_date,
                    end_date=end_date,
                    reason=reason,
                    backup_person=backup_person,
                    status='PENDING'
                )
                
                # Get department for user
                user_role = UserRole.objects.filter(user=user).first()
                department_name = user_role.department.name if user_role and user_role.department else 'No Department'
                
                # Get department conflicts for enhanced conflict analysis
                department_conflicts = None
                if user_role and user_role.department:
                    department_conflicts = get_department_conflicts(start_date, end_date, user_role.department, user)
                
                # Get team conflicts - check all teams the user belongs to
                team_conflicts = get_team_conflicts(start_date, end_date, user, user)
                
                # Get special leave info for maternity/paternity
                special_leave_info = ""
                if leave_type == 'MATERNITY':
                    from .leave_utils import get_maternity_leave_info
                    mat_info = get_maternity_leave_info(user)
                    special_leave_info = f"\n📋 *Maternity Leave Info*: {mat_info['status_text']} ({mat_info['available_days']} days available)"
                elif leave_type == 'PATERNITY':
                    from .leave_utils import get_paternity_leave_info
                    pat_info = get_paternity_leave_info(user)
                    special_leave_info = f"\n📋 *Paternity Leave Info*: {pat_info['status_text']} ({pat_info['available_days']} days available)"
                
                # Create notification for manager channel
                leave_blocks = [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"📄 *New Leave Request*\n\n"
                                f"*Employee:* <@{user.username}>\n"
                                f"*Department:* {department_name}\n"
                                f"*Leave Type:* {leave_request.get_leave_type_display()}\n"
                                f"*Duration:* {start_date} to {end_date} ({duration} days)\n"
                                f"*Reason:* {reason}\n"
                                f"*Backup Person:* {backup_person or 'Not specified'}\n"
                                f"*Status:* PENDING APPROVAL{balance_warning}{special_leave_info}"
                            )
                        }
                    }
                ]
                
                # Add conflicts section if any
                if conflicts['approved_count'] > 0 or conflicts['pending_count'] > 0:
                    conflicts_text = f"\n\n⚠️ *Employee Conflicts (All Departments):*"
                    if conflicts['approved_count'] > 0:
                        conflicts_text += f"\n• {conflicts['approved_count']} approved leave(s): {', '.join(conflicts['approved_names'])}"
                    if conflicts['pending_count'] > 0:
                        conflicts_text += f"\n• {conflicts['pending_count']} pending leave(s): {', '.join(conflicts['pending_names'])}"
                    leave_blocks[0]['text']['text'] += conflicts_text
                
                # Add department conflicts information
                if department_conflicts and (department_conflicts['approved_count'] > 0 or department_conflicts['pending_count'] > 0):
                    dept_conflicts_text = f"\n\n🏢 *Department Conflicts ({department_name}):*"
                    if department_conflicts['approved_count'] > 0:
                        dept_conflicts_text += f"\n• {department_conflicts['approved_count']} approved leave(s) in department: {', '.join(department_conflicts['approved_names'])}"
                    if department_conflicts['pending_count'] > 0:
                        dept_conflicts_text += f"\n• {department_conflicts['pending_count']} pending leave(s) in department: {', '.join(department_conflicts['pending_names'])}"
                    leave_blocks[0]['text']['text'] += dept_conflicts_text
                
                # Add team conflicts information if any team members are on leave
                if team_conflicts:
                    team_conflicts_text = f"\n\n👥 *Team Conflicts:*"
                    for team_name, team_data in team_conflicts.items():
                        if team_data['approved_count'] > 0 or team_data['pending_count'] > 0:
                            team_conflicts_text += f"\n🔸 *Team: {team_name}*"
                            if team_data['approved_count'] > 0:
                                # Show detailed date ranges for team conflicts
                                team_conflicts_text += f"\n  • Approved ({team_data['approved_count']}): {', '.join(team_data['approved_details'])}"
                            if team_data['pending_count'] > 0:
                                # Show detailed date ranges for team conflicts  
                                team_conflicts_text += f"\n  • Pending ({team_data['pending_count']}): {', '.join(team_data['pending_details'])}"
                    
                    if team_conflicts_text != f"\n\n👥 *Team Conflicts:*":
                        leave_blocks[0]['text']['text'] += team_conflicts_text
                
                # Add action buttons for managers
                leave_blocks.append({
                    "type": "input",
                    "block_id": "supervisor_comment",
                    "optional": True,
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "comment_input",
                        "placeholder": {"type": "plain_text", "text": "Add comments (optional)"}
                    },
                    "label": {"type": "plain_text", "text": "Manager Comments"}
                })
                
                # Add action buttons based on leave type
                if leave_type == 'CASUAL':
                    leave_blocks.append({
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "✅ Approve", "emoji": True},
                                "style": "primary",
                                "value": f"{leave_request.id}|APPROVE",
                                "action_id": "approve_regular"
                            },
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "💰 Approve as Unpaid", "emoji": True},
                                "value": f"{leave_request.id}|UNPAID",
                                "action_id": "approve_unpaid"
                            },
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "🔄 Approve with Compensatory Work", "emoji": True},
                                "value": f"{leave_request.id}|COMPENSATORY",
                                "action_id": "approve_compensatory"
                            },
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "❌ Reject", "emoji": True},
                                "style": "danger",
                                "value": f"{leave_request.id}|REJECT",
                                "action_id": "reject_leave"
                            }
                        ]
                    })
                elif leave_type == 'SICK':
                    # Sick leave logic: if more than 1 day OR insufficient balance, show medical certificate recommendation
                    requires_medical_cert = duration > 1 or duration > balance['sick']['remaining']
                    
                    if requires_medical_cert:
                        # Add warning about medical certificate requirement
                        cert_reason = "duration > 1 day" if duration > 1 else f"insufficient balance ({balance['sick']['remaining']} days remaining)"
                        leave_blocks[0]['text']['text'] += f"\n\n🏥 *MEDICAL CERTIFICATE RECOMMENDED*: {cert_reason}"
                    
                    # Always show both options for sick leave - manager can choose
                    leave_blocks.append({
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "✅ Approve", "emoji": True},
                                "style": "primary",
                                "value": f"{leave_request.id}|APPROVE",
                                "action_id": "approve_regular"
                            },
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "📋 Request Medical Certificate", "emoji": True},
                                "value": f"{leave_request.id}|REQUEST_MED_CERT",
                                "action_id": "request_med_cert"
                            },
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "❌ Reject", "emoji": True},
                                "style": "danger",
                                "value": f"{leave_request.id}|REJECT",
                                "action_id": "reject_leave"
                            }
                        ]
                    })
                elif leave_type == 'MATERNITY':
                    leave_blocks.append({
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "✅ Approve", "emoji": True},
                                "style": "primary",
                                "value": f"{leave_request.id}|APPROVE",
                                "action_id": "approve_regular"
                            },
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "📋 Request Medical Certificate", "emoji": True},
                                "value": f"{leave_request.id}|REQUEST_MED_CERT",
                                "action_id": "request_med_cert"
                            },
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "❌ Reject", "emoji": True},
                                "style": "danger",
                                "value": f"{leave_request.id}|REJECT",
                                "action_id": "reject_leave"
                            }
                        ]
                    })
                elif leave_type == 'PATERNITY':
                    leave_blocks.append({
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "✅ Approve", "emoji": True},
                                "style": "primary",
                                "value": f"{leave_request.id}|APPROVE",
                                "action_id": "approve_regular"
                            },
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "📋 Request Birth Certificate", "emoji": True},
                                "value": f"{leave_request.id}|REQUEST_BIRTH_CERT",
                                "action_id": "request_docs"
                            },
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "❌ Reject", "emoji": True},
                                "style": "danger",
                                "value": f"{leave_request.id}|REJECT",
                                "action_id": "reject_leave"
                            }
                        ]
                    })
                
                # Send to manager channel and create thread
                thread_response = start_leave_request_thread(user, leave_request, leave_blocks)
                
                if thread_response and thread_response.get('ts'):
                    leave_request.thread_ts = thread_response['ts']
                    leave_request.save()
                
                # Send confirmation to employee
                confirmation_message = (
                    f"✅ *Leave Request Submitted Successfully*\n\n"
                    f"*Type:* {leave_request.get_leave_type_display()}\n"
                    f"*Duration:* {start_date} to {end_date} ({duration} days)\n"
                    f"*Status:* Pending Approval\n\n"
                    f"Your request has been sent to managers for review."
                )
                
                # Add balance warning to employee if insufficient
                if balance_warning:
                    confirmation_message += f"\n\n⚠️ *Note:* You have insufficient balance for this request. Managers will review and may approve as unpaid leave or with compensatory work."
                
                try:
                    slack_client.chat_postMessage(
                        channel=payload['user']['id'],
                        text=confirmation_message
                    )
                except SlackApiError:
                    slack_client.chat_postMessage(
                        channel='leave_app',
                        text=f"✅ <@{payload['user']['id']}> - {confirmation_message}"
                    )
                
                logger.info(f"Leave request created: {leave_request.id} for user {user.username}")
                
            except Exception as e:
                logger.error(f"Background error processing leave request: {e}")
                try:
                    slack_client.chat_postMessage(
                        channel=payload['user']['id'],
                        text=f'❌ Error processing leave request: {str(e)}'
                    )
                except SlackApiError:
                    slack_client.chat_postMessage(
                        channel='leave_app',
                        text=f'❌ <@{payload["user"]["id"]}> - Error processing leave request: {str(e)}'
                    )
        
        # Start background thread
        thread = threading.Thread(target=process_leave_request_background)
        thread.daemon = True
        thread.start()
        
        # Return immediate response to close modal
        return JsonResponse({"response_action": "clear"})
        
    except Exception as e:
        logger.error(f"Error in leave request modal submission: {e}")
        return JsonResponse({
            "response_action": "errors",
            "errors": {
                "leave_type": f"Error processing request: {str(e)}"
            }
        })