from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('staff/create/', views.create_staff, name='create_staff'),
    
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
]