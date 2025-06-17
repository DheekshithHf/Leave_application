from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.contrib.auth.models import User
from django.db import transaction
from datetime import datetime, timedelta
import json
import logging

# Import Slack SDK
from slack_sdk.errors import SlackApiError

# Import utility modules
from .slack_utils import (
    slack_client, get_or_create_user, is_manager, is_in_manager_channel,
    send_personal_notification, send_manager_notification, start_leave_request_thread,
    update_leave_thread, SLACK_MANAGER_CHANNEL
)
from .leave_utils import (
    get_leave_balance, get_maternity_leave_info, get_paternity_leave_info,
    update_leave_balance_on_approval, get_conflicts_details, get_department_conflicts,
    create_leave_block
)
from .team_utils import (
    handle_create_team, handle_view_team, handle_join_team, handle_leave_team,
    handle_remove_member, handle_admin_role
)
from .approval_utils import (
    create_compensatory_notification_blocks, process_employee_response,
    create_document_upload_modal
)
from .command_handlers import (
    handle_apply_leave, handle_my_leaves, handle_leave_balance, 
    handle_leave_policy, handle_department_command
)
from .modal_handlers import handle_leave_request_modal_submission
from .block_action_handlers import handle_block_actions
from .calendar_handlers import handle_team_calendar, handle_team_calendar_filter_submission
from .models import LeaveRequest, LeaveBalance, UserRole, Department, Team

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@csrf_exempt
def slack_events(request):
    logger.info(f"Received request method: {request.method}")
    logger.info(f"Content-Type: {request.headers.get('Content-Type')}")
    
    if request.method == "POST":
        try:
            # Handle form-encoded data (slash commands and interactions)
            if request.headers.get('Content-Type') == 'application/x-www-form-urlencoded':
                command = request.POST.get('command')
                user_id = request.POST.get('user_id')
                
                if command:
                    if command == '/apply-leave':
                        return handle_apply_leave(request)
                    elif command == '/my-leaves':
                        return handle_my_leaves(request)
                    elif command == '/leave-balance':
                        return handle_leave_balance(request)
                    elif command == '/leave-policy':
                        return handle_leave_policy(request)
                    elif command == '/team-calendar':
                        # Check if command is being used in the leave-approvals channel
                        channel_id = request.POST.get('channel_id')
                        if not is_in_manager_channel(channel_id):
                            return JsonResponse({'text': 'Sorry, this command can only be used in the leave-approvals channel by managers.'})
                        
                        if not is_manager(user_id):
                            return JsonResponse({'text': 'Sorry, only managers can access the team calendar.'})
                        return handle_team_calendar(request)
                    elif command == '/make-manager':
                        # Check if the requesting user is already a manager
                        if not is_manager(user_id):
                            return JsonResponse({'text': 'Sorry, only existing managers can assign manager roles.'})
                        
                        # Get target user from text
                        target_user = request.POST.get('text', '').strip()
                        if not target_user:
                            return JsonResponse({'text': 'Please specify a user to make manager. Format: /make-manager @username'})
                            
                        # Remove @ symbol if present
                        target_user = target_user.lstrip('@')
                        
                        try:
                            # Make the user a manager
                            get_or_create_user(target_user, is_manager=True)
                            return JsonResponse({'text': f'Success! <@{target_user}> is now a manager.'})
                        except Exception as e:
                            logger.error(f"Error making user manager: {e}")
                            return JsonResponse({'text': f'Error making user manager: {str(e)}'})
                    elif command == '/department':
                        return handle_department_command(request)
                    elif command == '/create-team':
                        return handle_create_team(request)
                    elif command == '/join-team':
                        return handle_join_team(request)
                    elif command == '/leave-team':
                        return handle_leave_team(request)
                    elif command == '/remove-member':
                        return handle_remove_member(request)
                    elif command == '/view-team':
                        return handle_view_team(request)
                    elif command == '/admin-role':
                        return handle_admin_role(request)
                        
                elif request.POST.get('payload'):
                    # Handle interaction payload
                    payload = json.loads(request.POST.get('payload'))
                    logger.info(f"Interaction payload: {payload}")
                    
                    if payload.get('type') == 'view_submission':
                        return handle_modal_submission(payload)
                    elif payload.get('type') == 'block_actions':
                        return handle_block_actions(payload)
                    
            # Handle JSON data (events API)
            elif request.headers.get('Content-Type') == 'application/json':
                body = json.loads(request.body.decode('utf-8'))
                logger.info(f"JSON payload: {body}")
                
                if body.get('type') == 'url_verification':
                    return JsonResponse({'challenge': body['challenge']})
            
            return JsonResponse({'status': 'ok'})
            
        except Exception as e:
            logger.error(f"Error processing request: {e}")
            return JsonResponse({'text': f'Error: {str(e)}'}, status=200)
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)

