from django.http import JsonResponse
from .slack_utils import slack_client, update_leave_thread
from .leave_utils import update_leave_balance_on_approval
from .approval_utils import create_compensatory_notification_blocks, process_employee_response, create_document_upload_modal
from .models import LeaveRequest
from django.utils import timezone
from slack_sdk.errors import SlackApiError
import logging
from .file_access_handler import handle_document_access_request

logger = logging.getLogger(__name__)

def handle_block_actions(payload):
    """
    Main handler for all block action button clicks in Slack messages
    
    WORKFLOW ROUTING (Updated to match leave_tmp_out):
    - All notifications go to individual DMs with threading
    - Action buttons are removed after click and replaced with status
    - No messages sent to leave-approval channel
    """
    try:
        action = payload['actions'][0]
        action_id = action['action_id']
        
        if action_id == 'upload_document':
            return handle_upload_document_action(payload, action)
        elif action_id in ['approve_unpaid', 'approve_compensatory']:
            return handle_compensatory_actions(payload, action, action_id)
        elif action_id in ['employee_accept_unpaid', 'employee_reject_offer', 'employee_accept_comp']:
            return handle_employee_responses(payload, action, action_id)
        elif action_id in ['request_med_cert', 'request_docs', 'request_medical_certificate']:
            return handle_document_requests(payload, action, action_id)
        elif action_id == 'submit_doc_later':
            return handle_submit_doc_later(payload, action)
        elif action_id == 'cancel_request':
            return handle_cancel_request(payload, action)
        elif action_id in ['verify_document', 'reject_document']:
            return handle_document_verification(payload, action, action_id)
        elif action_id in ['approve_regular', 'reject_leave', 'approve_leave']:
            return handle_regular_approval(payload, action, action_id)
        elif action_id == 'get_fresh_file_link':
            return handle_get_fresh_file_link_action(payload)
        elif action_id == 'reshare_file':
            return handle_reshare_file_action(payload)
        elif action_id == 'reshare_document':
            return handle_reshare_document_action(payload)
        elif action_id == 'access_document':
            return handle_document_access_request(payload)
        # Return default response
        return JsonResponse({'status': 'ok'})
        
    except LeaveRequest.DoesNotExist:
        return JsonResponse({'text': 'Leave request not found'}, status=200)
    except Exception as e:
        logger.error(f"Error handling block actions: {e}")
        return JsonResponse({'text': f'Error: {str(e)}'}, status=200)

def handle_upload_document_action(payload, action):
    """Handle document upload button click - using working version logic"""
    leave_id = action['value'].split('|')[0]
    leave_request = LeaveRequest.objects.get(id=leave_id)
    
    # Update the original message to show upload in progress
    try:
        slack_client.chat_update(
            channel=payload['channel']['id'],
            ts=payload['message']['ts'],
            blocks=[{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"📎 *Document Upload in Progress*\n\n"
                        f"*Leave Type:* {leave_request.get_leave_type_display()}\n"
                        f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                        f"*Document Required:* {leave_request.document_type}\n"
                        f"*Status:* Opening upload form...\n\n"
                        f"✅ *Upload form opened - please complete the upload*"
                    )
                }
            }]
        )
    except Exception as e:
        logger.error(f"Error updating upload message: {e}")
    
    # Show upload modal - direct approach like working version
    slack_client.views_open(
        trigger_id=payload['trigger_id'],
        view=create_document_upload_modal(leave_request)
    )
    return JsonResponse({'text': 'Opening document upload form...'})

