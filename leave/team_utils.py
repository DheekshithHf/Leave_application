from django.http import JsonResponse
from .models import Team
from .slack_utils import get_or_create_user, slack_client
from django.db import transaction
from slack_sdk.errors import SlackApiError
import logging
import threading

logger = logging.getLogger(__name__)

def handle_create_team(request):
    """Handle team creation"""
    try:
        text = request.POST.get('text', '').strip()
        if not text:
            return JsonResponse({'text': 'Please specify a team name. Format: /create-team team_name'})
        
        user_id = request.POST.get('user_id')
        team_name = text
        
        # IMMEDIATE RESPONSE - Return success first to avoid timeout
        def create_team_background():
            """Background function to create team"""
            try:
                user = get_or_create_user(user_id)
                
                # Check if team already exists
                if Team.objects.filter(name=team_name).exists():
                    try:
                        slack_client.chat_postMessage(
                            channel=user_id,
                            text=f'❌ Team "{team_name}" already exists.'
                        )
                    except SlackApiError:
                        slack_client.chat_postMessage(
                            channel='leave_app',
                            text=f'❌ <@{user_id}> - Team "{team_name}" already exists.'
                        )
                    return
                
                # Create team and add creator as admin
                with transaction.atomic():
                    team = Team.objects.create(name=team_name)
                    team.members.add(user)
                    team.admins.add(user)
                
                success_message = (
                    f"✅ *Team Created Successfully*\n\n"
                    f"*Team Name:* {team_name}\n"
                    f"*Created By:* <@{user.username}>\n"
                    f"*Role:* Team Admin\n\n"
                    f"Team members can be added using the `/join-team {team_name}` command."
                )
                
                try:
                    slack_client.chat_postMessage(
                        channel=user_id,
                        text=success_message
                    )
                except SlackApiError:
                    slack_client.chat_postMessage(
                        channel='leave_app',
                        text=f'✅ <@{user_id}> - {success_message}'
                    )
                    
            except Exception as e:
                logger.error(f"Background error creating team: {e}")
                try:
                    slack_client.chat_postMessage(
                        channel=user_id,
                        text=f'❌ Error creating team: {str(e)}'
                    )
                except SlackApiError:
                    slack_client.chat_postMessage(
                        channel='leave_app',
                        text=f'❌ <@{user_id}> - Error creating team: {str(e)}'
                    )
        
        # Start background thread
        thread = threading.Thread(target=create_team_background)
        thread.daemon = True
        thread.start()
        
        # Return immediate response
        return JsonResponse({'text': f'⏳ Creating team "{team_name}"...'})
        
    except Exception as e:
        logger.error(f"Error creating team: {e}")
        return JsonResponse({'text': f'Error creating team: {str(e)}'}, status=200)

def handle_view_team(request):
    """Handle viewing team members"""
    try:
        text = request.POST.get('text', '').strip()
        if not text:
            return JsonResponse({'text': 'Please specify which team you want to view. Format: /view-team team_name'})
        
        user_id = request.POST.get('user_id')
        team_name = text
        
        # IMMEDIATE RESPONSE - Return success first to avoid timeout
        def view_team_background():
            """Background function to view team"""
            try:
                try:
                    team = Team.objects.get(name=team_name)
                except Team.DoesNotExist:
                    try:
                        slack_client.chat_postMessage(
                            channel=user_id,
                            text=f'❌ Team "{team_name}" does not exist.'
                        )
                    except SlackApiError:
                        slack_client.chat_postMessage(
                            channel='leave_app',
                            text=f'❌ <@{user_id}> - Team "{team_name}" does not exist.'
                        )
                    return
                
                # Get members and admins
                members = [f"<@{member.username}>" for member in team.members.all()]
                admins = [f"<@{admin.username}>" for admin in team.admins.all()]
                
                team_info = (
                    f"👥 *Team: {team_name}*\n\n"
                    f"*Team Admins:*\n{', '.join(admins)}\n\n"
                    f"*Team Members:*\n{', '.join(members)}"
                )
                
                try:
                    slack_client.chat_postMessage(
                        channel=user_id,
                        text=team_info
                    )
                except SlackApiError:
                    slack_client.chat_postMessage(
                        channel='leave_app',
                        text=f'👥 <@{user_id}> - {team_info}'
                    )
                    
            except Exception as e:
                logger.error(f"Background error viewing team: {e}")
                try:
                    slack_client.chat_postMessage(
                        channel=user_id,
                        text=f'❌ Error viewing team: {str(e)}'
                    )
                except SlackApiError:
                    slack_client.chat_postMessage(
                        channel='leave_app',
                        text=f'❌ <@{user_id}> - Error viewing team: {str(e)}'
                    )
        
        # Start background thread
        thread = threading.Thread(target=view_team_background)
        thread.daemon = True
        thread.start()
        
        # Return immediate response
        return JsonResponse({'text': f'⏳ Loading team "{team_name}" information...'})
        
    except Exception as e:
        logger.error(f"Error viewing team: {e}")
        return JsonResponse({'text': f'Error viewing team: {str(e)}'}, status=200)

