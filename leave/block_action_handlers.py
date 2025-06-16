from django.http import JsonResponse
from .slack_utils import slack_client, update_leave_thread
from .leave_utils import update_leave_balance_on_approval
from .approval_utils import create_compensatory_notification_blocks, process_employee_response, create_document_upload_modal
from .models import LeaveRequest
from django.utils import timezone
from slack_sdk.errors import SlackApiError
import logging

logger = logging.getLogger(__name__)

def handle_block_actions(payload):
    """Handle all block action button clicks"""
    try:
        action = payload['actions'][0]
        action_id = action['action_id']
        
        if action_id == 'upload_document':
            return handle_upload_document_action(payload, action)
        elif action_id in ['approve_unpaid', 'approve_compensatory']:
            return handle_compensatory_actions(payload, action, action_id)
        elif action_id in ['employee_accept_unpaid', 'employee_reject_offer', 'employee_accept_comp']:
            return handle_employee_responses(payload, action, action_id)
        elif action_id in ['request_med_cert', 'request_docs']:
            return handle_document_requests(payload, action, action_id)
        elif action_id == 'submit_doc_later':
            return handle_submit_doc_later(payload, action)
        elif action_id == 'cancel_request':
            return handle_cancel_request(payload, action)
        elif action_id in ['verify_document', 'reject_document']:
            return handle_document_verification(payload, action, action_id)
        elif action_id in ['approve_regular', 'reject_leave']:
            return handle_regular_approval(payload, action, action_id)
        
        # Return default response
        return JsonResponse({'status': 'ok'})
        
    except LeaveRequest.DoesNotExist:
        return JsonResponse({'text': 'Leave request not found'}, status=200)
    except Exception as e:
        logger.error(f"Error handling block actions: {e}")
        return JsonResponse({'text': f'Error: {str(e)}'}, status=200)

def handle_upload_document_action(payload, action):
    """Handle document upload button click"""
    leave_id = action['value'].split('|')[0]
    leave_request = LeaveRequest.objects.get(id=leave_id)
    
    # Show upload modal
    slack_client.views_open(
        trigger_id=payload['trigger_id'],
        view=create_document_upload_modal(leave_request)
    )
    return JsonResponse({'text': 'Opening document upload form...'})

def handle_compensatory_actions(payload, action, action_id):
    """Handle unpaid and compensatory leave actions"""
    leave_id = action['value'].split('|')[0]
    leave_request = LeaveRequest.objects.get(id=leave_id)
    
    # Get supervisor comment with fallback
    state_values = payload.get('state', {}).get('values', {})
    comment_input = state_values.get('supervisor_comment', {}).get('comment_input', {})
    comment = comment_input.get('value') if comment_input and comment_input.get('value') else 'No comment provided'
    
    # Create employee notification and get status
    notification_blocks = create_compensatory_notification_blocks(leave_request, action_id, comment)
    status_text = "offered as unpaid leave" if action_id == 'approve_unpaid' else "offered with compensatory work"
    
    # Send to employee via leave_app channel
    try:
        slack_client.chat_postMessage(
            channel='leave_app',
            blocks=notification_blocks,
            text=f"Leave request {status_text}"
        )
    except SlackApiError as channel_error:
        if 'channel_not_found' in str(channel_error):
            # Fallback to user DM if leave_app channel doesn't exist
            slack_client.chat_postMessage(
                channel=leave_request.employee.username,
                blocks=notification_blocks,
                text=f"Leave request {status_text}"
            )
        else:
            raise channel_error
    
    # Update manager view and create thread update
    slack_client.chat_update(
        channel=payload['channel']['id'],
        ts=payload['message']['ts'],
        blocks=[{
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Leave Request Update*\n"
                    f"*Employee:* <@{leave_request.employee.username}>\n"
                    f"*Status:* {status_text.upper()}\n"
                    f"*Waiting for employee response*"
                )
            }
        }]
    )
    
    # Send thread update to manager channel
    if leave_request.thread_ts:
        update_leave_thread(
            leave_request,
            [{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"💡 *Leave Request Update*\n\n"
                        f"*Employee:* <@{leave_request.employee.username}>\n"
                        f"*Action:* Leave {status_text}\n"
                        f"*Manager Comment:* {comment}\n"
                        f"*Status:* Waiting for employee response"
                    )
                }
            }],
            f"Leave {status_text} - waiting for employee response"
        )
    
    return JsonResponse({'status': 'ok'})

