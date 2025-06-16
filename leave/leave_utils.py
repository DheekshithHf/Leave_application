from django.contrib.auth.models import User
from django.db.models import Q
from .models import LeaveRequest, LeaveBalance, LeavePolicy, UserRole, Department
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

def get_maternity_leave_info(user):
    """Get maternity leave information for a user"""
    try:
        # Count previous maternity leaves
        maternity_count = LeaveRequest.objects.filter(
            employee=user,
            leave_type='MATERNITY',
            status__in=['APPROVED', 'APPROVED_UNPAID', 'APPROVED_COMPENSATORY']
        ).count()
        
        # Determine available days based on count
        if maternity_count == 0:
            available_days = 182  # 26 weeks for first time
            status_text = "First Maternity Leave"
        elif maternity_count == 1:
            available_days = 182  # 26 weeks for second time
            status_text = "Second Maternity Leave"
        else:
            available_days = 84   # 12 weeks for third time onwards
            status_text = f"Maternity Leave #{maternity_count + 1} (3rd+ time)"
        
        return {
            'count': maternity_count,
            'available_days': available_days,
            'status_text': status_text
        }
    except Exception as e:
        logger.error(f"Error getting maternity leave info: {e}")
        return {
            'count': 0,
            'available_days': 182,
            'status_text': "First Maternity Leave"
        }

def get_paternity_leave_info(user):
    """Get paternity leave information for a user"""
    try:
        # Count previous paternity leaves
        paternity_count = LeaveRequest.objects.filter(
            employee=user,
            leave_type='PATERNITY',
            status__in=['APPROVED', 'APPROVED_UNPAID', 'APPROVED_COMPENSATORY']
        ).count()
        
        # Paternity leave is 16 days per birth
        available_days = 16
        status_text = f"Paternity Leave #{paternity_count + 1}" if paternity_count > 0 else "First Paternity Leave"
        
        return {
            'count': paternity_count,
            'available_days': available_days,
            'status_text': status_text
        }
    except Exception as e:
        logger.error(f"Error getting paternity leave info: {e}")
        return {
            'count': 0,
            'available_days': 16,
            'status_text': "First Paternity Leave"
        }

def get_leave_balance(slack_user_id):
    """Get leave balance for a user"""
    from .slack_utils import get_or_create_user
    
    user = get_or_create_user(slack_user_id)
    balance = LeaveBalance.objects.get_or_create(user=user)[0]
    balance.reset_monthly_balance()
    
    # Safely get used days
    casual_used = int(getattr(balance, 'casual_used', 0))
    casual_remaining = int(balance.get_remaining_days('CASUAL'))
    sick_used = int(getattr(balance, 'sick_used', 0))
    sick_remaining = int(balance.get_remaining_days('SICK'))
    
    # Get dynamic maternity and paternity leave info
    maternity_info = get_maternity_leave_info(user)
    paternity_info = get_paternity_leave_info(user)
    
    leave_balances = {
        'casual': {'used': casual_used, 'remaining': casual_remaining},
        'sick': {'used': sick_used, 'remaining': sick_remaining},
        'maternity': {
            'used': maternity_info['count'], 
            'remaining': maternity_info['available_days'],
            'status': maternity_info['status_text']
        },
        'paternity': {
            'used': paternity_info['count'], 
            'remaining': paternity_info['available_days'],
            'status': paternity_info['status_text']
        }
    }
    
    return leave_balances

def update_leave_balance_on_approval(leave_request):
    """Update leave balance when a leave request is approved"""
    try:
        balance, created = LeaveBalance.objects.get_or_create(user=leave_request.employee)
        
        if leave_request.leave_type == 'CASUAL':
            balance.casual_used += (leave_request.end_date - leave_request.start_date).days + 1
        elif leave_request.leave_type == 'SICK':
            balance.sick_used += (leave_request.end_date - leave_request.start_date).days + 1
        
        balance.save()
        logger.info(f"Updated leave balance for {leave_request.employee.username}")
    except Exception as e:
        logger.error(f"Error updating leave balance: {e}")