def handle_modal_submission(payload):
    """Route modal submissions to appropriate handlers"""
    try:
        view = payload['view']
        callback_id = view['callback_id']
        
        if callback_id == 'department_selection':
            return handle_department_modal_submission(payload)
        elif callback_id == 'team_calendar_filter':
            return handle_team_calendar_filter_submission(payload)
        elif callback_id == 'document_upload_modal':
            return handle_document_upload_modal_submission(payload)
        elif callback_id == 'leave_request_modal':
            return handle_leave_request_modal_submission(payload)
        elif callback_id == 'comp_date_selection':
            return handle_comp_date_selection(payload)
        
        return JsonResponse({})
            
    except Exception as e:
        logger.error(f"Error in modal submission routing: {e}")
        return JsonResponse({
            "response_action": "errors",
            "errors": {
                "general": f"Error processing request: {str(e)}"
            }
        })

def handle_department_modal_submission(payload):
    """Handle department selection modal submission"""
    try:
        # Process the department selection form
        values = payload['view']['state']['values']
        selected_department = values['department_select']['department_choice']['selected_option']['value']
        user = get_or_create_user(payload['user']['id'])
        
        # Get or create the predefined department
        department, created = Department.objects.get_or_create(name=selected_department)
        
        # Update user's department
        user_role, role_created = UserRole.objects.get_or_create(user=user)
        old_department = user_role.department.name if user_role.department else "None"
        user_role.department = department
        user_role.save()
        
        # Send confirmation message to user
        confirmation_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"✅ *Department Assignment Successful*\n\n"
                        f"*User:* <@{user.username}>\n"
                        f"*Previous Department:* {old_department}\n"
                        f"*New Department:* {selected_department}\n"
                        f"*Status:* Successfully assigned to {selected_department}"
                    )
                }
            }
        ]
        
        # Send confirmation to user (try leave_app channel first, fallback to DM)
        try:
            slack_client.chat_postMessage(
                channel='leave_app',
                blocks=confirmation_blocks,
                text=f"Successfully assigned to {selected_department} department"
            )
        except SlackApiError as channel_error:
            if 'channel_not_found' in str(channel_error):
                # Fallback to user DM if leave_app channel doesn't exist
                slack_client.chat_postMessage(
                    channel=user.username,
                    blocks=confirmation_blocks,
                    text=f"Successfully assigned to {selected_department} department"
                )
            else:
                raise channel_error
        
        return JsonResponse({"response_action": "clear"})
        
    except Exception as e:
        logger.error(f"Error processing department selection: {e}")
        return JsonResponse({
            "response_action": "errors",
            "errors": {
                "department_select": f"Error assigning department: {str(e)}"
            }
        })

def handle_document_upload_modal_submission(payload):
    """Handle document upload modal submission"""
    try:
        # Get leave request ID and details
        leave_id = payload['view']['private_metadata']
        leave_request = LeaveRequest.objects.get(id=leave_id)
        values = payload['view']['state']['values']
        
        # Process file and notes
        file_info = values['document_upload']['file_upload']
        doc_notes = values.get('document_notes', {}).get('notes_input', {}).get('value', '')
        
        # Update leave request
        leave_request.document_status = 'SUBMITTED'
        leave_request.status = 'DOCS_SUBMITTED'
        leave_request.document_notes = f"File ID: {file_info['files'][0]['id']}\nNotes: {doc_notes}"
        leave_request.document_submission_date = timezone.now().date()
        leave_request.save()
        
        # Send to leave-approvals thread instead of new message
        document_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"📄 *Document Submitted for Review*\n\n"
                        f"*Employee:* <@{leave_request.employee.username}>\n"
                        f"*Leave Type:* {leave_request.leave_type}\n"
                        f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                        f"*Document Type:* {leave_request.document_type}\n"
                        f"*File Link:* <{file_info['files'][0]['url_private']}|View Document>\n"
                        f"*Notes:* {doc_notes or 'No notes provided'}"
                    )
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "✅ Verify & Approve Leave", "emoji": True},
                        "style": "primary",
                        "value": f"{leave_request.id}|VERIFY_DOC",
                        "action_id": "verify_document"
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "❌ Reject Document", "emoji": True},
                        "style": "danger",
                        "value": f"{leave_request.id}|REJECT_DOC",
                        "action_id": "reject_document"
                    }
                ]
            }
        ]
        
        # Send to the document thread in manager channel
        if leave_request.thread_ts:
            update_leave_thread(
                leave_request,
                document_blocks,
                f"Document submitted by <@{leave_request.employee.username}> for review"
            )
        
        # Notify employee via leave_app channel instead of DM
        try:
            slack_client.chat_postMessage(
                channel='leave_app',
                blocks=[{
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"✅ *Document Submitted Successfully*\n\n"
                            f"Your document has been submitted and is pending review.\n"
                            f"*Leave Type:* {leave_request.leave_type}\n"
                            f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                            f"*Document Type:* {leave_request.document_type}\n"
                            f"*Status:* Pending Review"
                        )
                    }
                }],
                text="Document submitted successfully"
            )
        except SlackApiError as channel_error:
            if 'channel_not_found' in str(channel_error):
                # Fallback to user DM if leave_app channel doesn't exist
                slack_client.chat_postMessage(
                    channel=leave_request.employee.username,
                    blocks=[{
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"✅ *Document Submitted Successfully*\n\n"
                                f"Your document has been submitted and is pending review.\n"
                                f"*Leave Type:* {leave_request.leave_type}\n"
                                f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                                f"*Document Type:* {leave_request.document_type}\n"
                                f"*Status:* Pending Review"
                            )
                        }
                    }],
                    text="Document submitted successfully"
                )
            else:
                raise channel_error
        
        return JsonResponse({"response_action": "clear"})
        
    except Exception as e:
        logger.error(f"Error processing document submission: {e}")
        return JsonResponse({
            "response_action": "errors",
            "errors": {
                "document_upload": f"Error processing document: {str(e)}"
            }
        })

