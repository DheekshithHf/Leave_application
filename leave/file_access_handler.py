from django.http import JsonResponse
from .slack_utils import slack_client
from .models import LeaveRequest
import logging

logger = logging.getLogger(__name__)

def handle_document_access_request(payload):
    """Simple solution: Ask employee to reshare file to manager"""
    try:
        action_value = payload['actions'][0]['value']
        leave_id = action_value.split('|')[0]
        leave_request = LeaveRequest.objects.get(id=leave_id)
        manager_id = payload['user']['id']
        
        logger.info(f"📄 DOCUMENT ACCESS: Manager {manager_id} requesting document for leave {leave_id}")
        
        # Get file info from leave request
        file_id = None
        file_name = "document"
        if leave_request.document_notes:
            for line in leave_request.document_notes.split('\n'):
                if line.startswith('File ID:'):
                    file_id = line.split(': ')[1].strip()
                elif line.startswith('File Name:'):
                    file_name = line.split(': ', 1)[1].strip()
        
        if not file_id:
            return JsonResponse({
                "response_type": "ephemeral",
                "text": "❌ Could not find document. Please ask employee to resubmit."
            })
        
        try:
            employee_id = leave_request.employee.username
            logger.info(f"📄 Requesting employee {employee_id} to reshare file {file_id} to manager {manager_id}")
            
            # Send automatic reshare request to employee
            employee_message = slack_client.chat_postMessage(
                channel=employee_id,
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"📄 **Document Reshare Request**\n\n"
                                f"Manager <@{manager_id}> needs to access your document for leave approval.\n\n"
                                f"**Leave Details:**\n"
                                f"• Leave Type: {leave_request.leave_type}\n"
                                f"• Duration: {leave_request.start_date} to {leave_request.end_date}\n"
                                f"• Document: `{file_name}`\n"
                                f"• File ID: `{file_id}`\n\n"
                                f"**📱 Quick Action Required:**\n"
                                f"Please find your file `{file_name}` and share it directly to <@{manager_id}>'s DM.\n\n"
                                f"**How to reshare:**\n"
                                f"1. Search for file ID `{file_id}` in Slack\n"
                                f"2. Right-click the file\n"
                                f"3. Select 'Share' or 'Forward'\n"
                                f"4. Send to <@{manager_id}>\n\n"
                                f"⚡ *This ensures the manager can open your document on any device.*"
                            )
                        }
                    }
                ]
            )
            
            if employee_message['ok']:
                logger.info(f"📄 SUCCESS: Reshare request sent to employee")
                
                # Also notify the manager
                manager_response = JsonResponse({
                    "response_type": "ephemeral",
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": (
                                    f"✅ **Document Request Sent**\n\n"
                                    f"I've asked <@{leave_request.employee.username}> to reshare the document directly to your DM.\n\n"
                                    f"**What happens next:**\n"
                                    f"• Employee will share `{file_name}` to your DM\n"
                                    f"• You'll receive a notification when they share it\n"
                                    f"• The file will be clickable and work on any device\n"
                                    f"• No more authentication issues!\n\n"
                                    f"**File Details:**\n"
                                    f"• Name: `{file_name}`\n"
                                    f"• File ID: `{file_id}`\n"
                                    f"• Employee: <@{leave_request.employee.username}>\n"
                                    f"• Leave: {leave_request.leave_type} ({leave_request.start_date} to {leave_request.end_date})\n\n"
                                    f"⏱️ *You should receive the file shortly in your DM.*"
                                )
                            }
                        }
                    ]
                })
                
                # Also send a quick DM to manager with the request status
                try:
                    slack_client.chat_postMessage(
                        channel=manager_id,
                        blocks=[
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": (
                                        f"📄 **Document Reshare in Progress**\n\n"
                                        f"I've asked <@{leave_request.employee.username}> to reshare `{file_name}` directly to your DM.\n\n"
                                        f"**Why this approach works:**\n"
                                        f"• Direct file sharing bypasses authentication issues\n"
                                        f"• Works on web, desktop, and mobile\n"
                                        f"• No more 'Page not found' errors\n\n"
                                        f"**Leave Details:**\n"
                                        f"• Type: {leave_request.leave_type}\n"
                                        f"• Duration: {leave_request.start_date} to {leave_request.end_date}\n"
                                        f"• Employee: <@{leave_request.employee.username}>\n\n"
                                        f"⏳ *Waiting for employee to reshare the file...*"
                                    )
                                }
                            },
                            {
                                "type": "actions",
                                "elements": [
                                    {
                                        "type": "button",
                                        "text": {"type": "plain_text", "text": "✅ Approve Leave", "emoji": True},
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
                    )
                except Exception as e:
                    logger.warning(f"📄 Could not send DM to manager: {e}")
                
                return manager_response
                
            else:
                logger.error(f"📄 Failed to send reshare request: {employee_message.get('error')}")
                return JsonResponse({
                    "response_type": "ephemeral",
                    "text": f"❌ Could not send reshare request to employee: {employee_message.get('error')}"
                })
                
        except Exception as e:
            logger.error(f"📄 Error sending reshare request: {e}")
            return JsonResponse({
                "response_type": "ephemeral",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"⚠️ **Manual Document Access**\n\n"
                                f"Automatic reshare failed. Please access manually:\n\n"
                                f"**File Details:**\n"
                                f"• Name: `{file_name}`\n"
                                f"• File ID: `{file_id}`\n"
                                f"• Employee: <@{leave_request.employee.username}>\n\n"
                                f"**Manual Steps:**\n"
                                f"1. Ask <@{leave_request.employee.username}> to share the file to your DM\n"
                                f"2. Search for file ID `{file_id}` in Slack\n"
                                f"3. Use Slack desktop app for better file access\n\n"
                                f"**Leave Details:**\n"
                                f"• Type: {leave_request.leave_type}\n"
                                f"• Duration: {leave_request.start_date} to {leave_request.end_date}\n\n"
                                f"Error: {str(e)}"
                            )
                        }
                    }
                ]
            })
        
    except Exception as e:
        logger.error(f"📄 CRITICAL ERROR: {e}")
        return JsonResponse({
            "response_type": "ephemeral",
            "text": f"❌ Critical error: {str(e)}"
        })