def handle_join_team(request):
    """Handle joining an existing team"""
    try:
        text = request.POST.get('text', '').strip()
        if not text:
            return JsonResponse({'text': 'Please specify a team name. Format: /join-team team_name'})
        
        user_id = request.POST.get('user_id')
        team_name = text
        
        # IMMEDIATE RESPONSE - Return success first to avoid timeout
        def join_team_background():
            """Background function to join team"""
            try:
                user = get_or_create_user(user_id)
                
                # Check if team exists
                try:
                    team = Team.objects.get(name=team_name)
                except Team.DoesNotExist:
                    # Send error message
                    try:
                        slack_client.chat_postMessage(
                            channel=user_id,
                            text=f'❌ Team "{team_name}" does not exist. Use /create-team to create it first.'
                        )
                    except SlackApiError:
                        slack_client.chat_postMessage(
                            channel='leave_app',
                            text=f'❌ <@{user_id}> - Team "{team_name}" does not exist.'
                        )
                    return
                
                # Check if user is already a member
                if team.members.filter(id=user.id).exists():
                    try:
                        slack_client.chat_postMessage(
                            channel=user_id,
                            text=f'ℹ️ You are already a member of team "{team_name}".'
                        )
                    except SlackApiError:
                        slack_client.chat_postMessage(
                            channel='leave_app',
                            text=f'ℹ️ <@{user_id}> - Already a member of team "{team_name}".'
                        )
                    return
                
                # Add user to team
                with transaction.atomic():
                    team.members.add(user)
                    team.refresh_from_db()
                    
                    # Verify the user was added
                    if team.members.filter(id=user.id).exists():
                        success_message = f'✅ Successfully joined team "{team_name}"! You are now a team member.'
                        try:
                            slack_client.chat_postMessage(
                                channel=user_id,
                                text=success_message
                            )
                        except SlackApiError:
                            slack_client.chat_postMessage(
                                channel='leave_app',
                                text=f'✅ <@{user_id}> - {success_message}'
                            )
                        logger.info(f"Successfully added user {user.username} to team {team_name}")
                    else:
                        error_message = f'❌ Failed to join team "{team_name}". Please try again.'
                        try:
                            slack_client.chat_postMessage(
                                channel=user_id,
                                text=error_message
                            )
                        except SlackApiError:
                            slack_client.chat_postMessage(
                                channel='leave_app',
                                text=f'❌ <@{user_id}> - {error_message}'
                            )
                        logger.error(f"Failed to add user {user.username} to team {team_name}")
                        
            except Exception as e:
                logger.error(f"Background error joining team: {e}")
                try:
                    slack_client.chat_postMessage(
                        channel=user_id,
                        text=f'❌ Error joining team: {str(e)}'
                    )
                except SlackApiError:
                    slack_client.chat_postMessage(
                        channel='leave_app',
                        text=f'❌ <@{user_id}> - Error joining team: {str(e)}'
                    )
        
        # Start background thread for database operation
        thread = threading.Thread(target=join_team_background)
        thread.daemon = True
        thread.start()
        
        # Return immediate response (within 3 seconds)
        return JsonResponse({'text': f'⏳ Processing request to join team "{team_name}"...'})
        
    except Exception as e:
        logger.error(f"Error joining team: {e}")
        return JsonResponse({'text': f'Error joining team: {str(e)}'}, status=200)