def handle_document_requests(payload, action, action_id):
    """Handle document request actions with proper threaded notifications like leave_tmp_out"""
    leave_id = action['value'].split('|')[0]
    leave_request = LeaveRequest.objects.get(id=leave_id)
    current_user_id = payload['user']['id']  # This is the manager requesting docs
    
    # Get supervisor comment with fallback
    state_values = payload.get('state', {}).get('values', {})
    comment_input = state_values.get('supervisor_comment', {}).get('comment_input', {})
    comment = comment_input.get('value') if comment_input and comment_input.get('value') else 'No comment provided'
    
    # Set document details based on action
    if action_id in ['request_med_cert', 'request_medical_certificate'] or action['value'].split('|')[1] == 'REQUEST_MED_CERT' or action['value'].split('|')[1] == 'REQUEST_DOCS':
        if leave_request.leave_type == 'SICK':
            doc_desc = "medical certificate"
            leave_request.document_type = 'Medical Certificate'
            doc_title = "Medical Certificate Required"
        elif leave_request.leave_type == 'MATERNITY':
            doc_desc = "medical certificate"
            leave_request.document_type = 'Medical Certificate'
            doc_title = "Medical Certificate Required"
        else:  # PATERNITY or others
            doc_desc = "birth certificate"
            leave_request.document_type = 'Birth Certificate'
            doc_title = "Birth Certificate Required"
    else:  # request_docs or REQUEST_BIRTH_CERT
        doc_desc = "birth certificate"
        leave_request.document_type = 'Birth Certificate'
        doc_title = "Birth Certificate Required"
    
    leave_request.document_status = 'PENDING'
    leave_request.status = 'PENDING_DOCS'
    leave_request.supervisor_comment = comment
    leave_request.save()
    
    # UPDATE: Remove buttons from original message and show action completed
    try:
        slack_client.chat_update(
            channel=payload['channel']['id'],
            ts=payload['message']['ts'],
            blocks=[{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"✅ *Action Completed: Document Requested*\n\n"
                        f"*Employee:* <@{leave_request.employee.username}>\n"
                        f"*Leave Type:* {leave_request.get_leave_type_display()}\n"
                        f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                        f"*Document Requested:* {doc_desc.title()}\n"
                        f"*Your Action:* Document requested\n"
                        f"*Your Comment:* {comment}\n"
                        f"*Status:* PENDING DOCUMENTS\n\n"
                        f"📨 *Employee has been notified and other managers updated*\n"
                        f"🔗 *Check thread for further updates*"
                    )
                }
            }]
        )
    except Exception as e:
        logger.error(f"Error updating original message after document request: {e}")
    
    # Create document request notification for EMPLOYEE - THREADED
    employee_notification_blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"📄 *{doc_title}*\n\n"
                    f"*Leave Type:* {leave_request.get_leave_type_display()}\n"
                    f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                    f"*Document Required:* {doc_desc.title()}\n"
                    f"*Status:* PENDING DOCUMENTS\n"
                    f"*Manager:* <@{current_user_id}>\n"
                    f"*Manager Comment:* {comment}\n\n"
                    f"Please choose one of the following options:"
                )
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "📎 Upload Document Now"},
                    "style": "primary",
                    "value": f"{leave_request.id}|UPLOAD_DOC",
                    "action_id": "upload_document"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "⏰ Submit Later"},
                    "value": f"{leave_request.id}|SUBMIT_LATER",
                    "action_id": "submit_doc_later"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✗ Cancel Request"},
                    "style": "danger",
                    "value": f"{leave_request.id}|CANCEL_REQUEST",
                    "action_id": "cancel_request"
                }
            ]
        }
    ]
    
    # Send THREADED notification to EMPLOYEE
    from .slack_utils import send_employee_notification
    send_employee_notification(
        leave_request,
        employee_notification_blocks,
        f"Document request from <@{current_user_id}>",
        notification_type="document_request"
    )
    
    # Create manager update notification for OTHER MANAGERS - THREADED
    manager_update_blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"📄 *Manager Action: Document Requested*\n\n"
                    f"*Employee:* <@{leave_request.employee.username}>\n"
                    f"*Leave Type:* {leave_request.get_leave_type_display()}\n"
                    f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                    f"*Document Requested:* {doc_desc.title()}\n"
                    f"*Action by:* <@{current_user_id}>\n"
                    f"*Manager Comment:* {comment}\n"
                    f"*Status:* PENDING DOCUMENTS\n\n"
                    f"Employee has been notified to submit the document."
                )
            }
        }
    ]
    
    # Send THREADED update to OTHER MANAGERS (excluding the one who took action)
    from .slack_utils import send_manager_update_notification
    send_manager_update_notification(
        leave_request,
        manager_update_blocks,
        f"Document requested by <@{current_user_id}> for <@{leave_request.employee.username}>",
        exclude_manager_id=current_user_id,
        notification_type="manager_action_update"
    )
    
    return JsonResponse({'status': 'ok'})

