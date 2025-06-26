from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
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
    update_leave_thread, SLACK_MANAGER_CHANNEL, send_employee_notification,
    send_manager_update_notification  # Add this missing import
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
    # REMOVE handle_team_calendar from this import - it's now only in calendar_handlers
)
from .modal_handlers import handle_leave_request_modal_submission, handle_email_leave_request_modal_submission
from .block_action_handlers import handle_block_actions
from .calendar_handlers import handle_team_calendar, handle_team_calendar_filter_submission  # Import from calendar_handlers only

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
                        # CRITICAL FIX: Remove the channel and manager checks from here
                        # Let the command handler deal with permissions and return immediate response
                        # This prevents timeout issues
                        if not is_manager(user_id):
                            return JsonResponse({'text': 'Sorry, only managers can access the team calendar.'})
                        return handle_team_calendar(request)
                    elif command == '/make-manager':
                        return handle_make_manager_command(request)
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
                    elif command == '/debug-manager':
                        return handle_debug_manager_command(request)
                        
                elif request.POST.get('payload'):
                    # Handle interaction payload (button clicks, modal submissions)
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
        elif callback_id == 'email_leave_request_modal':  # Add this missing handler
            return handle_email_leave_request_modal_submission(payload)
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
    """Handle document upload modal submission with immediate response and background processing"""
    try:
        # IMMEDIATE RESPONSE - Return success first to avoid timeout
        def process_document_upload_background():
            """Background function to process document upload"""
            try:
                # Get leave request ID and details
                leave_id = payload['view']['private_metadata']
                leave_request = LeaveRequest.objects.get(id=leave_id)
                values = payload['view']['state']['values']
                
                # Process file and notes
                file_info = values['document_upload']['file_upload']
                doc_notes = values.get('document_notes', {}).get('notes_input', {}).get('value', '')
                
                # Check if file was actually uploaded
                if not file_info.get('files') or len(file_info['files']) == 0:
                    # Send error message to employee via threaded DM
                    send_employee_notification(
                        leave_request,
                        [{
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": (
                                    f"❌ *Document Upload Failed*\n\n"
                                    f"No file was detected in your upload. Please try again.\n"
                                    f"*Leave Type:* {leave_request.leave_type}\n"
                                    f"*Duration:* {leave_request.start_date} to {leave_request.end_date}"
                                )
                            }
                        }],
                        "Document upload failed - no file detected",
                        notification_type="document_upload_error"
                    )
                    return
                
                # Get file information - SIMPLE APPROACH
                uploaded_file = file_info['files'][0]
                file_id = uploaded_file['id']
                file_name = uploaded_file.get('name', 'document')
                file_size = uploaded_file.get('size', 0)
                file_type = uploaded_file.get('filetype', 'unknown')
                
                # Use the simplest working URL - don't overcomplicate
                file_url = uploaded_file.get('url_private_download') or uploaded_file.get('url_private')
                
                # Update leave request
                leave_request.document_status = 'SUBMITTED'
                leave_request.status = 'DOCS_SUBMITTED'
                leave_request.document_notes = (
                    f"File ID: {file_id}\n"
                    f"File Name: {file_name}\n"
                    f"File Type: {file_type}\n"
                    f"File Size: {file_size} bytes\n"
                    f"Employee Notes: {doc_notes}"
                )
                leave_request.document_submission_date = timezone.now().date()
                leave_request.save()
                from .slack_utils import send_document_directly_to_managers
                send_document_directly_to_managers(leave_request, file_id, file_name, doc_notes)
                # Simple manager notification - just like it was working before
                document_blocks = [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": "📄 Document Submitted for Review",
                            "emoji": True
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"*Employee:* <@{leave_request.employee.username}>\n"
                                f"*Leave Type:* {leave_request.leave_type}\n"
                                f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                                f"*Document Type:* {leave_request.document_type}\n"
                                f"*File Name:* `{file_name}`\n"
                                f"*File Type:* {file_type.upper()}\n"
                                f"*Employee Notes:* {doc_notes or '_No notes provided_'}"
                            )
                        }
                    },
                    {
                        "type": "divider"
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"📄 *Click to view document:* <{file_url}|View {file_name}>"
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
                            },
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "📄 Get Document", "emoji": True},
                                "value": f"{leave_request.id}|ACCESS_DOC",
                                "action_id": "access_document"
                            }
                        ]
                    }
                ]
                
                # Send THREADED notification to ALL MANAGERS in their DMs
                send_manager_update_notification(
                    leave_request,
                    document_blocks,
                    f"Document submitted by <@{leave_request.employee.username}> for review",
                    exclude_manager_id=None,
                    notification_type="document_submitted"
                )
                
                # Send THREADED confirmation to EMPLOYEE in their DM
                employee_blocks = [{
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"✅ *Document Submitted Successfully*\n\n"
                            f"Your document has been submitted and is pending review.\n"
                            f"*Leave Type:* {leave_request.leave_type}\n"
                            f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                            f"*Document Type:* {leave_request.document_type}\n"
                            f"*File:* {file_name} ({file_type.upper()})\n"
                            f"*Status:* Pending Review\n\n"
                            f"🔗 *Managers have been notified*"
                        )
                    }
                }]
                
                send_employee_notification(
                    leave_request,
                    employee_blocks,
                    "Document submitted successfully",
                    notification_type="document_confirmation"
                )
                        
            except Exception as e:
                logger.error(f"Background error processing document upload: {e}")
                # Send error notification to employee via threaded DM
                try:
                    leave_request = LeaveRequest.objects.get(id=payload['view']['private_metadata'])
                    send_employee_notification(
                        leave_request,
                        [{
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"❌ *Document Upload Error*\n\nThere was an error processing your document upload: {str(e)}\n\nPlease try again."
                            }
                        }],
                        f"Document upload error: {str(e)}",
                        notification_type="document_upload_error"
                    )
                except:
                    pass
                
        # Start background thread IMMEDIATELY
        import threading
        thread = threading.Thread(target=process_document_upload_background)
        thread.daemon = True
        thread.start()
        
        # Return immediate response to clear modal (prevents timeout)
        return JsonResponse({"response_action": "clear"})
        
    except Exception as e:
        logger.error(f"Error in document upload modal submission: {e}")
        return JsonResponse({
            "response_action": "errors",
            "errors": {
                "document_upload": f"Error processing upload: {str(e)}"
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
        
        # Send confirmation to employee via threading
        employee_confirmation_blocks = [{
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
        }]
        
        send_employee_notification(
            leave_request,
            employee_confirmation_blocks,
            "Compensatory work date confirmed",
            notification_type="final_confirmation"
        )
        
        return JsonResponse({"response_action": "clear"})
        
    except Exception as e:
        logger.error(f"Error processing compensatory date selection: {e}")
        return JsonResponse({
            "response_action": "errors",
            "errors": {
                "comp_date": f"Error processing date selection: {str(e)}"
            }
        })

def handle_slack_command(request):
    """Handle Slack slash commands"""
    try:
        command = request.POST.get('command')
        
        if command == '/apply-leave':
            return handle_apply_leave(request)
        elif command == '/my-leaves':
            return handle_my_leaves(request)
        elif command == '/leave-balance':
            return handle_leave_balance(request)
        elif command == '/leave-policy':
            return handle_leave_policy(request)
        elif command == '/department':
            return handle_department_command(request)
        elif command == '/team-calendar':
            return handle_team_calendar(request)
        elif command == '/assign-manager':  # NEW COMMAND
            return handle_assign_manager_command(request)
        else:
            return JsonResponse({'text': f'Unknown command: {command}'})
            
    except Exception as e:
        logger.error(f"Error handling command: {e}")
        return JsonResponse({'text': 'Error processing command'}, status=200)

def handle_assign_manager_command(request):
    """Handle manager role assignment command - NEW"""
    try:
        text = request.POST.get('text', '').strip()
        user_id = request.POST.get('user_id')
        
        if not text:
            return JsonResponse({
                'text': (
                    "👔 *Assign Manager Role*\n\n"
                    "*Usage:* `/make-manager @username`\n"
                    "*Example:* `/make-manager @john.doe`\n\n"
                    "This command assigns manager role to the specified user."
                )
            })
        
        def assign_manager_role():
            """Background function to assign manager role"""
            try:
                # Extract username from text
                target_user_id = text.replace('@', '').replace('<', '').replace('>', '').strip()
                if target_user_id.startswith('U'):
                    # It's a user ID
                    target_user = get_or_create_user(target_user_id)
                else:
                    # It's a username, find user by username
                    from django.contrib.auth.models import User
                    target_user = User.objects.filter(username=target_user_id).first()
                    if not target_user:
                        slack_client.chat_postMessage(
                            channel=user_id,
                            text=f"❌ User not found: {target_user_id}"
                        )
                        return
                
                # Assign manager role
                from .models import UserRole
                user_role, created = UserRole.objects.get_or_create(user=target_user)
                user_role.role = 'MANAGER'
                user_role.is_admin = True
                user_role.save()
                
                success_text = (
                    f"✅ *Manager Role Assigned*\n\n"
                    f"*User:* <@{target_user.username}>\n"
                    f"*Role:* MANAGER\n"
                    f"*Admin Status:* Yes\n"
                    f"*Assigned by:* <@{user_id}>\n\n"
                    f"User can now access team calendar and manager features."
                )
                
                # Send confirmation to requesting manager
                slack_client.chat_postMessage(
                    channel=user_id,
                    text=success_text
                )
                
                # Notify the assigned user
                slack_client.chat_postMessage(
                    channel=target_user.username,
                    text=(
                        f"👔 *You've been assigned Manager Role*\n\n"
                        f"*Assigned by:* <@{user_id}>\n"
                        f"*New Role:* MANAGER\n\n"
                        f"You can now use manager commands like `/team-calendar`"
                    )
                )
                
            except Exception as e:
                logger.error(f"Error assigning manager role: {e}")
                slack_client.chat_postMessage(
                    channel=user_id,
                    text=f"❌ Error assigning manager role: {str(e)}"
                )
        
        # Start background thread
        import threading
        thread = threading.Thread(target=assign_manager_role)
        thread.daemon = True
        thread.start()
        
        return JsonResponse({'text': '⏳ Assigning manager role...'})
        
    except Exception as e:
        logger.error(f"Error in assign manager command: {e}")
        return JsonResponse({'text': 'Error processing manager assignment'}, status=200)

def handle_make_manager_command(request):
    """Handle make manager command with background processing to avoid timeout"""
    try:
        text = request.POST.get('text', '').strip()
        user_id = request.POST.get('user_id')
        
        def process_make_manager_background():
            """Background function to process make manager request"""
            try:
                # Check if the requesting user is already a manager
                if not is_manager(user_id):
                    slack_client.chat_postMessage(
                        channel=user_id,
                        text='❌ *Access Denied*\n\nOnly existing managers can assign manager roles to other users.\n\nIf you need manager access, please contact your current manager or system administrator.'
                    )
                    return
                
                # Get target user from text
                if not text:
                    slack_client.chat_postMessage(
                        channel=user_id,
                        text=(
                            "👔 *Make Manager Command*\n\n"
                            "*Usage:* `/make-manager @username` or `/make-manager <@U123456>`\n"
                            "*Example:* `/make-manager @john.doe` or `/make-manager <@U090M1K5DB4>`\n\n"
                            "💡 *Tip:* Use @ to mention the user directly for best results."
                        )
                    )
                    return
                
                # FIXED: Better parsing - extract actual Slack user ID
                target_user_input = text.strip()
                target_slack_id = None
                
                # Extract Slack user ID from mention format <@U123456> or <@U123456|username>
                if target_user_input.startswith('<@') and target_user_input.endswith('>'):
                    # Format: <@U123456> or <@U123456|username>
                    user_part = target_user_input[2:-1]  # Remove <@ and >
                    if '|' in user_part:
                        target_slack_id = user_part.split('|')[0]  # Get ID part before |
                    else:
                        target_slack_id = user_part
                elif target_user_input.startswith('@'):
                    # Format: @username - need to look up
                    username = target_user_input[1:]  # Remove @
                    try:
                        # Try to find user in Slack by username
                        users_response = slack_client.users_list()
                        if users_response['ok']:
                            for member in users_response['members']:
                                if (member.get('name') == username or 
                                    member.get('profile', {}).get('display_name', '').lower() == username.lower() or
                                    member.get('profile', {}).get('real_name', '').lower() == username.lower()):
                                    target_slack_id = member['id']
                                    break
                    except Exception as e:
                        logger.error(f"Error searching Slack users: {e}")
                elif target_user_input.startswith('U') and len(target_user_input) == 11:
                    # Direct Slack user ID
                    target_slack_id = target_user_input
                else:
                    # Plain username - try to find in Slack
                    try:
                        users_response = slack_client.users_list()
                        if users_response['ok']:
                            for member in users_response['members']:
                                if (member.get('name') == target_user_input or 
                                    member.get('profile', {}).get('display_name', '').lower() == target_user_input.lower() or
                                    member.get('profile', {}).get('real_name', '').lower() == target_user_input.lower()):
                                    target_slack_id = member['id']
                                    break
                    except Exception as e:
                        logger.error(f"Error searching Slack users: {e}")
                
                if not target_slack_id:
                    slack_client.chat_postMessage(
                        channel=user_id,
                        text=(
                            f"❌ *User Not Found*\n\n"
                            f"Could not find user from input: `{target_user_input}`\n\n"
                            f"💡 *Try these formats:*\n"
                            f"• `/make-manager <@U123456>` (mention the user)\n"
                            f"• `/make-manager @username`\n"
                            f"• Make sure they're in this Slack workspace"
                        )
                    )
                    return
                
                # CRITICAL FIX: Create user with consistent Slack ID as username
                target_user = get_or_create_user(target_slack_id)
                
                # Verify the user was created correctly
                logger.info(f"MAKE_MANAGER: Target user created/found - Username: {target_user.username}, Slack ID: {target_slack_id}")
                
                # Assign manager role
                from .models import UserRole
                user_role, created = UserRole.objects.get_or_create(user=target_user)
                old_role = user_role.role
                user_role.role = 'MANAGER'
                user_role.is_admin = True
                user_role.save()
                
                # VERIFICATION: Check if the assignment worked
                logger.info(f"MAKE_MANAGER: Role assignment - User ID: {target_user.id}, Role: {user_role.role}, Is Admin: {user_role.is_admin}")
                
                # Test if is_manager function works for this user
                manager_check = is_manager(target_slack_id)
                logger.info(f"MAKE_MANAGER: Manager check result for {target_slack_id}: {manager_check}")
                
                success_text = (
                    f"✅ *Manager Role Assigned Successfully*\n\n"
                    f"*User:* <@{target_slack_id}>\n"
                    f"*Slack ID:* `{target_slack_id}`\n"
                    f"*Previous Role:* {old_role or 'EMPLOYEE'}\n"
                    f"*New Role:* MANAGER\n"
                    f"*Admin Status:* Yes\n"
                    f"*Manager Check:* {'✅ PASS' if manager_check else '❌ FAIL'}\n"
                    f"*Assigned by:* <@{user_id}>\n\n"
                    f"🎯 *User can now access:*\n"
                    f"• Team calendar (`/team-calendar`)\n"
                    f"• Manager features\n"
                    f"• Leave approvals"
                )
                
                # Send confirmation to requesting manager
                slack_client.chat_postMessage(
                    channel=user_id,
                    text=success_text
                )
                
                # Send notification to the assigned user
                try:
                    slack_client.chat_postMessage(
                        channel=target_slack_id,
                        text=(
                            f"👔 *You've been assigned Manager Role*\n\n"
                            f"*Assigned by:* <@{user_id}>\n"
                            f"*New Role:* MANAGER\n\n"
                            f"🎯 *You can now use:*\n"
                            f"• `/team-calendar` - View team leave calendar\n"
                            f"• Manager commands and features\n"
                            f"• Leave approval workflows\n\n"
                            f"Welcome to the management team! 🎉"
                        )
                    )
                    logger.info(f"MAKE_MANAGER: Notification sent successfully to {target_slack_id}")
                except SlackApiError as e:
                    logger.warning(f"MAKE_MANAGER: Failed to send notification to {target_slack_id}: {e}")
                    slack_client.chat_postMessage(
                        channel=user_id,
                        text=(
                            f"⚠️ *Manager Role Assigned Successfully*\n\n"
                            f"The user <@{target_slack_id}> has been assigned the manager role successfully, "
                            f"but we couldn't send them a notification due to a Slack API issue.\n\n"
                            f"Please inform them manually that they now have manager access."
                        )
                    )
                    
            except Exception as e:
                logger.error(f"Background error in make manager: {e}")
                try:
                    slack_client.chat_postMessage(
                        channel=user_id,
                        text=f"❌ *System Error*\n\nThere was a system error processing your request: {str(e)}\n\nPlease try again later."
                    )
                except:
                    pass
        
        # Start background thread
        import threading
        thread = threading.Thread(target=process_make_manager_background)
        thread.daemon = True
        thread.start()
        
        # Return immediate response to avoid timeout
        return JsonResponse({'text': '⏳ Processing manager assignment request...'})
        
    except Exception as e:
        logger.error(f"Error in make manager command: {e}")
        return JsonResponse({'text': '❌ Error processing manager assignment request'}, status=200)

def handle_debug_manager_command(request):
    """Debug command to check manager status"""
    try:
        user_id = request.POST.get('user_id')
        text = request.POST.get('text', '').strip()
        
        if text:
            # Check specific user
            target_user_id = text.replace('@', '').replace('<', '').replace('>', '').strip()
            if '|' in target_user_id:
                target_user_id = target_user_id.split('|')[0]
        else:
            # Check current user
            target_user_id = user_id
        
        # Get user info
        try:
            user = get_or_create_user(target_user_id)
            from .models import UserRole
            user_role = UserRole.objects.filter(user=user).first()
            
            manager_status = is_manager(target_user_id)
            
            debug_text = (
                f"🔍 *Manager Status Debug*\n\n"
                f"*Target User:* <@{target_user_id}>\n"
                f"*Slack ID:* `{target_user_id}`\n"
                f"*DB Username:* `{user.username}`\n"
                f"*DB User ID:* `{user.id}`\n"
                f"*Role:* {user_role.role if user_role else 'None'}\n"
                f"*Is Admin:* {user_role.is_admin if user_role else 'False'}\n"
                f"*Manager Check Result:* {'✅ TRUE' if manager_status else '❌ FALSE'}\n\n"
                f"*Raw Data:*\n"
                f"```\n"
                f"UserRole ID: {user_role.id if user_role else 'None'}\n"
                f"Role Value: '{user_role.role}' if user_role else 'None'\n"
                f"Admin Value: {user_role.is_admin if user_role else 'None'}\n"
                f"```"
            )
            
            return JsonResponse({'text': debug_text})
            
        except Exception as e:
            return JsonResponse({'text': f"❌ Error checking user: {str(e)}"})
            
    except Exception as e:
        return JsonResponse({'text': f"❌ Debug error: {str(e)}"})