def handle_employee_responses(payload, action, action_id):
    """Handle employee responses to compensatory offers"""
    leave_id = action['value'].split('|')[0]
    leave_request = LeaveRequest.objects.get(id=leave_id)
    
    # Process response and create notification
    notification_blocks, status_text = process_employee_response(leave_request, action_id, payload)
    
    # Update thread in manager channel
    if leave_request.thread_ts:
        update_leave_thread(
            leave_request,
            notification_blocks,
            f"Employee response: {status_text}"
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
                        f"✅ *Leave Request Update*\n\n"
                        f"You have {status_text}\n"
                        f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                        f"*Status:* {leave_request.status}"
                    )
                }
            }],
            text=f"Leave request {status_text}"
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
                            f"✅ *Leave Request Update*\n\n"
                            f"You have {status_text}\n"
                            f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                            f"*Status:* {leave_request.status}"
                        )
                    }
                }],
                text=f"Leave request {status_text}"
            )
        else:
            raise channel_error
    
    # Update the original message in the employee's channel to remove buttons
    if payload.get('message') and payload.get('channel'):
        try:
            slack_client.chat_update(
                channel=payload['channel']['id'],
                ts=payload['message']['ts'],
                blocks=[{
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"✅ *Leave Request Update*\n\n"
                            f"You have {status_text}\n"
                            f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                            f"*Status:* {leave_request.status}"
                        )
                    }
                }]
            )
        except SlackApiError as e:
            logger.error(f"Error updating message: {e}")
    
    return JsonResponse({'status': 'ok'})

