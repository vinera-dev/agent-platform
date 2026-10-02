from django.urls import path

from tenants import views

urlpatterns = [
    path("whoami", views.whoami),
]
