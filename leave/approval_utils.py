from django.http import JsonResponse
from .models import LeaveRequest
from .slack_utils import get_or_create_user, slack_client, update_leave_thread
from .leave_utils import update_leave_balance_on_approval
from slack_sdk.errors import SlackApiError
import logging

logger = logging.getLogger(__name__)

def create_compensatory_notification_blocks(leave_request, action_id, comment):
    """Create notification blocks for compensatory options"""
    if action_id == 'approve_unpaid':
        status_text = "offered as unpaid leave"
        title = "💰 Unpaid Leave Offer"
        description = "Your leave request has been conditionally approved as **unpaid leave**."
        accept_button = {
            "type": "button",
            "text": {"type": "plain_text", "text": "✓ Accept Unpaid Leave"},
            "style": "primary",
            "value": f"{leave_request.id}|ACCEPT_UNPAID",
            "action_id": "employee_accept_unpaid"
        }
    else:  # approve_compensatory
        status_text = "offered with compensatory work"
        title = "🔄 Compensatory Work Offer"
        description = "Your leave request has been conditionally approved with **compensatory work** required."
        accept_button = {
            "type": "button",
            "text": {"type": "plain_text", "text": "✓ Accept with Compensatory Work"},
            "style": "primary",
            "value": f"{leave_request.id}|ACCEPT_COMP",
            "action_id": "employee_accept_comp"
        }
    
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"{title}\n\n"
                    f"{description}\n\n"
                    f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                    f"*Manager Comment:* {comment}\n\n"
                    "Please choose your response:"
                )
            }
        },
        {
            "type": "actions",
            "elements": [
                accept_button,
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✗ Decline Offer"},
                    "style": "danger",
                    "value": f"{leave_request.id}|REJECT_OFFER",
                    "action_id": "employee_reject_offer"
                }
            ]
        }
    ]

def process_employee_response(leave_request, action_id, payload):
    """Process employee response to compensatory offers"""
    if action_id == 'employee_accept_unpaid':
        leave_request.status = 'APPROVED_UNPAID'
        leave_request.save()
        status_text = "accepted unpaid leave offer"
        
        notification_blocks = [{
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"✅ *Employee Response: Accepted Unpaid Leave*\n\n"
                    f"<@{leave_request.employee.username}> has accepted the unpaid leave offer.\n"
                    f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                    f"*Final Status:* APPROVED AS UNPAID LEAVE"
                )
            }
        }]
        
    elif action_id == 'employee_accept_comp':
        leave_request.status = 'APPROVED_COMPENSATORY'
        leave_request.save()
        status_text = "accepted compensatory work offer"
        
        notification_blocks = [{
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"✅ *Employee Response: Accepted Compensatory Work*\n\n"
                    f"<@{leave_request.employee.username}> has accepted the compensatory work arrangement.\n"
                    f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                    f"*Final Status:* APPROVED WITH COMPENSATORY WORK"
                )
            }
        }]
        
    else:  # employee_reject_offer
        leave_request.status = 'REJECTED'
        leave_request.save()
        status_text = "declined the offer"
        
        notification_blocks = [{
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"❌ *Employee Response: Declined Offer*\n\n"
                    f"<@{leave_request.employee.username}> has declined the compensatory offer.\n"
                    f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                    f"*Final Status:* REJECTED"
                )
            }
        }]
    
    return notification_blocks, status_text

def create_document_upload_modal(leave_request):
    """Create document upload modal"""
    return {
        "type": "modal",
        "callback_id": "document_upload_modal",
        "title": {"type": "plain_text", "text": "Submit Documents"},
        "submit": {"type": "plain_text", "text": "Submit Documents"},
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "📎 Document Upload",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Document Required:* {leave_request.document_type}\n"
                        f"*Leave Period:* {leave_request.start_date} to {leave_request.end_date}\n\n"
                        "_Please upload the required document in one of these formats: PDF, DOC, DOCX, JPG, JPEG, or PNG_"
                    )
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "input",
                "block_id": "document_upload",
                "element": {
                    "type": "file_input",
                    "action_id": "file_upload",
                    "filetypes": ["pdf", "doc", "docx", "jpg", "jpeg", "png"],
                    "max_files": 1
                },
                "label": {"type": "plain_text", "text": "Select Document", "emoji": True}
            },
            {
                "type": "input",
                "block_id": "document_notes",
                "optional": True,
                "element": {
                    "type": "plain_text_input",
                    "action_id": "notes_input",
                    "multiline": True,
                    "placeholder": {"type": "plain_text", "text": "Add any additional notes or comments about the document"}
                },
                "label": {"type": "plain_text", "text": "Additional Notes", "emoji": True}
            }
        ],
        "private_metadata": str(leave_request.id)
    }