def get_conflicts_details(start_date, end_date, exclude_user=None):
    """Get detailed conflicts with employee names, departments, and date ranges"""
    conflicts = LeaveRequest.objects.filter(
        Q(start_date__lte=end_date) & Q(end_date__gte=start_date),
        status__in=['APPROVED', 'PENDING']
    )
    if exclude_user:
        conflicts = conflicts.exclude(employee=exclude_user)
    
    approved_leaves = conflicts.filter(status='APPROVED')
    pending_leaves = conflicts.filter(status='PENDING')
    
    # Format approved leaves with detailed info
    approved_details = []
    for leave in approved_leaves:
        user_role = UserRole.objects.filter(user=leave.employee).first()
        department_name = user_role.department.name if user_role and user_role.department else 'No Department'
        
        # Format date range
        if leave.start_date == leave.end_date:
            date_str = leave.start_date.strftime('%Y-%m-%d')
        else:
            date_str = f"{leave.start_date.strftime('%Y-%m-%d')} to {leave.end_date.strftime('%Y-%m-%d')}"
        
        approved_details.append(f"<@{leave.employee.username}> - {department_name} - {date_str}")
    
    # Format pending leaves with detailed info
    pending_details = []
    for leave in pending_leaves:
        user_role = UserRole.objects.filter(user=leave.employee).first()
        department_name = user_role.department.name if user_role and user_role.department else 'No Department'
        
        # Format date range
        if leave.start_date == leave.end_date:
            date_str = leave.start_date.strftime('%Y-%m-%d')
        else:
            date_str = f"{leave.start_date.strftime('%Y-%m-%d')} to {leave.end_date.strftime('%Y-%m-%d')}"
        
        pending_details.append(f"<@{leave.employee.username}> - {department_name} - {date_str}")
    
    return {
        'approved_count': len(approved_details),
        'pending_count': len(pending_details),
        'approved_details': approved_details,
        'pending_details': pending_details,
        'approved_names': [f"<@{leave.employee.username}>" for leave in approved_leaves],
        'pending_names': [f"<@{leave.employee.username}>" for leave in pending_leaves]
    }

def get_department_conflicts(start_date, end_date, department, exclude_user=None):
    """Get detailed department conflicts with employee names and date ranges"""
    conflicts = LeaveRequest.objects.filter(
        Q(start_date__lte=end_date) & Q(end_date__gte=start_date),
        status__in=['APPROVED', 'PENDING'],
        employee__userrole__department=department
    )
    if exclude_user:
        conflicts = conflicts.exclude(employee=exclude_user)
    
    approved_leaves = conflicts.filter(status='APPROVED')
    pending_leaves = conflicts.filter(status='PENDING')
    
    # Format approved leaves with detailed info
    approved_details = []
    for leave in approved_leaves:
        # Format date range
        if leave.start_date == leave.end_date:
            date_str = leave.start_date.strftime('%Y-%m-%d')
        else:
            date_str = f"{leave.start_date.strftime('%Y-%m-%d')} to {leave.end_date.strftime('%Y-%m-%d')}"
        
        approved_details.append(f"<@{leave.employee.username}> - {department.name} - {date_str}")
    
    # Format pending leaves with detailed info
    pending_details = []
    for leave in pending_leaves:
        # Format date range
        if leave.start_date == leave.end_date:
            date_str = leave.start_date.strftime('%Y-%m-%d')
        else:
            date_str = f"{leave.start_date.strftime('%Y-%m-%d')} to {leave.end_date.strftime('%Y-%m-%d')}"
        
        pending_details.append(f"<@{leave.employee.username}> - {department.name} - {date_str}")
    
    return {
        'approved_count': len(approved_details),
        'pending_count': len(pending_details),
        'approved_details': approved_details,
        'pending_details': pending_details,
        'approved_names': [f"<@{leave.employee.username}>" for leave in approved_leaves],
        'pending_names': [f"<@{leave.employee.username}>" for leave in pending_leaves]
    }

def create_leave_block(leave, display_options):
    """Create a formatted block for a single leave entry"""
    days = (leave.end_date - leave.start_date).days + 1
    user_role = UserRole.objects.filter(user=leave.employee).first()
    department = user_role.department.name if user_role and user_role.department else 'No Dept'
    
    # Status emoji
    status_emoji_map = {
        'PENDING': '⏳',
        'APPROVED': '✅',
        'REJECTED': '❌',
        'CANCELLED': '🚫',
        'PENDING_DOCS': '📄',
        'DOCS_SUBMITTED': '📋',
        'APPROVED_UNPAID': '💰',
        'APPROVED_COMPENSATORY': '🔄'
    }
    emoji = status_emoji_map.get(leave.status, '❓')
    
    # Base text
    text = f"{emoji} *<@{leave.employee.username}>*"
    
    if 'SHOW_DETAILS' in display_options:
        text += f" ({department})"
    
    text += f"\n📋 {leave.get_leave_type_display()} • {days} days"
    text += f"\n📅 {leave.start_date.strftime('%b %d')} - {leave.end_date.strftime('%b %d')}"
    text += f"\n📊 Status: {leave.status.replace('_', ' ').title()}"
    
    if 'SHOW_REASONS' in display_options and leave.reason:
        reason_preview = leave.reason[:100] + '...' if len(leave.reason) > 100 else leave.reason
        text += f"\n💬 Reason: {reason_preview}"
    
    if 'SHOW_CONFLICTS' in display_options:
        # Check for conflicts with this leave
        conflicts = LeaveRequest.objects.filter(
            start_date__lte=leave.end_date,
            end_date__gte=leave.start_date,
            status__in=['APPROVED', 'PENDING']
        ).exclude(id=leave.id)
        
        if conflicts.exists():
            text += f"\n⚠️ Conflicts with {conflicts.count()} other leave(s)"
    
    return {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": text
        }
    }