def handle_regular_approval(payload, action, action_id):
    """Handle regular approval and rejection actions with proper threaded notifications like leave_tmp_out"""
    leave_id = action['value'].split('|')[0]
    leave_request = LeaveRequest.objects.get(id=leave_id)
    current_user_id = payload['user']['id']  # This is the manager taking action
    
    # Get supervisor comment with fallback
    state_values = payload.get('state', {}).get('values', {})
    comment = state_values.get('supervisor_comment', {}).get('comment_input', {}).get('value', 'No comment provided')
    
    # Handle different action_id variations
    if action_id in ['approve_regular', 'approve_leave']:
        leave_request.status = 'APPROVED'
        status_text = "approved"
        emoji = "✅"
        # Update leave balance when approved
        update_leave_balance_on_approval(leave_request)
    else:  # reject_leave
        leave_request.status = 'REJECTED'
        status_text = "rejected"
        emoji = "❌"
    
    leave_request.supervisor_comment = comment
    leave_request.save()
    
    # UPDATE: Remove buttons from original message and show action completed
    try:
        slack_client.chat_update(
            channel=payload['channel']['id'],
            ts=payload['message']['ts'],
            blocks=[{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"{emoji} *Action Completed: Leave Request {status_text.upper()}*\n\n"
                        f"*Employee:* <@{leave_request.employee.username}>\n"
                        f"*Leave Type:* {leave_request.get_leave_type_display()}\n"
                        f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                        f"*Your Action:* {status_text.title()}\n"
                        f"*Your Comment:* {comment}\n"
                        f"*Final Status:* {status_text.upper()}\n\n"
                        f"📨 *Employee and other managers have been notified*\n"
                        f"🔒 *This request is now complete*"
                    )
                }
            }]
        )
    except Exception as e:
        logger.error(f"Error updating original message after regular approval: {e}")
    
    # Create THREADED notification for EMPLOYEE
    employee_notification_blocks = [{
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                f"{emoji} *Leave Request - FINAL DECISION*\n\n"
                f"Your leave request has been *{status_text.upper()}*\n\n"
                f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                f"*Manager:* <@{current_user_id}>\n"
                f"*Final Status:* {status_text.upper()}\n"
                f"*Comment:* {comment}\n\n"
                f"🔒 *This request is now complete.*"
            )
        }
    }]
    
    # Send THREADED notification to EMPLOYEE
    from .slack_utils import send_employee_notification
    send_employee_notification(
        leave_request,
        employee_notification_blocks,
        f"Leave request {status_text} by <@{current_user_id}>",
        notification_type="final_decision"
    )
    
    # Create THREADED manager update notification for OTHER MANAGERS
    manager_update_blocks = [{
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                f"{emoji} *Manager Action: Leave Request {status_text.upper()}*\n\n"
                f"*Employee:* <@{leave_request.employee.username}>\n"
                f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                f"*Action by:* <@{current_user_id}>\n"
                f"*Final Status:* {status_text.upper()}\n"
                f"*Comment:* {comment}\n\n"
                f"🔒 *This request is now complete.*"
            )
        }
    }]
    
    # Send THREADED update to OTHER MANAGERS (excluding the one who took action)
    from .slack_utils import send_manager_update_notification
    send_manager_update_notification(
        leave_request,
        manager_update_blocks,
        f"Leave request {status_text} by <@{current_user_id}> for <@{leave_request.employee.username}>",
        exclude_manager_id=current_user_id,
        notification_type="final_decision"
    )
    
    return JsonResponse({'status': 'ok'})

def handle_compensatory_actions(payload, action, action_id):
    """Handle unpaid and compensatory leave actions with proper threaded notifications like leave_tmp_out"""
    leave_id = action['value'].split('|')[0]
    leave_request = LeaveRequest.objects.get(id=leave_id)
    current_user_id = payload['user']['id']
    
    # Get supervisor comment with fallback
    state_values = payload.get('state', {}).get('values', {})
    comment_input = state_values.get('supervisor_comment', {}).get('comment_input', {})
    comment = comment_input.get('value') if comment_input and comment_input.get('value') else 'No comment provided'
    
    # Create employee notification and get status
    notification_blocks = create_compensatory_notification_blocks(leave_request, action_id, comment)
    status_text = "offered as unpaid leave" if action_id == 'approve_unpaid' else "offered with compensatory work"
    
    # UPDATE: Remove buttons from original message and show action completed
    try:
        slack_client.chat_update(
            channel=payload['channel']['id'],
            ts=payload['message']['ts'],
            blocks=[{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"💡 *Action Completed: {status_text.title()}*\n\n"
                        f"*Employee:* <@{leave_request.employee.username}>\n"
                        f"*Leave Type:* {leave_request.get_leave_type_display()}\n"
                        f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                        f"*Your Action:* {status_text.title()}\n"
                        f"*Your Comment:* {comment}\n"
                        f"*Status:* Waiting for employee response\n\n"
                        f"📨 *Employee has been notified to accept/reject*\n"
                        f"🔗 *Check thread for employee response*"
                    )
                }
            }]
        )
    except Exception as e:
        logger.error(f"Error updating original message after compensatory action: {e}")
    
    # Send THREADED notification to EMPLOYEE ONLY
    from .slack_utils import send_employee_notification
    send_employee_notification(
        leave_request,
        notification_blocks,
        f"Manager <@{current_user_id}> {status_text}",
        notification_type="compensatory_offer"
    )
    
    # Create THREADED manager update for OTHER MANAGERS
    manager_update_blocks = [{
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                f"💡 *Manager Action: {status_text.title()}*\n\n"
                f"*Employee:* <@{leave_request.employee.username}>\n"
                f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                f"*Action by:* <@{current_user_id}>\n"
                f"*Offer:* {status_text.title()}\n"
                f"*Manager Comment:* {comment}\n"
                f"*Status:* Waiting for employee response\n\n"
                f"Employee has been notified to accept or reject the offer."
            )
        }
    }]
    
    # Send THREADED update to OTHER MANAGERS
    from .slack_utils import send_manager_update_notification
    send_manager_update_notification(
        leave_request,
        manager_update_blocks,
        f"{status_text.title()} by <@{current_user_id}> for <@{leave_request.employee.username}>",
        exclude_manager_id=current_user_id,
        notification_type="compensatory_offer"
    )
    
    return JsonResponse({'status': 'ok'})

