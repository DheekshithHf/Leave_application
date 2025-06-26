from django.urls import path
from . import views

urlpatterns = [
    path('slack/events/', views.slack_events, name='slack_events'),
    path('slack/commands/assign-manager/', views.handle_slack_command, name='assign_manager'),
]