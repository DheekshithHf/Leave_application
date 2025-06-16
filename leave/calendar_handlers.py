from django.http import JsonResponse
from .slack_utils import slack_client, get_or_create_user, is_manager, is_in_manager_channel
from .models import Department
from datetime import datetime, timedelta
from slack_sdk.errors import SlackApiError
import logging
import threading

logger = logging.getLogger(__name__)

def handle_team_calendar(request):
    """Handle team calendar display (manager only) - Interactive form for filtering"""
    try:
        # Open interactive modal form for managers to specify what they want
        user_id = request.POST.get('user_id')
        
        # Get list of departments for dropdown
        departments = Department.objects.all()
        department_options = [
            {"text": {"type": "plain_text", "text": "All Departments"}, "value": "ALL"}
        ]
        for dept in departments:
            department_options.append({
                "text": {"type": "plain_text", "text": dept.name}, 
                "value": str(dept.id)
            })
        
        # Get current date info for default values
        today = datetime.now().date()
        
        view = {
            "type": "modal",
            "callback_id": "team_calendar_filter",
            "title": {"type": "plain_text", "text": "Team Calendar Filter"},
            "submit": {"type": "plain_text", "text": "Generate Calendar"},
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "📅 Customize Your Team Calendar",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Select the filters below to generate a customized team calendar view:\n\n✅ *All matching records will be displayed (no limits)*\n🔍 Use filters to narrow down results for specific needs"
                    }
                },
                {
                    "type": "divider"
                },
                {
                    "type": "input",
                    "block_id": "calendar_month",
                    "element": {
                        "type": "static_select",
                        "action_id": "month_select",
                        "placeholder": {"type": "plain_text", "text": "Select month to view"},
                        "initial_option": {
                            "text": {"type": "plain_text", "text": today.strftime('%B %Y')}, 
                            "value": today.strftime('%Y-%m')
                        },
                        "options": [
                            # Current year months
                            {"text": {"type": "plain_text", "text": f"January {today.year}"}, "value": f"{today.year}-01"},
                            {"text": {"type": "plain_text", "text": f"February {today.year}"}, "value": f"{today.year}-02"},
                            {"text": {"type": "plain_text", "text": f"March {today.year}"}, "value": f"{today.year}-03"},
                            {"text": {"type": "plain_text", "text": f"April {today.year}"}, "value": f"{today.year}-04"},
                            {"text": {"type": "plain_text", "text": f"May {today.year}"}, "value": f"{today.year}-05"},
                            {"text": {"type": "plain_text", "text": f"June {today.year}"}, "value": f"{today.year}-06"},
                            {"text": {"type": "plain_text", "text": f"July {today.year}"}, "value": f"{today.year}-07"},
                            {"text": {"type": "plain_text", "text": f"August {today.year}"}, "value": f"{today.year}-08"},
                            {"text": {"type": "plain_text", "text": f"September {today.year}"}, "value": f"{today.year}-09"},
                            {"text": {"type": "plain_text", "text": f"October {today.year}"}, "value": f"{today.year}-10"},
                            {"text": {"type": "plain_text", "text": f"November {today.year}"}, "value": f"{today.year}-11"},
                            {"text": {"type": "plain_text", "text": f"December {today.year}"}, "value": f"{today.year}-12"},
                            # Next year months (first 6 months)
                            {"text": {"type": "plain_text", "text": f"January {today.year + 1}"}, "value": f"{today.year + 1}-01"},
                            {"text": {"type": "plain_text", "text": f"February {today.year + 1}"}, "value": f"{today.year + 1}-02"},
                            {"text": {"type": "plain_text", "text": f"March {today.year + 1}"}, "value": f"{today.year + 1}-03"},
                            {"text": {"type": "plain_text", "text": f"April {today.year + 1}"}, "value": f"{today.year + 1}-04"},
                            {"text": {"type": "plain_text", "text": f"May {today.year + 1}"}, "value": f"{today.year + 1}-05"},
                            {"text": {"type": "plain_text", "text": f"June {today.year + 1}"}, "value": f"{today.year + 1}-06"},
                            # Previous year months (last 6 months)
                            {"text": {"type": "plain_text", "text": f"July {today.year - 1}"}, "value": f"{today.year - 1}-07"},
                            {"text": {"type": "plain_text", "text": f"August {today.year - 1}"}, "value": f"{today.year - 1}-08"},
                            {"text": {"type": "plain_text", "text": f"September {today.year - 1}"}, "value": f"{today.year - 1}-09"},
                            {"text": {"type": "plain_text", "text": f"October {today.year - 1}"}, "value": f"{today.year - 1}-10"},
                            {"text": {"type": "plain_text", "text": f"November {today.year - 1}"}, "value": f"{today.year - 1}-11"},
                            {"text": {"type": "plain_text", "text": f"December {today.year - 1}"}, "value": f"{today.year - 1}-12"}
                        ]
                    },
                    "label": {"type": "plain_text", "text": "📅 Select Month"}
                },
                {
                    "type": "input",
                    "block_id": "custom_start_date",
                    "optional": True,
                    "element": {
                        "type": "datepicker",
                        "action_id": "start_date_select",
                        "initial_date": today.strftime('%Y-%m-%d'),
                        "placeholder": {"type": "plain_text", "text": "Select start date"}
                    },
                    "label": {"type": "plain_text", "text": "📅 Custom Start Date (Optional - overrides month selection)"}
                },
                {
                    "type": "input",
                    "block_id": "custom_end_date",
                    "optional": True,
                    "element": {
                        "type": "datepicker",
                        "action_id": "end_date_select",
                        "initial_date": today.strftime('%Y-%m-%d'),
                        "placeholder": {"type": "plain_text", "text": "Select end date"}
                    },
                    "label": {"type": "plain_text", "text": "📅 Custom End Date (Optional - overrides month selection)"}
                },
                {
                    "type": "input",
                    "block_id": "department_filter",
                    "element": {
                        "type": "static_select",
                        "action_id": "department_select",
                        "placeholder": {"type": "plain_text", "text": "Choose department"},
                        "initial_option": department_options[0],
                        "options": department_options
                    },
                    "label": {"type": "plain_text", "text": "🏢 Department Filter"}
                },
                {
                    "type": "input",
                    "block_id": "status_filter",
                    "element": {
                        "type": "checkboxes",
                        "action_id": "status_select",
                        "initial_options": [
                            {"text": {"type": "plain_text", "text": "Pending Approval"}, "value": "PENDING"},
                            {"text": {"type": "plain_text", "text": "Approved"}, "value": "APPROVED"}
                        ],
                        "options": [
                            {"text": {"type": "plain_text", "text": "Pending Approval"}, "value": "PENDING"},
                            {"text": {"type": "plain_text", "text": "Approved"}, "value": "APPROVED"},
                            {"text": {"type": "plain_text", "text": "Rejected"}, "value": "REJECTED"},
                            {"text": {"type": "plain_text", "text": "Document Required"}, "value": "DOCS"},
                            {"text": {"type": "plain_text", "text": "Cancelled"}, "value": "CANCELLED"}
                        ]
                    },
                    "label": {"type": "plain_text", "text": "📊 Leave Status (Select all that apply)"}
                },
                {
                    "type": "input",
                    "block_id": "leave_type_filter",
                    "optional": True,
                    "element": {
                        "type": "checkboxes",
                        "action_id": "leave_type_select",
                        "options": [
                            {"text": {"type": "plain_text", "text": "Casual Leave"}, "value": "CASUAL"},
                            {"text": {"type": "plain_text", "text": "Sick Leave"}, "value": "SICK"},
                            {"text": {"type": "plain_text", "text": "Maternity Leave"}, "value": "MATERNITY"},
                            {"text": {"type": "plain_text", "text": "Paternity Leave"}, "value": "PATERNITY"}
                        ]
                    },
                    "label": {"type": "plain_text", "text": "📋 Leave Types (Optional - leave empty for all types)"}
                },
                {
                    "type": "input",
                    "block_id": "display_options",
                    "optional": True,
                    "element": {
                        "type": "checkboxes",
                        "action_id": "display_select",
                        "options": [
                            {"text": {"type": "plain_text", "text": "Show employee details"}, "value": "SHOW_DETAILS"},
                            {"text": {"type": "plain_text", "text": "Show leave reasons"}, "value": "SHOW_REASONS"},
                            {"text": {"type": "plain_text", "text": "Show conflict analysis"}, "value": "SHOW_CONFLICTS"},
                            {"text": {"type": "plain_text", "text": "Group by department"}, "value": "GROUP_DEPT"}
                        ]
                    },
                    "label": {"type": "plain_text", "text": "⚙️ Display Options (Optional)"}
                },
                {
                    "type": "input",
                    "block_id": "sort_option",
                    "optional": True,
                    "element": {
                        "type": "static_select",
                        "action_id": "sort_select",
                        "placeholder": {"type": "plain_text", "text": "Choose sorting order"},
                        "initial_option": {"text": {"type": "plain_text", "text": "Date (Earliest First)"}, "value": "DATE_ASC"},
                        "options": [
                            {"text": {"type": "plain_text", "text": "Date (Earliest First)"}, "value": "DATE_ASC"},
                            {"text": {"type": "plain_text", "text": "Date (Latest First)"}, "value": "DATE_DESC"},
                            {"text": {"type": "plain_text", "text": "Employee Name (A-Z)"}, "value": "EMPLOYEE_ASC"},
                            {"text": {"type": "plain_text", "text": "Employee Name (Z-A)"}, "value": "EMPLOYEE_DESC"},
                            {"text": {"type": "plain_text", "text": "Leave Type"}, "value": "TYPE"},
                            {"text": {"type": "plain_text", "text": "Status (Pending First)"}, "value": "STATUS_PENDING"},
                            {"text": {"type": "plain_text", "text": "Duration (Longest First)"}, "value": "DURATION_DESC"}
                        ]
                    },
                    "label": {"type": "plain_text", "text": "📈 Sort Results By (Optional)"}
                }
            ]
        }
        
        response = slack_client.views_open(
            trigger_id=request.POST.get('trigger_id'),
            view=view
        )
        return JsonResponse({'text': 'Opening team calendar filter...'})
        
    except Exception as e:
        logger.error(f"Error opening team calendar filter: {e}")
        return JsonResponse({'text': 'Error opening calendar filter'}, status=200)

