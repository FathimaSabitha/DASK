from django.urls import path
from . import views

urlpatterns = [
    path('', views.register, name='home'),
    path('register/', views.register, name='register'),
]