def handle_employee_responses(payload, action, action_id):
    """Handle employee responses with proper threaded notifications to managers like leave_tmp_out"""
    leave_id = action['value'].split('|')[0]
    leave_request = LeaveRequest.objects.get(id=leave_id)
    current_user_id = payload['user']['id']  # This is the employee responding
    
    # Process response and create notification
    if action_id == 'employee_accept_comp':
        # Update the original message to show acceptance
        try:
            slack_client.chat_update(
                channel=payload['channel']['id'],
                ts=payload['message']['ts'],
                blocks=[{
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"🔄 *Compensatory Work Accepted*\n\n"
                            f"*Leave Type:* {leave_request.get_leave_type_display()}\n"
                            f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                            f"*Status:* You accepted compensatory work arrangement\n\n"
                            f"✅ *Date selection form opened - please choose your work date*"
                        )
                    }
                }]
            )
        except Exception as e:
            logger.error(f"Error updating employee response message: {e}")
        
        # For compensatory work, ask employee to choose a date
        leave_request.status = 'PENDING_COMP_DATE'
        leave_request.save()
        
        # Create date selection modal
        date_modal = {
            "type": "modal",
            "callback_id": "comp_date_selection",
            "title": {"type": "plain_text", "text": "Select Compensatory Date"},
            "submit": {"type": "plain_text", "text": "Confirm Date"},
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"*Please select when you will do compensatory work:*\n\n"
                            f"*Leave Period:* {leave_request.start_date} to {leave_request.end_date}\n"
                            f"*Duration:* {(leave_request.end_date - leave_request.start_date).days + 1} days\n\n"
                            f"You need to complete equivalent work hours on the selected date(s)."
                        )
                    }
                },
                {
                    "type": "input",
                    "block_id": "comp_date",
                    "element": {
                        "type": "datepicker",
                        "action_id": "date_select",
                        "placeholder": {"type": "plain_text", "text": "Select compensatory work date"}
                    },
                    "label": {"type": "plain_text", "text": "Compensatory Work Date"}
                }
            ],
            "private_metadata": str(leave_request.id)
        }
        
        slack_client.views_open(
            trigger_id=payload['trigger_id'],
            view=date_modal
        )
        
        # Notify ALL MANAGERS about acceptance with THREADING
        manager_notification_blocks = [{
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"🔄 *Employee Response: Accepted Compensatory Work*\n\n"
                    f"<@{leave_request.employee.username}> has accepted the compensatory work arrangement.\n"
                    f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                    f"*Status:* Employee is selecting compensatory work date"
                )
            }
        }]
        
        from .slack_utils import send_manager_update_notification
        send_manager_update_notification(
            leave_request,
            manager_notification_blocks,
            f"Employee <@{leave_request.employee.username}> accepted compensatory work",
            exclude_manager_id=None,  # Don't exclude any manager for employee responses
            notification_type="employee_response"
        )
        
        return JsonResponse({'status': 'ok'})
        
    else:
        # Handle other responses normally with THREADING
        notification_blocks, status_text = process_employee_response(leave_request, action_id, payload)
        
        # Update the original message to show response status
        response_emoji = "✅" if "accepted" in status_text else "❌"
        try:
            slack_client.chat_update(
                channel=payload['channel']['id'],
                ts=payload['message']['ts'],
                blocks=[{
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"{response_emoji} *Response Recorded*\n\n"
                            f"*Leave Type:* {leave_request.get_leave_type_display()}\n"
                            f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                            f"*Your Response:* {status_text.title()}\n"
                            f"*Status:* {leave_request.status}\n\n"
                            f"🔗 *Managers have been notified of your decision*"
                        )
                    }
                }]
            )
        except Exception as e:
            logger.error(f"Error updating employee response message: {e}")
        
        # Send THREADED notification to ALL MANAGERS (this is an employee response, so notify all managers)
        from .slack_utils import send_manager_update_notification
        send_manager_update_notification(
            leave_request,
            notification_blocks,
            f"Employee <@{leave_request.employee.username}> response: {status_text}",
            exclude_manager_id=None,  # Don't exclude any manager for employee responses
            notification_type="employee_response"
        )
        
        # Send THREADED acknowledgment to EMPLOYEE (like leave_tmp_out)
        try:
            slack_client.chat_postMessage(
                channel=current_user_id,
                thread_ts=leave_request.thread_ts if leave_request.thread_ts else None,
                blocks=[{
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"✅ *Leave Request Update*\n\n"
                            f"You have {status_text}\n"
                            f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                            f"*Status:* {leave_request.status}\n\n"
                            f"🔗 *Managers have been notified of your response*"
                        )
                    }
                }],
                text=f"Response recorded: {status_text}"
            )
        except Exception as e:
            logger.error(f"Error sending threaded employee acknowledgment: {e}")
        
        return JsonResponse({'status': 'ok'})

