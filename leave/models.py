from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Department(models.Model):
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.name

class UserRole(models.Model):
    ROLE_CHOICES = [
        ('EMPLOYEE', 'Employee'),
        ('MANAGER', 'Manager'),
        ('ADMIN', 'Admin')
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='EMPLOYEE')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    is_admin = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username} - {self.role}"

class Team(models.Model):
    name = models.CharField(max_length=100, unique=True)
    members = models.ManyToManyField(User, related_name='teams')
    admins = models.ManyToManyField(User, related_name='admin_teams')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class LeaveBalance(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    casual_leave = models.IntegerField(default=2)
    sick_leave = models.IntegerField(default=5)
    maternity_leave = models.IntegerField(default=180)
    paternity_leave = models.IntegerField(default=30)
    # Add tracking fields for used leave
    casual_used = models.IntegerField(default=0)
    sick_used = models.IntegerField(default=0)
    last_reset = models.DateField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username}'s Leave Balance"

    def reset_monthly_balance(self):
        today = timezone.now().date()
        if self.last_reset.month != today.month or self.last_reset.year != today.year:
            self.casual_leave = 2
            self.sick_leave = 5
            self.casual_used = 0  # Reset used days
            self.sick_used = 0    # Reset used days
            self.last_reset = today
            self.save()

    def get_used_days(self, leave_type):
        if leave_type == 'CASUAL':
            return self.casual_used
        elif leave_type == 'SICK':
            return self.sick_used
        return 0

    def get_remaining_days(self, leave_type):
        if leave_type == 'CASUAL':
            return max(0, self.casual_leave - self.casual_used)
        elif leave_type == 'SICK':
            return max(0, self.sick_leave - self.sick_used)
        elif leave_type == 'MATERNITY':
            return self.maternity_leave
        elif leave_type == 'PATERNITY':
            return self.paternity_leave
        return 0

class LeaveRequest(models.Model):
    LEAVE_TYPES = [
        ('CASUAL', 'Casual Leave'),
        ('SICK', 'Sick Leave'),
        ('MATERNITY', 'Maternity Leave'),
        ('PATERNITY', 'Paternity Leave'),
    ]
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('PENDING_DOCS', 'Pending Documents'),
        ('DOCS_SUBMITTED', 'Documents Submitted'),
        ('PENDING_UNPAID', 'Pending Unpaid Acceptance'),
        ('PENDING_COMP', 'Pending Compensatory Acceptance'),
        ('APPROVED_UNPAID', 'Approved as Unpaid'),
        ('APPROVED_COMP', 'Approved with Compensatory'),
        ('CANCELLED', 'Cancelled')
    ]
    
    DOCUMENT_STATUS = [
        ('NOT_REQUIRED', 'Not Required'),
        ('PENDING', 'Pending'),
        ('SUBMITTED', 'Submitted'),
        ('VERIFIED', 'Verified'),
        ('REJECTED', 'Rejected')
    ]

    employee = models.ForeignKey(User, on_delete=models.CASCADE, related_name='leave_requests')
    leave_type = models.CharField(max_length=20, choices=LEAVE_TYPES)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    backup_person = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    supervisor_comment = models.TextField(null=True, blank=True)
    
    # Document related fields
    document_type = models.CharField(max_length=100, null=True, blank=True)
    document_status = models.CharField(max_length=20, choices=DOCUMENT_STATUS, default='NOT_REQUIRED')
    document_submission_date = models.DateField(null=True, blank=True)
    document_verification_date = models.DateField(null=True, blank=True)
    document_notes = models.TextField(null=True, blank=True)
    
    # Compensatory work related
    compensatory_date = models.DateField(null=True, blank=True)
    
    # Thread tracking
    thread_ts = models.CharField(max_length=50, null=True, blank=True)
    document_thread_ts = models.CharField(max_length=50, null=True, blank=True)  # For document submission thread

    def __str__(self):
        return f"{self.employee.username}'s {self.get_leave_type_display()} ({self.start_date} to {self.end_date})"

class LeavePolicy(models.Model):
    name = models.CharField(max_length=100)
    casual_leave_limit = models.IntegerField(default=2)
    sick_leave_limit = models.IntegerField(default=5)
    maternity_leave_limit = models.IntegerField(default=180)
    paternity_leave_limit = models.IntegerField(default=30)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Leave Policies"