def handle_document_requests(payload, action, action_id):
    """Handle document request actions"""
    leave_id = action['value'].split('|')[0]
    leave_request = LeaveRequest.objects.get(id=leave_id)
    
    # Get supervisor comment with fallback
    state_values = payload.get('state', {}).get('values', {})
    comment_input = state_values.get('supervisor_comment', {}).get('comment_input', {})
    comment = comment_input.get('value') if comment_input and comment_input.get('value') else 'No comment provided'
    
    # Set document details based on action
    if action_id == 'request_med_cert' or action['value'].split('|')[1] == 'REQUEST_MED_CERT':
        doc_desc = "medical certificate"
        leave_request.document_type = 'Medical Certificate'
        doc_title = "Medical Certificate Required"
    else:  # request_docs or REQUEST_BIRTH_CERT
        doc_desc = "birth certificate"
        leave_request.document_type = 'Birth Certificate'
        doc_title = "Birth Certificate Required"
    
    leave_request.document_status = 'PENDING'
    leave_request.status = 'PENDING_DOCS'
    leave_request.supervisor_comment = comment
    leave_request.save()
    
    # Create document request thread in manager channel
    thread_blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"📄 *Document Request Created*\n\n"
                    f"*Employee:* <@{leave_request.employee.username}>\n"
                    f"*Leave Type:* {leave_request.get_leave_type_display()}\n"
                    f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                    f"*Document Required:* {doc_desc.title()}\n"
                    f"*Manager Comment:* {comment}\n"
                    f"*Status:* Waiting for employee to upload document"
                )
            }
        }
    ]
    
    # Send to thread in manager channel
    if leave_request.thread_ts:
        thread_response = update_leave_thread(
            leave_request,
            thread_blocks,
            f"Document request created for <@{leave_request.employee.username}>"
        )
        # Store the document request thread timestamp for future updates
        if thread_response and thread_response.get('ts'):
            leave_request.document_thread_ts = thread_response['ts']
            leave_request.save()
    
    # Create document request notification with new workflow options
    notification_blocks = [
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
                    f"*Supervisor Comment:* {comment}\n\n"
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
    
    # Send to leave_app channel instead of employee's DM
    try:
        slack_client.chat_postMessage(
            channel='leave_app',
            blocks=notification_blocks,
            text="Document request for leave application"
        )
    except SlackApiError as channel_error:
        if 'channel_not_found' in str(channel_error):
            # Fallback to user DM if leave_app channel doesn't exist
            slack_client.chat_postMessage(
                channel=leave_request.employee.username,
                blocks=notification_blocks,
                text="Document request for leave application"
            )
        else:
            raise channel_error
    
    # Update original message in manager channel
    original_msg = payload['message']
    original_blocks = original_msg['blocks']
    updated_blocks = [original_blocks[0]]  # Keep the first block with leave details
    updated_blocks[0]['text']['text'] += f"\n\n*Current Status:* Documents Requested ({doc_desc})"
    
    slack_client.chat_update(
        channel=payload['channel']['id'],
        ts=original_msg['ts'],
        blocks=updated_blocks,
        text=original_msg['text']
    )
    
    return JsonResponse({'status': 'ok'})

def handle_submit_doc_later(payload, action):
    """Handle submit document later action"""
    leave_id = action['value'].split('|')[0]
    leave_request = LeaveRequest.objects.get(id=leave_id)
    leave_request.status = 'DOCS_PENDING_LATER'
    leave_request.save()
    
    # Update message in leave_app channel to show pending status
    try:
        slack_client.chat_update(
            channel=payload['channel']['id'],
            ts=payload['message']['ts'],
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"⏰ *Document Upload Pending*\n\n"
                            f"*Leave Type:* {leave_request.get_leave_type_display()}\n"
                            f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                            f"*Document Required:* {leave_request.document_type}\n"
                            f"*Status:* PENDING - Will submit later\n\n"
                            f"You can upload the document when ready:"
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
                        }
                    ]
                }
            ]
        )
    except SlackApiError as update_error:
        logger.error(f"Error updating message: {update_error}")
    
    # Notify manager about submit later decision
    if leave_request.thread_ts:
        update_leave_thread(
            leave_request,
            [{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"⏰ *Employee Response: Submit Later*\n\n"
                        f"<@{leave_request.employee.username}> has chosen to submit documents later.\n"
                        f"*Document Required:* {leave_request.document_type}\n"
                        f"*Current Status:* Waiting for document submission"
                    )
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "✓ Approve Without Document"},
                        "style": "primary",
                        "value": f"{leave_request.id}|APPROVE_NO_DOC",
                        "action_id": "approve_regular"
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "✗ Reject Request"},
                        "style": "danger",
                        "value": f"{leave_request.id}|REJECT",
                        "action_id": "reject_leave"
                    }
                ]
            }],
            "Employee chose to submit documents later"
        )
    
    return JsonResponse({'status': 'ok'})

def handle_cancel_request(payload, action):
    """Handle cancel request action"""
    leave_id = action['value'].split('|')[0]
    leave_request = LeaveRequest.objects.get(id=leave_id)
    leave_request.status = 'CANCELLED'
    leave_request.save()
    
    # Update message in current channel
    try:
        slack_client.chat_update(
            channel=payload['channel']['id'],
            ts=payload['message']['ts'],
            blocks=[{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"❌ *Leave Request Cancelled*\n\n"
                        f"You have cancelled your leave request.\n"
                        f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                        f"*Status:* CANCELLED"
                    )
                }
            }]
        )
    except SlackApiError as update_error:
        logger.error(f"Error updating message: {update_error}")
    
    # Notify manager about cancellation
    if leave_request.thread_ts:
        update_leave_thread(
            leave_request,
            [{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"❌ *Leave Request Cancelled*\n\n"
                        f"<@{leave_request.employee.username}> has cancelled their leave request.\n"
                        f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                        f"*Status:* CANCELLED"
                    )
                }
            }],
            "Leave request cancelled by employee"
        )
    
    return JsonResponse({'status': 'ok'})