def handle_document_verification(payload, action, action_id):
    """Handle document verification and rejection with immediate response like leave_tmp_out"""
    try:
        # IMMEDIATE RESPONSE - Return success first to avoid timeout
        def process_document_verification_background():
            """Background function to process document verification"""
            try:
                leave_id = action['value'].split('|')[0]
                leave_request = LeaveRequest.objects.get(id=leave_id)
                current_user_id = payload['user']['id']
                state_values = payload.get('state', {}).get('values', {})
                comment = state_values.get('supervisor_comment', {}).get('comment_input', {}).get('value', 'No comment provided')
                
                if action_id == 'verify_document':
                    leave_request.document_status = 'APPROVED'
                    leave_request.status = 'APPROVED'
                    status_text = "verified and leave approved"
                    emoji = "✅"
                    final_status = "APPROVED"
                    # Update leave balance when approved
                    update_leave_balance_on_approval(leave_request)
                else:
                    leave_request.document_status = 'REJECTED'
                    leave_request.status = 'REJECTED'
                    status_text = "rejected"
                    emoji = "❌"
                    final_status = "REJECTED"
                
                leave_request.supervisor_comment = comment
                leave_request.save()
                
                # UPDATE: Remove buttons from original message and show action completed
                try:
                    slack_client.chat_update(
                        channel=payload['channel']['id'],
                        ts=payload['message']['ts'],
                        blocks=[{
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": (
                                    f"{emoji} *Action Completed: Document {status_text.upper()}*\n\n"
                                    f"*Employee:* <@{leave_request.employee.username}>\n"
                                    f"*Leave Type:* {leave_request.get_leave_type_display()}\n"
                                    f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                                    f"*Your Action:* Document {status_text}\n"
                                    f"*Your Comment:* {comment}\n"
                                    f"*Final Status:* {final_status}\n\n"
                                    f"📨 *Employee and other managers have been notified*\n"
                                    f"🔒 *This request is now complete*"
                                )
                            }
                        }]
                    )
                except Exception as e:
                    logger.error(f"Error updating original message after document verification: {e}")
                
                # Send THREADED notification to EMPLOYEE via DM (like leave_tmp_out)
                employee_notification_blocks = [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"{emoji} *Leave Request Update - FINAL DECISION*\n\n"
                                f"Your document has been {status_text} and your leave request is now **{final_status}**.\n\n"
                                f"*Leave Type:* {leave_request.get_leave_type_display()}\n"
                                f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                                f"*Document Status:* {status_text.upper()}\n"
                                f"*Leave Status:* {final_status}\n"
                                f"*Manager Comment:* {comment}"
                            )
                        }
                    }
                ]
                
                from .slack_utils import send_employee_notification
                send_employee_notification(
                    leave_request,
                    employee_notification_blocks,
                    f"Leave request {final_status.lower()} - Final decision",
                    notification_type="final_decision"
                )
                
                # Send THREADED notification to OTHER MANAGERS (like leave_tmp_out)
                manager_update_blocks = [{
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"{emoji} *FINAL DECISION: Document {status_text.upper()}*\n\n"
                            f"*Employee:* <@{leave_request.employee.username}>\n"
                            f"*Leave Type:* {leave_request.get_leave_type_display()}\n"
                            f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                            f"*Document Status:* {status_text.upper()}\n"
                            f"*Leave Status:* {final_status}\n"
                            f"*Reviewer:* <@{current_user_id}>\n"
                            f"*Final Comment:* {comment}\n\n"
                            f"🔒 *This request has been completed and the thread is now closed.*"
                        )
                    }
                }]
                
                from .slack_utils import send_manager_update_notification
                send_manager_update_notification(
                    leave_request,
                    manager_update_blocks,
                    f"FINAL: Document {status_text} - Thread closed",
                    exclude_manager_id=current_user_id,
                    notification_type="final_decision"
                )
                        
            except Exception as e:
                logger.error(f"Background error processing document verification: {e}")
                try:
                    slack_client.chat_postMessage(
                        channel=current_user_id,
                        text=f"❌ Error processing document verification: {str(e)}"
                    )
                except:
                    pass
        
        # Start background thread IMMEDIATELY
        import threading
        thread = threading.Thread(target=process_document_verification_background)
        thread.daemon = True
        thread.start()
        
        # Return immediate response (prevents timeout)
        return JsonResponse({'status': 'ok'})
        
    except Exception as e:
        logger.error(f"Error handling document verification: {e}")
        return JsonResponse({'text': f'Error: {str(e)}'}, status=200)

