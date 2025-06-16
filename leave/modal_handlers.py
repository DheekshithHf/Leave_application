from django.http import JsonResponse
from .slack_utils import slack_client, get_or_create_user, update_leave_thread, start_leave_request_thread
from .leave_utils import get_leave_balance, get_conflicts_details
from .models import LeaveRequest, UserRole, Department
from django.utils import timezone
from datetime import datetime
from slack_sdk.errors import SlackApiError
import logging
import threading

logger = logging.getLogger(__name__)

def handle_leave_request_modal_submission(payload):
    """Handle leave request modal submission with immediate response"""
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
                backup_person = values.get('backup_person', {}).get('backup_person_input', {}).get('value', '')
                
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
                
                # Check if user has enough balance
                if leave_type == 'CASUAL' and duration > balance['casual']['remaining']:
                    error_message = f'❌ Insufficient casual leave balance. You have {balance["casual"]["remaining"]} days remaining, but requested {duration} days.'
                    try:
                        slack_client.chat_postMessage(
                            channel=payload['user']['id'],
                            text=error_message
                        )
                    except SlackApiError:
                        slack_client.chat_postMessage(
                            channel='leave_app',
                            text=f'❌ <@{payload["user"]["id"]}> - {error_message}'
                        )
                    return
                elif leave_type == 'SICK' and duration > balance['sick']['remaining']:
                    error_message = f'❌ Insufficient sick leave balance. You have {balance["sick"]["remaining"]} days remaining, but requested {duration} days.'
                    try:
                        slack_client.chat_postMessage(
                            channel=payload['user']['id'],
                            text=error_message
                        )
                    except SlackApiError:
                        slack_client.chat_postMessage(
                            channel='leave_app',
                            text=f'❌ <@{payload["user"]["id"]}> - {error_message}'
                        )
                    return
                
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
                                f"*Status:* PENDING APPROVAL"
                            )
                        }
                    }
                ]
                
                # Add conflicts section if any
                if conflicts['has_conflicts']:
                    conflicts_text = f"\n⚠️ *Conflicts Detected:*\n{conflicts['message']}"
                    leave_blocks[0]['text']['text'] += conflicts_text
                
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
                if leave_type in ['CASUAL', 'SICK']:
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
                thread_response = start_leave_request_thread(leave_request, leave_blocks, f"New leave request from <@{user.username}>")
                
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
                
                if conflicts['has_conflicts']:
                    confirmation_message += f"\n\n⚠️ *Note:* {conflicts['message']}"
                
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