def handle_leave_team(request):
    """Handle leaving a team"""
    try:
        text = request.POST.get('text', '').strip()
        if not text:
            return JsonResponse({'text': 'Please specify a team name. Format: /leave-team team_name'})
        
        user_id = request.POST.get('user_id')
        team_name = text
        
        # IMMEDIATE RESPONSE - Return success first to avoid timeout
        def leave_team_background():
            """Background function to leave team"""
            try:
                user = get_or_create_user(user_id)
                
                # Check if team exists
                try:
                    team = Team.objects.get(name=team_name)
                except Team.DoesNotExist:
                    try:
                        slack_client.chat_postMessage(
                            channel=user_id,
                            text=f'❌ Team "{team_name}" does not exist.'
                        )
                    except SlackApiError:
                        slack_client.chat_postMessage(
                            channel='leave_app',
                            text=f'❌ <@{user_id}> - Team "{team_name}" does not exist.'
                        )
                    return
                
                # Check if user is a member
                if not team.members.filter(id=user.id).exists():
                    try:
                        slack_client.chat_postMessage(
                            channel=user_id,
                            text=f'ℹ️ You are not a member of team "{team_name}".'
                        )
                    except SlackApiError:
                        slack_client.chat_postMessage(
                            channel='leave_app',
                            text=f'ℹ️ <@{user_id}> - Not a member of team "{team_name}".'
                        )
                    return
                
                # Check if user is the original creator (prevent leaving if they're the only admin)
                user_is_admin = team.admins.filter(id=user.id).exists()
                admin_count = team.admins.count()
                
                if user_is_admin and admin_count == 1:
                    error_message = f'❌ You cannot leave team "{team_name}" as you are the only admin. Please assign another admin first or delete the team.'
                    try:
                        slack_client.chat_postMessage(
                            channel=user_id,
                            text=error_message
                        )
                    except SlackApiError:
                        slack_client.chat_postMessage(
                            channel='leave_app',
                            text=f'❌ <@{user_id}> - {error_message}'
                        )
                    return
                
                # Remove user from team (both member and admin if applicable)
                with transaction.atomic():
                    team.members.remove(user)
                    if user_is_admin:
                        team.admins.remove(user)
                
                success_message = (
                    f"✅ *Successfully Left Team*\n\n"
                    f"*Team Name:* {team_name}\n"
                    f"*Former Member:* <@{user.username}>\n"
                    f"*Status:* Left the team\n\n"
                    f"You can rejoin the team anytime using `/join-team {team_name}`"
                )
                
                try:
                    slack_client.chat_postMessage(
                        channel=user_id,
                        text=success_message
                    )
                except SlackApiError:
                    slack_client.chat_postMessage(
                        channel='leave_app',
                        text=f'✅ <@{user_id}> - Successfully left team "{team_name}"'
                    )
                    
            except Exception as e:
                logger.error(f"Background error leaving team: {e}")
                try:
                    slack_client.chat_postMessage(
                        channel=user_id,
                        text=f'❌ Error leaving team: {str(e)}'
                    )
                except SlackApiError:
                    slack_client.chat_postMessage(
                        channel='leave_app',
                        text=f'❌ <@{user_id}> - Error leaving team: {str(e)}'
                    )
        
        # Start background thread
        thread = threading.Thread(target=leave_team_background)
        thread.daemon = True
        thread.start()
        
        # Return immediate response
        return JsonResponse({'text': f'⏳ Processing request to leave team "{team_name}"...'})
        
    except Exception as e:
        logger.error(f"Error leaving team: {e}")
        return JsonResponse({'text': f'Error leaving team: {str(e)}'}, status=200)