def handle_submit_doc_later(payload, action):
    """Handle employee choosing to submit documents later"""
    try:
        leave_id = action['value'].split('|')[0]
        leave_request = LeaveRequest.objects.get(id=leave_id)
        current_user_id = payload['user']['id']  # This is the employee
        
        # Update status to indicate documents will be submitted later
        leave_request.status = 'DOCS_PENDING_LATER'
        leave_request.save()
        
        # Update the original message to show decision
        try:
            slack_client.chat_update(
                channel=payload['channel']['id'],
                ts=payload['message']['ts'],
                blocks=[{
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"⏰ *Document Submission Delayed*\n\n"
                            f"*Leave Type:* {leave_request.get_leave_type_display()}\n"
                            f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                            f"*Document Required:* {leave_request.document_type}\n"
                            f"*Your Decision:* Will submit documents later\n"
                            f"*Status:* DOCUMENTS PENDING\n\n"
                            f"🔗 *Managers have been notified of your decision*"
                        )
                    }
                }]
            )
        except Exception as e:
            logger.error(f"Error updating submit later message: {e}")
        
        # Send THREADED notification to ALL MANAGERS
        manager_notification_blocks = [{
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"⏰ *Employee Response: Will Submit Documents Later*\n\n"
                    f"*Employee:* <@{leave_request.employee.username}>\n"
                    f"*Leave Type:* {leave_request.get_leave_type_display()}\n"
                    f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                    f"*Document Required:* {leave_request.document_type}\n"
                    f"*Status:* DOCUMENTS PENDING (Employee will submit later)\n\n"
                    f"Employee has chosen to submit documents at a later time."
                )
            }
        }]
        
        from .slack_utils import send_manager_update_notification
        send_manager_update_notification(
            leave_request,
            manager_notification_blocks,
            f"Employee <@{leave_request.employee.username}> will submit documents later",
            exclude_manager_id=None,
            notification_type="document_delay"
        )
        
        # Send THREADED acknowledgment to EMPLOYEE
        try:
            slack_client.chat_postMessage(
                channel=current_user_id,
                thread_ts=leave_request.thread_ts if leave_request.thread_ts else None,
                blocks=[{
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"⏰ *Document Submission Delayed*\n\n"
                            f"*Leave Type:* {leave_request.get_leave_type_display()}\n"
                            f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                            f"*Document Required:* {leave_request.document_type}\n"
                            f"*Status:* Documents pending (will submit later)\n\n"
                            f"🔗 *Managers have been notified. Remember to submit documents when ready.*"
                        )
                    }
                }],
                text="Document submission delayed"
            )
        except Exception as e:
            logger.error(f"Error sending threaded employee acknowledgment: {e}")
        
        return JsonResponse({'status': 'ok'})
        
    except Exception as e:
        logger.error(f"Error handling submit doc later: {e}")
        return JsonResponse({'text': f'Error: {str(e)}'}, status=200)