def handle_document_verification(payload, action, action_id):
    """Handle document verification and rejection"""
    leave_id = action['value'].split('|')[0]
    leave_request = LeaveRequest.objects.get(id=leave_id)
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
    
    # Create final thread message to end the flow
    final_thread_blocks = [
        {
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
                    f"*Reviewer:* <@{payload['user']['id']}>\n"
                    f"*Final Comment:* {comment}\n\n"
                    f"🔒 *This request has been completed and the thread is now closed.*"
                )
            }
        }
    ]
    
    # Send final message to thread in manager channel
    if leave_request.thread_ts:
        update_leave_thread(
            leave_request,
            final_thread_blocks,
            f"FINAL: Document {status_text} - Thread closed"
        )
    
    # Send notification to employee via leave_app channel
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
    
    try:
        slack_client.chat_postMessage(
            channel='leave_app',
            blocks=employee_notification_blocks,
            text=f"Leave request {final_status.lower()} - Final decision"
        )
    except SlackApiError as channel_error:
        if 'channel_not_found' in str(channel_error):
            # Fallback to user DM if leave_app channel doesn't exist
            slack_client.chat_postMessage(
                channel=leave_request.employee.username,
                blocks=employee_notification_blocks,
                text=f"Leave request {final_status.lower()} - Final decision"
            )
        else:
            raise channel_error
    
    return JsonResponse({'status': 'ok'})

def handle_regular_approval(payload, action, action_id):
    """Handle regular approval and rejection actions"""
    leave_id = action['value'].split('|')[0]
    leave_request = LeaveRequest.objects.get(id=leave_id)
    state_values = payload.get('state', {}).get('values', {})
    comment = state_values.get('supervisor_comment', {}).get('comment_input', {}).get('value', 'No comment provided')
    
    if action_id == 'approve_regular':
        leave_request.status = 'APPROVED'
        status_text = "approved"
        emoji = "✅"
        # Update leave balance when approved
        update_leave_balance_on_approval(leave_request)
    else:
        leave_request.status = 'REJECTED'
        status_text = "rejected"
        emoji = "❌"
    
    leave_request.supervisor_comment = comment
    leave_request.save()
    
    # Create notification blocks
    notification_blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"{emoji} *Leave Request {status_text}*\n\n"
                    f"*From:* <@{leave_request.employee.username}>\n"
                    f"*Type:* {leave_request.get_leave_type_display()}\n"
                    f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                    f"*Status:* {status_text.upper()}\n"
                    f"*Comment:* {comment}"
                )
            }
        }
    ]
    
    # Update thread in manager channel
    if leave_request.thread_ts:
        update_leave_thread(
            leave_request,
            notification_blocks,
            f"Leave request {status_text} for <@{leave_request.employee.username}>"
        )
    
    # Send to employee via leave_app channel
    try:
        slack_client.chat_postMessage(
            channel='leave_app',
            blocks=[{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"{emoji} *Leave Request Update*\n\n"
                        f"Your leave request has been {status_text}\n"
                        f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                        f"*Status:* {status_text.upper()}\n"
                        f"*Comment:* {comment}"
                    )
                }
            }],
            text=f"Leave request has been {status_text}"
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
                            f"{emoji} *Leave Request Update*\n\n"
                            f"Your leave request has been {status_text}\n"
                            f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                            f"*Status:* {status_text.upper()}\n"
                            f"*Comment:* {comment}"
                        )
                    }
                }],
                text=f"Leave request has been {status_text}"
            )
        else:
            raise channel_error
    
    return JsonResponse({'status': 'ok'})