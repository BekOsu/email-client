from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', lambda request: redirect('email_agent')),  # Redirect to your email agent view
    path("eagent/", include("eagent.urls")),
]