def handle_cancel_request(payload, action):
    """Handle employee canceling their leave request"""
    try:
        leave_id = action['value'].split('|')[0]
        leave_request = LeaveRequest.objects.get(id=leave_id)
        current_user_id = payload['user']['id']  # This is the employee
        
        # Update status to cancelled
        leave_request.status = 'CANCELLED'
        leave_request.save()
        
        # Update the original message to show cancellation
        try:
            slack_client.chat_update(
                channel=payload['channel']['id'],
                ts=payload['message']['ts'],
                blocks=[{
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"🚫 *Leave Request Cancelled*\n\n"
                            f"*Leave Type:* {leave_request.get_leave_type_display()}\n"
                            f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                            f"*Your Action:* Request cancelled\n"
                            f"*Final Status:* CANCELLED\n\n"
                            f"🔗 *Managers have been notified of the cancellation*"
                        )
                    }
                }]
            )
        except Exception as e:
            logger.error(f"Error updating cancel message: {e}")
        
        # Send THREADED notification to ALL MANAGERS
        manager_notification_blocks = [{
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"🚫 *Leave Request Cancelled by Employee*\n\n"
                    f"*Employee:* <@{leave_request.employee.username}>\n"
                    f"*Leave Type:* {leave_request.get_leave_type_display()}\n"
                    f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                    f"*Final Status:* CANCELLED\n\n"
                    f"🔒 *This request is now complete.*"
                )
            }
        }]
        
        from .slack_utils import send_manager_update_notification
        send_manager_update_notification(
            leave_request,
            manager_notification_blocks,
            f"Leave request cancelled by <@{leave_request.employee.username}>",
            exclude_manager_id=None,
            notification_type="request_cancelled"
        )
        
        # Send THREADED acknowledgment to EMPLOYEE
        try:
            slack_client.chat_postMessage(
                channel=current_user_id,
                thread_ts=leave_request.thread_ts if leave_request.thread_ts else None,
                blocks=[{
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"🚫 *Leave Request Cancelled*\n\n"
                            f"*Leave Type:* {leave_request.get_leave_type_display()}\n"
                            f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                            f"*Final Status:* CANCELLED\n\n"
                            f"🔗 *Managers have been notified. This request is now complete.*"
                        )
                    }
                }],
                text="Leave request cancelled"
            )
        except Exception as e:
            logger.error(f"Error sending threaded employee acknowledgment: {e}")
        
        return JsonResponse({'status': 'ok'})
        
    except Exception as e:
        logger.error(f"Error handling cancel request: {e}")
        return JsonResponse({'text': f'Error: {str(e)}'}, status=200)

def handle_get_fresh_file_link_action(payload):
    """Handle get fresh file link action"""
    try:
        action_value = payload['actions'][0]['value']
        leave_id = action_value.split('|')[0]
        leave_request = LeaveRequest.objects.get(id=leave_id)
        
        # Extract file ID from document_notes
        file_id = None
        if leave_request.document_notes:
            for line in leave_request.document_notes.split('\n'):
                if line.startswith('File ID:'):
                    file_id = line.split(': ')[1].strip()
                    break
        
        if not file_id:
            return JsonResponse({
                "response_type": "ephemeral",
                "text": "❌ Could not find file ID. Please contact the employee to reshare the document."
            })
        
        # Try to get a fresh file link with multiple methods
        try:
            file_response = slack_client.files_info(file=file_id)
            if file_response['ok']:
                file_data = file_response['file']
                file_name = file_data.get('name', 'document')
                
                # Try multiple URL methods
                fresh_url = None
                access_method = "failed"
                
                # Method 1: Try public URL
                try:
                    share_response = slack_client.files_sharedPublicURL(file=file_id)
                    if share_response['ok']:
                        fresh_url = share_response['file']['permalink_public']
                        access_method = "Fresh Public Link"
                except:
                    pass
                
                # Method 2: Try private download URL
                if not fresh_url:
                    fresh_url = file_data.get('url_private_download')
                    if fresh_url:
                        access_method = "Fresh Private Download Link"
                
                # Method 3: Fallback to private URL
                if not fresh_url:
                    fresh_url = file_data.get('url_private')
                    access_method = "Fresh Private Link"
                
                if fresh_url:
                    return JsonResponse({
                        "response_type": "ephemeral",
                        "blocks": [
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": (
                                        f"🔗 *Fresh Document Link Generated*\n\n"
                                        f"*File:* {file_name}\n"
                                        f"*Link Type:* {access_method}\n"
                                        f"*Employee:* <@{leave_request.employee.username}>\n\n"
                                        f"📄 **Click here to view:** <{fresh_url}|Open {file_name}>\n\n"
                                        f"💡 *Tip:* If this link still doesn't work, try the 'Re-share File' button or contact IT support."
                                    )
                                }
                            }
                        ]
                    })
                else:
                    return JsonResponse({
                        "response_type": "ephemeral",
                        "text": f"❌ Could not generate fresh link. File ID: `{file_id}`. Please try re-sharing the file."
                    })
            else:
                return JsonResponse({
                    "response_type": "ephemeral",
                    "text": f"❌ Could not access file information. File ID: `{file_id}`"
                })
                
        except Exception as e:
            logger.error(f"Error getting fresh file link: {e}")
            return JsonResponse({
                "response_type": "ephemeral",
                "text": f"❌ Error getting fresh file link: {str(e)}. File ID: `{file_id}`"
            })
            
    except Exception as e:
        logger.error(f"Error in get fresh file link action: {e}")
        return JsonResponse({
            "response_type": "ephemeral",
            "text": f"❌ Error: {str(e)}"
        })

