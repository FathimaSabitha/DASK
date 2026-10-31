from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('staff/create/', views.create_staff, name='create_staff'),
    
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('customers/', views.customer_list, name='customer_list'),
    path('customers/<int:pk>/', views.customer_detail, name='customer_detail'),
    path('customers/<int:pk>/edit/', views.customer_update, name='customer_update'),
]