from slack_sdk.web.client import WebClient
from slack_sdk.errors import SlackApiError
from django.contrib.auth.models import User
from .models import UserRole
import logging
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

SLACK_BOT_TOKEN = os.getenv('SLACK_BOT_TOKEN')
SLACK_MANAGER_CHANNEL = os.getenv('SLACK_MANAGER_CHANNEL', '#leave-approvals')
slack_client = WebClient(
    token=SLACK_BOT_TOKEN,
    timeout=30
)

def check_manager_status(user_id):
    """Check if user is in manager channel"""
    try:
        # First try to get channel ID
        try:
            channel_info = slack_client.conversations_info(channel=SLACK_MANAGER_CHANNEL.lstrip('#'))
            channel_id = channel_info['channel']['id']
        except SlackApiError:
            # If channel not found by name, list all channels and find it
            channels = slack_client.conversations_list(types="public_channel,private_channel")
            channel_id = None
            for channel in channels['channels']:
                if channel['name'] == SLACK_MANAGER_CHANNEL.lstrip('#'):
                    channel_id = channel['id']
                    break
            if not channel_id:
                logger.error("Could not find manager channel")
                return False

        # Get channel members using the channel ID
        response = slack_client.conversations_members(channel=channel_id)
        channel_members = response['members']
        return user_id in channel_members
    except SlackApiError as e:
        logger.error(f"Error checking channel membership: {e}")
        return False

# def get_or_create_user(slack_user_id, is_manager=None):
#     """Get or create user with role management"""
#     try:
#         user = User.objects.get(username=slack_user_id)
#         # Update role based on channel membership
#         is_manager_status = check_manager_status(slack_user_id) if is_manager is None else is_manager
#         role, created = UserRole.objects.get_or_create(
#             user=user,
#             defaults={'role': 'MANAGER' if is_manager_status else 'EMPLOYEE'}
#         )
#         if role.role == 'MANAGER' and not is_manager_status:
#             role.role = 'EMPLOYEE'
#             role.save()
#         elif role.role == 'EMPLOYEE' and is_manager_status:
#             role.role = 'MANAGER'
#             role.save()
#     except User.DoesNotExist:
#         # Get user info from Slack
#         try:
#             user_info = slack_client.users_info(user=slack_user_id)
#             name = user_info['user']['profile'].get('real_name', slack_user_id)
#             email = user_info['user']['profile'].get('email', f"{slack_user_id}@example.com")
            
#             # Create Django user
#             user = User.objects.create_user(
#                 username=slack_user_id,
#                 email=email,
#                 first_name=name.split()[0] if ' ' in name else name
#             )
#             # Create user role based on channel membership
#             is_manager_status = check_manager_status(slack_user_id) if is_manager is None else is_manager
#             UserRole.objects.create(
#                 user=user,
#                 role='MANAGER' if is_manager_status else 'EMPLOYEE'
#             )
#         except SlackApiError:
#             # Fallback to creating user with just slack_user_id
#             user = User.objects.create_user(
#                 username=slack_user_id,
#                 email=f"{slack_user_id}@example.com"
#             )
#             UserRole.objects.create(user=user, role='EMPLOYEE')
#     return user