def handle_reshare_file_action(payload):
    """Handle re-share file action"""
    try:
        action_value = payload['actions'][0]['value']
        leave_id = action_value.split('|')[0]
        leave_request = LeaveRequest.objects.get(id=leave_id)
        manager_id = payload['user']['id']
        
        # Extract file ID from document_notes
        file_id = None
        if leave_request.document_notes:
            for line in leave_request.document_notes.split('\n'):
                if line.startswith('File ID:'):
                    file_id = line.split(': ')[1].strip()
                    break
        
        if not file_id:
            return JsonResponse({
                "response_type": "ephemeral",
                "text": "❌ Could not find file ID. Please contact the employee to reshare the document."
            })
        
        try:
            # Share file directly to the manager's DM
            share_response = slack_client.files_share(
                file=file_id,
                channels=manager_id
            )
            
            if share_response['ok']:
                return JsonResponse({
                    "response_type": "ephemeral",
                    "text": (
                        f"✅ *File Re-shared Successfully*\n\n"
                        f"The document has been shared directly to your DM. "
                        f"Check your messages for the file. You should now be able to open it directly."
                    )
                })
            else:
                return JsonResponse({
                    "response_type": "ephemeral",
                    "text": f"❌ Could not re-share file. Error: {share_response.get('error', 'Unknown error')}"
                })
                
        except Exception as e:
            logger.error(f"Error re-sharing file: {e}")
            return JsonResponse({
                "response_type": "ephemeral",
                "text": f"❌ Error re-sharing file: {str(e)}"
            })
            
    except Exception as e:
        logger.error(f"Error in reshare file action: {e}")
        return JsonResponse({
            "response_type": "ephemeral",
            "text": f"❌ Error: {str(e)}"
        })

def handle_reshare_document_action(payload):
    """Handle reshare document action - simple approach"""
    try:
        action_value = payload['actions'][0]['value']
        leave_id = action_value.split('|')[0]
        leave_request = LeaveRequest.objects.get(id=leave_id)
        manager_id = payload['user']['id']
        
        # Extract file ID from document_notes
        file_id = None
        file_name = "document"
        if leave_request.document_notes:
            for line in leave_request.document_notes.split('\n'):
                if line.startswith('File ID:'):
                    file_id = line.split(': ')[1].strip()
                elif line.startswith('File Name:'):
                    file_name = line.split(': ')[1].strip()
        
        if not file_id:
            return JsonResponse({
                "response_type": "ephemeral",
                "text": "❌ Could not find file ID. Please ask the employee to resubmit the document."
            })
        
        try:
            # Simple approach: Share file directly to manager's DM
            response = slack_client.files_share(
                file=file_id,
                channels=manager_id
            )
            
            if response['ok']:
                return JsonResponse({
                    "response_type": "ephemeral",
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": (
                                    f"✅ *Document Reshared*\n\n"
                                    f"The document `{file_name}` has been shared to your DM.\n"
                                    f"Check your direct messages for the file.\n\n"
                                    f"*Employee:* <@{leave_request.employee.username}>\n"
                                    f"*Leave Type:* {leave_request.leave_type}\n"
                                    f"*Duration:* {leave_request.start_date} to {leave_request.end_date}"
                                )
                            }
                        }
                    ]
                })
            else:
                error_msg = response.get('error', 'Unknown error')
                return JsonResponse({
                    "response_type": "ephemeral",
                    "text": f"❌ Could not reshare document: {error_msg}. File ID: `{file_id}`"
                })
                
        except Exception as e:
            logger.error(f"Error resharing document: {e}")
            return JsonResponse({
                "response_type": "ephemeral",
                "text": f"❌ Error resharing document: {str(e)}. Please try again or contact the employee."
            })
            
    except Exception as e:
        logger.error(f"Error in reshare document action: {e}")
        return JsonResponse({
            "response_type": "ephemeral",
            "text": f"❌ Error: {str(e)}"
        })
    #                                 f"*Leave Type:* {leave_request.leave_type}\n"
    #                                 f"*Duration:* {leave_request.start_date} to {leave_request.end_date}"
    #                             )
    #                         }
    #                     }
    #                 ]
    #             })
    #         else:
    #             error_msg = response.get('error', 'Unknown error')
    #             return JsonResponse({
    #                 "response_type": "ephemeral",
    #                 "text": f"❌ Could not reshare document: {error_msg}. File ID: `{file_id}`"
    #             })
                
    #     except Exception as e:
    #         logger.error(f"Error resharing document: {e}")
    #         return JsonResponse({
    #             "response_type": "ephemeral",
    #             "text": f"❌ Error resharing document: {str(e)}. Please try again or contact the employee."
    #         })
            
    # except Exception as e:
    #     logger.error(f"Error in reshare document action: {e}")
    #     return JsonResponse({
    #         "response_type": "ephemeral",
    #         "text": f"❌ Error: {str(e)}"
    #     })

