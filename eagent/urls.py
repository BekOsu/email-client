from django.urls import path
from . import views

urlpatterns = [
    path("", views.email_agent_view, name="email_agent"),
]