def handle_team_calendar_filter_submission(payload):
    """Process team calendar filter form submission and generate customized calendar"""
    try:
        # IMMEDIATE RESPONSE - Return success first to avoid timeout
        def build_and_send_filtered_calendar():
            """Background function to build and send filtered calendar"""
            try:
                from .models import LeaveRequest, UserRole
                from .leave_utils import create_leave_block
                from .slack_utils import SLACK_MANAGER_CHANNEL
                
                # Extract form values
                values = payload['view']['state']['values']
                
                # Check if custom dates are provided
                custom_start = None
                custom_end = None
                
                if ('custom_start_date' in values and values['custom_start_date']['start_date_select'].get('selected_date') and
                    'custom_end_date' in values and values['custom_end_date']['end_date_select'].get('selected_date')):
                    # Use custom date range
                    custom_start = datetime.strptime(
                        values['custom_start_date']['start_date_select']['selected_date'],
                        '%Y-%m-%d'
                    ).date()
                    custom_end = datetime.strptime(
                        values['custom_end_date']['end_date_select']['selected_date'],
                        '%Y-%m-%d'
                    ).date()
                    
                    # Ensure start date is not after end date
                    if custom_start > custom_end:
                        custom_start, custom_end = custom_end, custom_start
                    
                    start_of_month = custom_start
                    end_of_month = custom_end
                    date_source = "custom"
                    
                elif 'custom_start_date' in values and values['custom_start_date']['start_date_select'].get('selected_date'):
                    # Only start date provided - use start date to end of that month
                    custom_start = datetime.strptime(
                        values['custom_start_date']['start_date_select']['selected_date'],
                        '%Y-%m-%d'
                    ).date()
                    start_of_month = custom_start
                    end_of_month = (start_of_month.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
                    date_source = "start_only"
                    
                elif 'custom_end_date' in values and values['custom_end_date']['end_date_select'].get('selected_date'):
                    # Only end date provided - use start of that month to end date
                    custom_end = datetime.strptime(
                        values['custom_end_date']['end_date_select']['selected_date'],
                        '%Y-%m-%d'
                    ).date()
                    start_of_month = custom_end.replace(day=1)
                    end_of_month = custom_end
                    date_source = "end_only"
                    
                else:
                    # Use selected month from dropdown
                    selected_month_value = values['calendar_month']['month_select']['selected_option']['value']
                    year, month = selected_month_value.split('-')
                    start_of_month = datetime(int(year), int(month), 1).date()
                    end_of_month = (start_of_month + timedelta(days=32)).replace(day=1) - timedelta(days=1)
                    date_source = "month"
                
                # Get department filter
                dept_filter = values['department_filter']['department_select']['selected_option']['value']
                
                # Get status filters
                status_options = values['status_filter']['status_select']['selected_options']
                status_filters = []
                for option in status_options:
                    status_value = option['value']
                    if status_value == 'PENDING':
                        status_filters.extend(['PENDING', 'PENDING_DOCS', 'DOCS_SUBMITTED'])
                    elif status_value == 'APPROVED':
                        status_filters.extend(['APPROVED', 'APPROVED_UNPAID', 'APPROVED_COMPENSATORY'])
                    elif status_value == 'DOCS':
                        status_filters.extend(['PENDING_DOCS', 'DOCS_SUBMITTED', 'DOCS_PENDING_LATER'])
                    else:
                        status_filters.append(status_value)
                
                # Get leave type filters (optional)
                leave_type_filters = []
                if 'leave_type_filter' in values and values['leave_type_filter']['leave_type_select'].get('selected_options'):
                    leave_type_options = values['leave_type_filter']['leave_type_select']['selected_options']
                    leave_type_filters = [option['value'] for option in leave_type_options]
                
                # Get display options (optional)
                display_options = []
                if 'display_options' in values and values['display_options']['display_select'].get('selected_options'):
                    display_opts = values['display_options']['display_select']['selected_options']
                    display_options = [option['value'] for option in display_opts]
                
                # Get sort option (optional)
                sort_option = "DATE_ASC"  # Default
                if 'sort_option' in values and values['sort_option']['sort_select'].get('selected_option'):
                    sort_option = values['sort_option']['sort_select']['selected_option']['value']
                
                # Build query
                query = LeaveRequest.objects.filter(
                    start_date__lte=end_of_month,
                    end_date__gte=start_of_month,
                    status__in=status_filters
                )
                
                # Apply department filter
                if dept_filter != 'ALL':
                    query = query.filter(employee__userrole__department_id=dept_filter)
                
                # Apply leave type filter
                if leave_type_filters:
                    query = query.filter(leave_type__in=leave_type_filters)
                
                # Apply sorting
                if sort_option == "DATE_ASC":
                    leaves = query.order_by('start_date', 'employee__username')
                elif sort_option == "DATE_DESC":
                    leaves = query.order_by('-start_date', 'employee__username')
                elif sort_option == "EMPLOYEE_ASC":
                    leaves = query.order_by('employee__username', 'start_date')
                elif sort_option == "EMPLOYEE_DESC":
                    leaves = query.order_by('-employee__username', 'start_date')
                elif sort_option == "TYPE":
                    leaves = query.order_by('leave_type', 'start_date', 'employee__username')
                elif sort_option == "STATUS_PENDING":
                    # Custom sorting to put PENDING statuses first
                    leaves = query.extra(
                        select={
                            'status_priority': "CASE WHEN status LIKE 'PENDING%' THEN 1 WHEN status LIKE 'DOCS%' THEN 2 ELSE 3 END"
                        }
                    ).order_by('status_priority', 'start_date', 'employee__username')
                elif sort_option == "DURATION_DESC":
                    # Sort by duration (longest first)
                    leaves = query.extra(
                        select={
                            'duration': '(end_date - start_date + 1)'
                        }
                    ).order_by('-duration', 'start_date', 'employee__username')
                else:
                    leaves = query.order_by('start_date', 'employee__username')
                
                # Build calendar blocks with dynamic header
                if date_source == "custom":
                    if start_of_month == end_of_month:
                        header_text = f"📅 Filtered Team Calendar - {start_of_month.strftime('%B %d, %Y')}"
                    else:
                        header_text = f"📅 Filtered Team Calendar - {start_of_month.strftime('%b %d')} to {end_of_month.strftime('%b %d, %Y')}"
                elif date_source in ["start_only", "end_only"]:
                    header_text = f"📅 Filtered Team Calendar - {start_of_month.strftime('%b %d')} to {end_of_month.strftime('%b %d, %Y')}"
                else:
                    header_text = f"📅 Filtered Team Calendar - {start_of_month.strftime('%B %Y')}"
                
                blocks = [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": header_text,
                            "emoji": True
                        }
                    }
                ]
                
                # Add filter summary
                dept_name = "All Departments" if dept_filter == 'ALL' else Department.objects.get(id=dept_filter).name if dept_filter != 'ALL' else "All"
                status_names = [opt['text']['text'] for opt in status_options]
                leave_type_names = [opt['text']['text'] for opt in values.get('leave_type_filter', {}).get('leave_type_select', {}).get('selected_options', [])]
                
                filter_text = f"🔍 *Applied Filters:*\n"
                filter_text += f"• *Department:* {dept_name}\n"
                filter_text += f"• *Status:* {', '.join(status_names)}\n"
                if leave_type_names:
                    filter_text += f"• *Leave Types:* {', '.join(leave_type_names)}\n"
                
                # Add date range info to filter summary
                if date_source == "custom":
                    if start_of_month == end_of_month:
                        filter_text += f"• *Date:* {start_of_month.strftime('%B %d, %Y')}\n"
                    else:
                        filter_text += f"• *Date Range:* {start_of_month.strftime('%b %d')} to {end_of_month.strftime('%b %d, %Y')}\n"
                elif date_source in ["start_only", "end_only"]:
                    filter_text += f"• *Date Range:* {start_of_month.strftime('%b %d')} to {end_of_month.strftime('%b %d, %Y')}\n"
                else:
                    filter_text += f"• *Period:* {start_of_month.strftime('%B %Y')}\n"
                
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": filter_text
                    }
                })
                blocks.append({"type": "divider"})
                
                if not leaves.exists():
                    blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"🔍 *No leaves found matching your filters*"
                        }
                    })
                else:
                    # Group by department if requested
                    if 'GROUP_DEPT' in display_options:
                        # Group leaves by department
                        dept_groups = {}
                        for leave in leaves:
                            user_role = UserRole.objects.filter(user=leave.employee).first()
                            dept_name = user_role.department.name if user_role and user_role.department else 'No Department'
                            if dept_name not in dept_groups:
                                dept_groups[dept_name] = []
                            dept_groups[dept_name].append(leave)
                        
                        for dept_name, dept_leaves in dept_groups.items():
                            blocks.append({
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": f"🏢 *{dept_name}* ({len(dept_leaves)} leaves)"
                                }
                            })
                            
                            # Show ALL leaves in department (no limit)
                            for leave in dept_leaves:
                                blocks.append(create_leave_block(leave, display_options))
                            
                            blocks.append({"type": "divider"})
                    else:
                        # Regular list view - Show ALL leaves (no limit)
                        for leave in leaves:
                            blocks.append(create_leave_block(leave, display_options))
                
                # Add comprehensive summary
                total_leaves = leaves.count()
                total_days = sum((leave.end_date - leave.start_date).days + 1 for leave in leaves)
                
                # Additional statistics
                pending_count = leaves.filter(status__in=['PENDING', 'PENDING_DOCS', 'DOCS_SUBMITTED']).count()
                approved_count = leaves.filter(status__in=['APPROVED', 'APPROVED_UNPAID', 'APPROVED_COMPENSATORY']).count()
                rejected_count = leaves.filter(status='REJECTED').count()
                
                summary_text = f"📊 *Complete Summary:*\n"
                summary_text += f"• *Total Records:* {total_leaves} leaves\n"
                summary_text += f"• *Total Days:* {total_days} days\n"
                summary_text += f"• *Pending:* {pending_count} | *Approved:* {approved_count} | *Rejected:* {rejected_count}\n"
                
                if total_leaves > 50:
                    summary_text += f"\n💡 *Tip: Large dataset ({total_leaves} records). Use filters above to narrow down specific results.*"
                
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": summary_text
                    }
                })
                
                # Send to the leave-approvals channel
                try:
                    slack_client.chat_postMessage(
                        channel=SLACK_MANAGER_CHANNEL.lstrip('#'),
                        blocks=blocks,
                        text=header_text
                    )
                except SlackApiError as e:
                    logger.error(f"Error sending filtered calendar: {e}")
                    # Send error message
                    slack_client.chat_postMessage(
                        channel=SLACK_MANAGER_CHANNEL.lstrip('#'),
                        text=f"⚠️ Error generating filtered calendar: {str(e)}"
                    )
                
            except Exception as e:
                logger.error(f"Background error building filtered calendar: {e}")
                try:
                    from .slack_utils import SLACK_MANAGER_CHANNEL
                    slack_client.chat_postMessage(
                        channel=SLACK_MANAGER_CHANNEL.lstrip('#'),
                        text=f"⚠️ Error loading filtered calendar: {str(e)}"
                    )
                except Exception as slack_error:
                    logger.error(f"Failed to send error message: {slack_error}")
        
        # Start background thread for processing
        thread = threading.Thread(target=build_and_send_filtered_calendar)
        thread.daemon = True
        thread.start()
        
        # Return immediate response to close modal (prevents timeout)
        return JsonResponse({"response_action": "clear"})
        
    except Exception as e:
        logger.error(f"Error in team calendar filter submission: {e}")
        return JsonResponse({
            "response_action": "errors",
            "errors": {
                "calendar_month": f"Error processing filter: {str(e)}"
            }
        })