def get_or_create_user(slack_user_id, is_manager=None):
    """Get or create user with role management - FIXED TO ONLY USE SLACK USER IDS"""
    
    # CRITICAL: Validate that we have a proper Slack user ID
    if not slack_user_id or not slack_user_id.startswith('U') or len(slack_user_id) != 11:
        logger.error(f"Invalid Slack user ID format: {slack_user_id}")
        raise ValueError(f"Invalid Slack user ID: {slack_user_id}")
    
    try:
        user = User.objects.get(username=slack_user_id)
        logger.info(f"Found existing user: {user.username}")
        
        # Only update role if explicitly specified
        if is_manager is not None:
            from .models import UserRole
            user_role, created = UserRole.objects.get_or_create(
                user=user,
                defaults={'role': 'EMPLOYEE', 'is_admin': False}
            )
            
            if is_manager and user_role.role != 'MANAGER':
                user_role.role = 'MANAGER'
                user_role.is_admin = True
                user_role.save()
                logger.info(f"Updated {slack_user_id} to MANAGER")
            elif not is_manager and user_role.role != 'EMPLOYEE':
                user_role.role = 'EMPLOYEE'
                user_role.is_admin = False
                user_role.save()
                logger.info(f"Updated {slack_user_id} to EMPLOYEE")
        
        return user
        
    except User.DoesNotExist:
        logger.info(f"Creating new user for Slack ID: {slack_user_id}")
        
        # Get user info from Slack to get proper name and email
        try:
            user_info = slack_client.users_info(user=slack_user_id)
            profile = user_info['user']['profile']
            name = profile.get('real_name', profile.get('display_name', slack_user_id))
            email = profile.get('email', f"{slack_user_id}@company.com")
            
            logger.info(f"Got Slack user info: {name}, {email}")
            
        except SlackApiError as e:
            logger.warning(f"Could not get Slack user info for {slack_user_id}: {e}")
            name = slack_user_id
            email = f"{slack_user_id}@company.com"
        
        # Create Django user with SLACK USER ID as username
        user = User.objects.create_user(
            username=slack_user_id,  # ALWAYS use Slack user ID
            email=email,
            first_name=name.split()[0] if ' ' in name else name,
            last_name=' '.join(name.split()[1:]) if ' ' in name else ''
        )
        
        # Create user role
        from .models import UserRole
        UserRole.objects.create(
            user=user,
            role='MANAGER' if is_manager else 'EMPLOYEE',
            is_admin=bool(is_manager)
        )
        
        logger.info(f"Created new user: {slack_user_id} with role: {'MANAGER' if is_manager else 'EMPLOYEE'}")
        return user

def is_manager(user_id):
    """
    Check if user is a manager - ENHANCED to include assigned managers
    
    Returns True if:
    1. User is in the managers channel
    2. User has manager role in UserRole model
    3. User is admin of any team
    """
    try:
        # Method 1: Check if user is in managers channel
        # if is_in_manager_channel(user_id):
        #     return True
        
        # # Method 2: Check UserRole model for manager role - ENHANCED
        try:
            user = get_or_create_user(user_id)
            from .models import UserRole
            
            # Check if user has manager role assigned
            user_role = UserRole.objects.filter(user=user).first()
            if user_role and user_role.role == 'MANAGER':
                logger.info(f"USER {user_id} is manager via UserRole: {user_role.role}")
                return True
            
            # Check if user is admin flag is set
            if user_role and user_role.is_admin:
                logger.info(f"USER {user_id} is manager via admin flag: {user_role.is_admin}")
                return True
                
        except Exception as role_error:
            logger.warning(f"Error checking UserRole for manager status: {role_error}")
        
        # # Method 3: Check if user is admin of any team
        # try:
        #     from .models import Team
        #     user = get_or_create_user(user_id)
        #     teams_as_admin = Team.objects.filter(admins=user)
        #     if teams_as_admin.exists():
        #         logger.info(f"USER {user_id} is manager via team admin: {teams_as_admin.count()} teams")
        #         return True
        # except Exception as team_error:
        #     logger.warning(f"Error checking team admin status: {team_error}")
        
        # logger.info(f"USER {user_id} is NOT a manager")
        # return False
        
    except Exception as e:
        logger.error(f"Error checking manager status for {user_id}: {e}")
        return False

def is_in_manager_channel(channel_id):
    """Check if the current channel is the leave-approvals channel"""
    try:
        # Get the leave-approvals channel ID
        try:
            channel_info = slack_client.conversations_info(channel=SLACK_MANAGER_CHANNEL.lstrip('#'))
            manager_channel_id = channel_info['channel']['id']
       
        except SlackApiError:
            # Try getting channel list and find the channel
            channels = slack_client.conversations_list(types="public_channel,private_channel")
            manager_channel_id = None
            for channel in channels['channels']:
                if channel['name'] == SLACK_MANAGER_CHANNEL.lstrip('#'):
                    manager_channel_id = channel['id']
                    break
            if not manager_channel_id:
                logger.error("Could not find leave-approvals channel")
                return False
        
        return channel_id == manager_channel_id
    except SlackApiError as e:
        logger.error(f"Error checking channel: {e}")
        return False