def handle_remove_member(request):
    """Handle removing a member from team (admin only)"""
    try:
        text = request.POST.get('text', '').strip()
        if not text:
            return JsonResponse({'text': 'Please specify username and team name. Format: /remove-member @username team_name'})
        
        parts = text.split()
        if len(parts) < 2:
            return JsonResponse({'text': 'Please specify both username and team name. Format: /remove-member @username team_name'})
        
        target_username = parts[0].lstrip('@')
        team_name = ' '.join(parts[1:])  # Support team names with spaces
        admin_user_id = request.POST.get('user_id')
        
        # IMMEDIATE RESPONSE - Return success first to avoid timeout
        def remove_member_background():
            """Background function to remove member"""
            try:
                admin_user = get_or_create_user(admin_user_id)
                
                # Quick validation checks first (these are fast)
                try:
                    team = Team.objects.get(name=team_name)
                except Team.DoesNotExist:
                    error_message = f'❌ Team "{team_name}" does not exist.'
                    try:
                        slack_client.chat_postMessage(
                            channel=admin_user_id,
                            text=error_message
                        )
                    except SlackApiError:
                        slack_client.chat_postMessage(
                            channel='leave_app',
                            text=f'❌ <@{admin_user_id}> - {error_message}'
                        )
                    return
                
                if not team.admins.filter(id=admin_user.id).exists():
                    error_message = f'❌ You are not an admin of team "{team_name}". Only admins can remove members.'
                    try:
                        slack_client.chat_postMessage(
                            channel=admin_user_id,
                            text=error_message
                        )
                    except SlackApiError:
                        slack_client.chat_postMessage(
                            channel='leave_app',
                            text=f'❌ <@{admin_user_id}> - {error_message}'
                        )
                    return
                
                try:
                    target_user = get_or_create_user(target_username)
                except:
                    error_message = f'❌ User @{target_username} not found.'
                    try:
                        slack_client.chat_postMessage(
                            channel=admin_user_id,
                            text=error_message
                        )
                    except SlackApiError:
                        slack_client.chat_postMessage(
                            channel='leave_app',
                            text=f'❌ <@{admin_user_id}> - {error_message}'
                        )
                    return
                
                if not team.members.filter(id=target_user.id).exists():
                    error_message = f'❌ @{target_username} is not a member of team "{team_name}".'
                    try:
                        slack_client.chat_postMessage(
                            channel=admin_user_id,
                            text=error_message
                        )
                    except SlackApiError:
                        slack_client.chat_postMessage(
                            channel='leave_app',
                            text=f'❌ <@{admin_user_id}> - {error_message}'
                        )
                    return
                
                if target_user.id == admin_user.id:
                    error_message = '❌ You cannot remove yourself. Use /leave-team command instead.'
                    try:
                        slack_client.chat_postMessage(
                            channel=admin_user_id,
                            text=error_message
                        )
                    except SlackApiError:
                        slack_client.chat_postMessage(
                            channel='leave_app',
                            text=f'❌ <@{admin_user_id}> - {error_message}'
                        )
                    return
                
                target_is_admin = team.admins.filter(id=target_user.id).exists()
                admin_count = team.admins.count()
                
                if target_is_admin and admin_count == 1:
                    error_message = f'❌ Cannot remove @{target_username} as they are the only admin. Assign another admin first.'
                    try:
                        slack_client.chat_postMessage(
                            channel=admin_user_id,
                            text=error_message
                        )
                    except SlackApiError:
                        slack_client.chat_postMessage(
                            channel='leave_app',
                            text=f'❌ <@{admin_user_id}> - {error_message}'
                        )
                    return
                
                # Background processing for database operations
                with transaction.atomic():
                    team.members.remove(target_user)
                    if target_is_admin:
                        team.admins.remove(target_user)
                    logger.info(f"Successfully removed user {target_username} from team {team_name}")
                
                success_message = f'✅ Successfully removed @{target_username} from team "{team_name}".'
                try:
                    slack_client.chat_postMessage(
                        channel=admin_user_id,
                        text=success_message
                    )
                except SlackApiError:
                    slack_client.chat_postMessage(
                        channel='leave_app',
                        text=f'✅ <@{admin_user_id}> - {success_message}'
                    )
                
            except Exception as e:
                logger.error(f"Background error removing member: {e}")
                try:
                    slack_client.chat_postMessage(
                        channel=admin_user_id,
                        text=f'❌ Error removing member: {str(e)}'
                    )
                except SlackApiError:
                    slack_client.chat_postMessage(
                        channel='leave_app',
                        text=f'❌ <@{admin_user_id}> - Error removing member: {str(e)}'
                    )
        
        # Start background thread
        thread = threading.Thread(target=remove_member_background)
        thread.daemon = True
        thread.start()
        
        # Return immediate response
        return JsonResponse({'text': f'⏳ Processing request to remove @{target_username} from team "{team_name}"...'})
        
    except Exception as e:
        logger.error(f"Error removing member: {e}")
        return JsonResponse({'text': f'Error removing member: {str(e)}'}, status=200)

