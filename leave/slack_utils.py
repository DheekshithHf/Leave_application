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

def get_or_create_user(slack_user_id, is_manager=None):
    """Get or create user with role management"""
    try:
        user = User.objects.get(username=slack_user_id)
        # Update role based on channel membership
        is_manager_status = check_manager_status(slack_user_id) if is_manager is None else is_manager
        role, created = UserRole.objects.get_or_create(
            user=user,
            defaults={'role': 'MANAGER' if is_manager_status else 'EMPLOYEE'}
        )
        if role.role == 'MANAGER' and not is_manager_status:
            role.role = 'EMPLOYEE'
            role.save()
        elif role.role == 'EMPLOYEE' and is_manager_status:
            role.role = 'MANAGER'
            role.save()
    except User.DoesNotExist:
        # Get user info from Slack
        try:
            user_info = slack_client.users_info(user=slack_user_id)
            name = user_info['user']['profile'].get('real_name', slack_user_id)
            email = user_info['user']['profile'].get('email', f"{slack_user_id}@example.com")
            
            # Create Django user
            user = User.objects.create_user(
                username=slack_user_id,
                email=email,
                first_name=name.split()[0] if ' ' in name else name
            )
            # Create user role based on channel membership
            is_manager_status = check_manager_status(slack_user_id) if is_manager is None else is_manager
            UserRole.objects.create(
                user=user,
                role='MANAGER' if is_manager_status else 'EMPLOYEE'
            )
        except SlackApiError:
            # Fallback to creating user with just slack_user_id
            user = User.objects.create_user(
                username=slack_user_id,
                email=f"{slack_user_id}@example.com"
            )
            UserRole.objects.create(user=user, role='EMPLOYEE')
    return user

def is_manager(user_id):
    """Check if user is a manager"""
    try:
        # Get channel ID first
        try:
            channel_info = slack_client.conversations_info(channel=SLACK_MANAGER_CHANNEL.lstrip('#'))
            channel_id = channel_info['channel']['id']
        except SlackApiError:
            # Try getting channel list and find the channel
            channels = slack_client.conversations_list(types="private_channel")
            channel_id = None
            for channel in channels['channels']:
                if channel['name'] == SLACK_MANAGER_CHANNEL.lstrip('#'):
                    channel_id = channel['id']
                    break
            if not channel_id:
                logger.error("Could not find leave-approvals channel")
                return False

        # Get channel members using the channel ID
        response = slack_client.conversations_members(channel=channel_id)
        channel_members = response['members']
        return user_id in channel_members
    except SlackApiError as e:
        logger.error(f"Error checking channel membership: {e}")
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