def send_slack_message(channel, blocks, fallback_text=""):
    """Send message to Slack channel"""
    try:
        # Replace test-bot with test_bot if that's the target channel
        if channel == 'test-bot':
            channel = 'test_bot'
            
        return slack_client.chat_postMessage(
            channel=channel,
            blocks=blocks,
            text=fallback_text
        )
    except SlackApiError as e:
        logger.error(f"Error sending message to channel {channel}: {e}")
        if 'channel_not_found' in str(e):
            logger.error(f"Channel {channel} not found. Please check channel name/ID")
        return None

def send_personal_notification(user_id, blocks, text=None):
    """Helper function to send notifications to user's DM"""
    try:
        return slack_client.chat_postMessage(
            channel=user_id,
            blocks=blocks,
            text=text or "Leave notification"
        )
    except SlackApiError as e:
        logger.error(f"Error sending DM to user {user_id}: {e}")
        return None

def send_manager_notification(blocks, text=None):
    """Helper function to send notifications to manager channel"""
    try:
        return slack_client.chat_postMessage(
            channel=SLACK_MANAGER_CHANNEL.lstrip('#'),
            blocks=blocks,
            text=text or "Leave notification"
        )
    except SlackApiError as e:
        logger.error(f"Error sending to manager channel: {e}")
        return None

def start_leave_request_thread(user, leave_request, blocks):
    """Start a new thread for leave request in manager channel"""
    try:
        # Send initial message to create thread
        response = slack_client.chat_postMessage(
            channel=SLACK_MANAGER_CHANNEL.lstrip('#'),
            blocks=blocks,
            text=f"New leave request from <@{user.username}>"
        )
        
        # Store thread_ts in leave_request for future reference
        if response and response['ts']:
            leave_request.thread_ts = response['ts']
            leave_request.save()
            
        return response
    except SlackApiError as e:
        logger.error(f"Error creating thread: {e}")
        return None

def update_leave_thread(leave_request, blocks, text=None):
    """Update existing leave request thread"""
    try:
        if not leave_request.thread_ts:
            return None
            
        return slack_client.chat_postMessage(
            channel=SLACK_MANAGER_CHANNEL.lstrip('#'),
            thread_ts=leave_request.thread_ts,
            blocks=blocks,
            text=text or "Leave request update"
        )
    except SlackApiError as e:
        logger.error(f"Error updating thread: {e}")
        return None

def send_employee_notification(leave_request, blocks, text_summary, notification_type="employee_update"):
    """Send threaded notification to the employee"""
    try:
        employee_id = leave_request.employee.username
        
        # Always send to employee's DM, with thread if available
        response = slack_client.chat_postMessage(
            channel=employee_id,
            blocks=blocks,
            text=text_summary,
            thread_ts=leave_request.employee_thread_ts if leave_request.employee_thread_ts else None,
            metadata={
                "event_type": f"leave_{notification_type}",
                "event_payload": {
                    "leave_id": str(leave_request.id),
                    "employee_id": employee_id,
                    "notification_type": notification_type
                }
            }
        )
        
        if response['ok']:
            # If this is the first message and no employee_thread_ts exists, store it
            if not leave_request.employee_thread_ts:
                leave_request.employee_thread_ts = response['ts']
                leave_request.save()
            logger.info(f"Employee notification sent to {employee_id}, employee_thread_ts: {leave_request.employee_thread_ts}")
            return True
        else:
            logger.error(f"Failed to send employee notification: {response}")
            return False
            
    except SlackApiError as e:
        logger.error(f"Error sending employee notification: {e}")
        return False

def start_employee_leave_thread(leave_request, blocks, text_summary):
    """Start a new thread for employee leave notifications"""
    try:
        employee_id = leave_request.employee.username
        
        # Send initial message to create employee thread
        response = slack_client.chat_postMessage(
            channel=employee_id,
            blocks=blocks,
            text=text_summary,
            metadata={
                "event_type": "leave_request_employee",
                "event_payload": {
                    "leave_id": str(leave_request.id),
                    "employee_id": employee_id,
                    "notification_type": "initial_confirmation"
                }
            }
        )
        
        # Store employee_thread_ts in leave_request for future reference
        if response and response['ts']:
            leave_request.employee_thread_ts = response['ts']
            leave_request.save()
            logger.info(f"Employee thread created for leave {leave_request.id}, thread_ts: {response['ts']}")
            
        return response
    except SlackApiError as e:
        logger.error(f"Error creating employee thread: {e}")
        return None