def handle_admin_role(request):
    """Handle admin role management (add/remove admin privileges)"""
    try:
        text = request.POST.get('text', '').strip()
        if not text:
            return JsonResponse({
                'text': 'Please specify action, username and team name. Format: /admin-role add @username team_name OR /admin-role remove @username team_name'
            })
        
        parts = text.split()
        if len(parts) < 3:
            return JsonResponse({
                'text': 'Please specify action, username and team name. Format: /admin-role add @username team_name OR /admin-role remove @username team_name'
            })
        
        action = parts[0].lower()
        target_username = parts[1].lstrip('@')
        team_name = ' '.join(parts[2:])  # Support team names with spaces
        admin_user_id = request.POST.get('user_id')
        
        if action not in ['add', 'remove']:
            return JsonResponse({'text': 'Action must be either "add" or "remove". Format: /admin-role add @username team_name'})
        
        # IMMEDIATE RESPONSE - Return success first to avoid timeout
        def manage_admin_role_background():
            """Background function to manage admin role"""
            try:
                admin_user = get_or_create_user(admin_user_id)
                
                # Fast validation checks first
                try:
                    team = Team.objects.get(name=team_name)
                except Team.DoesNotExist:
                    error_message = f'❌ Team "{team_name}" does not exist.'
                    try:
                        slack_client.chat_postMessage(
                            channel=admin_user_id,
                            text=error_message
                        )
                    except SlackApiError:
                        slack_client.chat_postMessage(
                            channel='leave_app',
                            text=f'❌ <@{admin_user_id}> - {error_message}'
                        )
                    return
                
                if not team.admins.filter(id=admin_user.id).exists():
                    error_message = f'❌ You are not an admin of team "{team_name}". Only admins can manage admin roles.'
                    try:
                        slack_client.chat_postMessage(
                            channel=admin_user_id,
                            text=error_message
                        )
                    except SlackApiError:
                        slack_client.chat_postMessage(
                            channel='leave_app',
                            text=f'❌ <@{admin_user_id}> - {error_message}'
                        )
                    return
                
                try:
                    target_user = get_or_create_user(target_username)
                except:
                    error_message = f'❌ User @{target_username} not found.'
                    try:
                        slack_client.chat_postMessage(
                            channel=admin_user_id,
                            text=error_message
                        )
                    except SlackApiError:
                        slack_client.chat_postMessage(
                            channel='leave_app',
                            text=f'❌ <@{admin_user_id}> - {error_message}'
                        )
                    return
                
                if not team.members.filter(id=target_user.id).exists():
                    error_message = f'❌ @{target_username} is not a member of team "{team_name}".'
                    try:
                        slack_client.chat_postMessage(
                            channel=admin_user_id,
                            text=error_message
                        )
                    except SlackApiError:
                        slack_client.chat_postMessage(
                            channel='leave_app',
                            text=f'❌ <@{admin_user_id}> - {error_message}'
                        )
                    return
                
                target_is_admin = team.admins.filter(id=target_user.id).exists()
                
                if action == 'add':
                    if target_is_admin:
                        info_message = f'ℹ️ @{target_username} is already an admin of team "{team_name}".'
                        try:
                            slack_client.chat_postMessage(
                                channel=admin_user_id,
                                text=info_message
                            )
                        except SlackApiError:
                            slack_client.chat_postMessage(
                                channel='leave_app',
                                text=f'ℹ️ <@{admin_user_id}> - {info_message}'
                            )
                        return
                    
                    # Add admin role
                    with transaction.atomic():
                        team.admins.add(target_user)
                        logger.info(f"Successfully granted admin role to {target_username} in team {team_name}")
                    
                    success_message = f'✅ Successfully granted admin role to @{target_username} in team "{team_name}".'
                    try:
                        slack_client.chat_postMessage(
                            channel=admin_user_id,
                            text=success_message
                        )
                    except SlackApiError:
                        slack_client.chat_postMessage(
                            channel='leave_app',
                            text=f'✅ <@{admin_user_id}> - {success_message}'
                        )
                
                else:  # action == 'remove'
                    if not target_is_admin:
                        info_message = f'ℹ️ @{target_username} is not an admin of team "{team_name}".'
                        try:
                            slack_client.chat_postMessage(
                                channel=admin_user_id,
                                text=info_message
                            )
                        except SlackApiError:
                            slack_client.chat_postMessage(
                                channel='leave_app',
                                text=f'ℹ️ <@{admin_user_id}> - {info_message}'
                            )
                        return
                    
                    admin_count = team.admins.count()
                    if target_user.id == admin_user.id and admin_count == 1:
                        error_message = '❌ You cannot remove your own admin privileges as you are the only admin.'
                        try:
                            slack_client.chat_postMessage(
                                channel=admin_user_id,
                                text=error_message
                            )
                        except SlackApiError:
                            slack_client.chat_postMessage(
                                channel='leave_app',
                                text=f'❌ <@{admin_user_id}> - {error_message}'
                            )
                        return
                    
                    first_admin = team.admins.first()
                    if target_user.id == first_admin.id and admin_count > 1 and admin_user.id != first_admin.id:
                        error_message = f'❌ Cannot remove admin privileges from @{target_username} as they are the team creator. Only the creator can remove their own privileges.'
                        try:
                            slack_client.chat_postMessage(
                                channel=admin_user_id,
                                text=error_message
                            )
                        except SlackApiError:
                            slack_client.chat_postMessage(
                                channel='leave_app',
                                text=f'❌ <@{admin_user_id}> - {error_message}'
                            )
                        return
                    
                    # Remove admin role
                    with transaction.atomic():
                        team.admins.remove(target_user)
                        logger.info(f"Successfully removed admin role from {target_username} in team {team_name}")
                    
                    success_message = f'✅ Successfully removed admin role from @{target_username} in team "{team_name}".'
                    try:
                        slack_client.chat_postMessage(
                            channel=admin_user_id,
                            text=success_message
                        )
                    except SlackApiError:
                        slack_client.chat_postMessage(
                            channel='leave_app',
                            text=f'✅ <@{admin_user_id}> - {success_message}'
                        )
                        
            except Exception as e:
                logger.error(f"Background error managing admin role: {e}")
                try:
                    slack_client.chat_postMessage(
                        channel=admin_user_id,
                        text=f'❌ Error managing admin role: {str(e)}'
                    )
                except SlackApiError:
                    slack_client.chat_postMessage(
                        channel='leave_app',
                        text=f'❌ <@{admin_user_id}> - Error managing admin role: {str(e)}'
                    )
        
        # Start background thread
        thread = threading.Thread(target=manage_admin_role_background)
        thread.daemon = True
        thread.start()
        
        # Return immediate response
        action_text = "granting" if action == 'add' else "removing"
        return JsonResponse({'text': f'⏳ Processing request for {action_text} admin role...'})
    
    except Exception as e:
        logger.error(f"Error managing admin role: {e}")
        return JsonResponse({'text': f'Error managing admin role: {str(e)}'}, status=200)