def handle_comp_date_selection(payload):
    """Handle compensatory date selection modal submission"""
    try:
        # Get leave request ID and details
        leave_id = payload['view']['private_metadata']
        leave_request = LeaveRequest.objects.get(id=leave_id)
        values = payload['view']['state']['values']
        
        # Get selected date
        selected_date = values['comp_date']['date_select']['selected_date']
        comp_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
        
        # Update leave request
        leave_request.compensatory_date = comp_date
        leave_request.status = 'APPROVED_COMPENSATORY'
        leave_request.save()
        
        # Update leave balance for approved compensatory leave
        from .leave_utils import update_leave_balance_on_approval
        update_leave_balance_on_approval(leave_request)
        
        # Notify manager about date selection
        if leave_request.thread_ts:
            update_leave_thread(
                leave_request,
                [{
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"✅ *FINAL DECISION: Compensatory Work Date Selected*\n\n"
                            f"*Employee:* <@{leave_request.employee.username}>\n"
                            f"*Leave Period:* {leave_request.start_date} to {leave_request.end_date}\n"
                            f"*Compensatory Work Date:* {comp_date}\n"
                            f"*Final Status:* APPROVED WITH COMPENSATORY WORK\n\n"
                            f"🔒 *This request has been completed and the thread is now closed.*"
                        )
                    }
                }],
                f"FINAL: Compensatory work date selected - Thread closed"
            )
        
        # Send confirmation to employee via leave_app channel
        try:
            slack_client.chat_postMessage(
                channel='leave_app',
                blocks=[{
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"✅ *Leave Request Finalized*\n\n"
                            f"Your compensatory work arrangement has been confirmed.\n"
                            f"*Leave Period:* {leave_request.start_date} to {leave_request.end_date}\n"
                            f"*Compensatory Work Date:* {comp_date}\n"
                            f"*Status:* APPROVED WITH COMPENSATORY WORK\n\n"
                            f"Please complete your compensatory work on the selected date."
                        )
                    }
                }],
                text="Compensatory work date confirmed"
            )
        except SlackApiError as channel_error:
            if 'channel_not_found' in str(channel_error):
                # Fallback to user DM if leave_app channel doesn't exist
                slack_client.chat_postMessage(
                    channel=leave_request.employee.username,
                    blocks=[{
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"✅ *Leave Request Finalized*\n\n"
                                f"Your compensatory work arrangement has been confirmed.\n"
                                f"*Leave Period:* {leave_request.start_date} to {leave_request.end_date}\n"
                                f"*Compensatory Work Date:* {comp_date}\n"
                                f"*Status:* APPROVED WITH COMPENSATORY WORK\n\n"
                                f"Please complete your compensatory work on the selected date."
                            )
                        }
                    }],
                    text="Compensatory work date confirmed"
                )
            else:
                raise channel_error
        
        return JsonResponse({"response_action": "clear"})
        
    except Exception as e:
        logger.error(f"Error processing compensatory date selection: {e}")
        return JsonResponse({
            "response_action": "errors",
            "errors": {
                "comp_date": f"Error processing date selection: {str(e)}"
            }
        })