# def send_manager_update_notification(leave_request, blocks, text_summary, exclude_manager_id=None, notification_type="manager_update"):
#     """Send threaded notifications to managers (excluding the one who took action)"""
#     try:
#         selected_managers = leave_request.get_selected_managers_list()
#         if not selected_managers:
#             logger.warning(f"No selected managers found for leave request {leave_request.id}")
#             return []
        
#         # Exclude the manager who took the action to avoid self-notification
#         managers_to_notify = [m for m in selected_managers if m != exclude_manager_id] if exclude_manager_id else selected_managers
        
#         if not managers_to_notify:
#             logger.info(f"No managers to notify after excluding {exclude_manager_id}")
#             return []
        
#         notification_results = []
        
#         for manager_id in managers_to_notify:
#             try:
#                 # Send threaded message to each manager's DM
#                 response = slack_client.chat_postMessage(
#                     channel=manager_id,
#                     blocks=blocks,
#                     text=text_summary,
#                     thread_ts=leave_request.thread_ts if leave_request.thread_ts else None,
#                     metadata={
#                         "event_type": f"leave_{notification_type}",
#                         "event_payload": {
#                             "leave_id": str(leave_request.id),
#                             "employee_id": leave_request.employee.username,
#                             "manager_id": manager_id,
#                             "notification_type": notification_type
#                         }
#                     }
#                 )
                
#                 if response['ok']:
#                     notification_results.append({
#                         'manager': manager_id,
#                         'success': True,
#                         'ts': response['ts']
#                     })
#                     logger.info(f"Manager update sent to {manager_id}, thread_ts: {leave_request.thread_ts}")
#                 else:
#                     notification_results.append({
#                         'manager': manager_id,
#                         'success': False,
#                         'error': 'Slack API returned not ok'
#                     })
                    
#             except SlackApiError as e:
#                 logger.error(f"Error sending manager update to {manager_id}: {e}")
#                 notification_results.append({
#                     'manager': manager_id,
#                     'success': False,
#                     'error': str(e)
#                 })
        
#         return notification_results
        
#     except Exception as e:
#         logger.error(f"Error in send_manager_update_notification: {e}")
#         return []

def send_manager_update_notification(leave_request, blocks, text_summary, exclude_manager_id=None, notification_type="manager_update"):
    """Send threaded notifications to managers (excluding the one who took action)"""
    try:
        selected_managers = leave_request.get_selected_managers_list()
        if not selected_managers:
            logger.warning(f"No selected managers found for leave request {leave_request.id}")
            return []
        
        # Exclude the manager who took the action to avoid self-notification
        managers_to_notify = [m for m in selected_managers if m != exclude_manager_id] if exclude_manager_id else selected_managers
        
        if not managers_to_notify:
            logger.info(f"No managers to notify after excluding {exclude_manager_id}")
            return []
        
        notification_results = []
        
        for manager_id in managers_to_notify:
            try:

                manager_thread_ts = leave_request.get_manager_thread(manager_id)
                logger.info(f"Sending to manager {manager_id} with thread_ts: {manager_thread_ts}")

                if not manager_thread_ts:
                    # Fallback: use main thread_ts but this shouldn't happen in normal flow
                    manager_thread_ts = leave_request.thread_ts
                    logger.warning(f"No specific thread found for manager {manager_id}, using main thread {manager_thread_ts}")
                # Send threaded message to each manager's DM
                response = slack_client.chat_postMessage(
                    channel=manager_id,
                    blocks=blocks,
                    text=text_summary,
                    thread_ts=manager_thread_ts,
                    metadata={
                        "event_type": f"leave_{notification_type}",
                        "event_payload": {
                            "leave_id": str(leave_request.id),
                            "employee_id": leave_request.employee.username,
                            "manager_id": manager_id,
                            "notification_type": notification_type
                        }
                    }
                )
                
                if response['ok']:
                    notification_results.append({
                        'manager': manager_id,
                        'success': True,
                        'ts': response['ts']
                    })
                    logger.info(f"Manager update sent to {manager_id}, thread_ts: {manager_thread_ts}")
                else:
                    notification_results.append({
                        'manager': manager_id,
                        'success': False,
                        'error': 'Slack API returned not ok'
                    })
                    
            except SlackApiError as e:
                logger.error(f"Error sending manager update to {manager_id}: {e}")
                notification_results.append({
                    'manager': manager_id,
                    'success': False,
                    'error': str(e)
                })
        
        return notification_results
        
    except Exception as e:
        logger.error(f"Error in send_manager_update_notification: {e}")
        return []

