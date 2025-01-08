from django.urls import path
from .views import check_emails

urlpatterns = [
    path("check-emails/", check_emails, name="check_emails"),
]
