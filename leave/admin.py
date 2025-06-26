from django.contrib import admin
from .models import LeaveRequest, LeaveBalance, LeavePolicy, Department, Team, UserRole

@admin.register(LeaveBalance)
class LeaveBalanceAdmin(admin.ModelAdmin):
    list_display = ['user', 'casual_leave', 'sick_leave', 'last_reset_date']
    search_fields = ['user__username']
    readonly_fields = ['last_reset_date']

@admin.register(LeavePolicy)
class LeavePolicyAdmin(admin.ModelAdmin):
    list_display = ['name', 'casual_leave_limit', 'sick_leave_limit', 'created_at']
    search_fields = ['name']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ['employee', 'leave_type', 'start_date', 'end_date', 'status', 'created_at']
    list_filter = ['status', 'leave_type']
    search_fields = ['employee__username', 'reason']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name']

@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name']
    filter_horizontal = ['members', 'admins']

@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'department', 'is_admin']
    list_filter = ['role', 'department', 'is_admin']
    search_fields = ['user__username', 'department__name']