def send_leave_request_to_managers(selected_managers, leave_request, leave_blocks):
    """Send leave request notifications to selected managers via their DMs with thread creation"""
    try:
        notification_results = {
            'sent': [],
            'failed': [],
            'total_sent': 0,
            'total_failed': 0
        }
        
        for manager_id in selected_managers:
            try:
                # Send initial message to manager's DM
                response = slack_client.chat_postMessage(
                    channel=manager_id,
                    blocks=leave_blocks,
                    text=f"New leave request from <@{leave_request.employee.username}>",
                    metadata={
                        "event_type": "leave_request_new",
                        "event_payload": {
                            "leave_id": str(leave_request.id),
                            "employee_id": leave_request.employee.username,
                            "manager_id": manager_id
                        }
                    }
                )
                
                if response['ok']:
                    # Store the thread_ts from the first successful manager notification
                    if not leave_request.thread_ts:
                        leave_request.thread_ts = response['ts']
                        leave_request.save()
                    leave_request.set_manager_thread(manager_id, response['ts'])
                    notification_results['sent'].append({
                        'manager': manager_id,
                        'ts': response['ts'],
                        'channel': response['channel']
                    })
                    notification_results['total_sent'] += 1
                    logger.info(f"Leave request sent to manager {manager_id}, ts: {response['ts']}")
                else:
                    notification_results['failed'].append({
                        'manager': manager_id,
                        'error': 'Slack API returned not ok'
                    })
                    notification_results['total_failed'] += 1
                    
            except SlackApiError as e:
                logger.error(f"Error sending to manager {manager_id}: {e}")
                notification_results['failed'].append({
                    'manager': manager_id,
                    'error': str(e)
                })
                notification_results['total_failed'] += 1
        
        return notification_results
        
    except Exception as e:
        logger.error(f"Error in send_leave_request_to_managers: {e}")
        return {
            'sent': [],
            'failed': [{'manager': 'all', 'error': str(e)}],
            'total_sent': 0,
            'total_failed': len(selected_managers)
        }


# Add this function to your existing slack_utils.py - don't modify existing functions

def send_document_directly_to_managers(leave_request, file_id, file_name, doc_notes):
    """Send document directly to all managers via DM - separate from main notification"""
    try:
        # Get all managers
        managers = User.objects.filter(
            userrole__role__in=['MANAGER', 'ADMIN']
        ).distinct()
        
        for manager in managers:
            try:
                # Share file directly to each manager's DM
                share_response = slack_client.files_share(
                    file=file_id,
                    channels=manager.username  # This is the Slack user ID
                )
                
                if share_response['ok']:
                    # Send a separate message explaining the document
                    explanation_blocks = [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": (
                                    f"📄 *Document shared above for leave request*\n\n"
                                    f"*Employee:* <@{leave_request.employee.username}>\n"
                                    f"*Leave Type:* {leave_request.leave_type}\n"
                                    f"*Duration:* {leave_request.start_date} to {leave_request.end_date}\n"
                                    f"*Document Type:* {leave_request.document_type}\n"
                                    f"*File Name:* {file_name}\n"
                                    f"*Employee Notes:* {doc_notes or 'No notes provided'}\n\n"
                                    f"👆 *The document file is shared above - click on it to open*"
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
                    
                    slack_client.chat_postMessage(
                        channel=manager.username,
                        blocks=explanation_blocks,
                        text=f"Document for {leave_request.employee.username}'s leave request"
                    )
                    
                    logger.info(f"Document shared directly to manager {manager.username}")
                    
            except Exception as e:
                logger.error(f"Failed to share document to manager {manager.username}: {e}")
                
    except Exception as e:
        logger.error(f"Error in send_document_directly_to_managers: {e}")