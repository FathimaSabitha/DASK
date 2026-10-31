from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
urlpatterns = [
    path('register/', views.register, name='register'),
    path('staff/create/', views.create_staff, name='create_staff'),
    
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    # Customer Password Reset

path(
    'password-reset/',
    auth_views.PasswordResetView.as_view(
        template_name='core/authentication/password_reset.html',
        email_template_name='core/authentication/password_reset_email.html',
        success_url='/password-reset/done/'
    ),
    name='password_reset'
),

path(
    'password-reset/done/',
    auth_views.PasswordResetDoneView.as_view(
        template_name='core/authentication/password_reset_done.html'
    ),
    name='password_reset_done'
),

path(
    'reset/<uidb64>/<token>/',
    auth_views.PasswordResetConfirmView.as_view(
        template_name='core/authentication/password_reset_confirm.html',
        success_url='/reset/complete/'
    ),
    name='password_reset_confirm'
),

path(
    'reset/complete/',
    auth_views.PasswordResetCompleteView.as_view(
        template_name='core/authentication/password_reset_complete.html'
    ),
    name='password_reset_complete'
),
    path('customers/', views.customer_list, name='customer_list'),
    path('customers/<int:pk>/', views.customer_detail, name='customer_detail'),
    path('customers/<int:pk>/edit/', views.customer_update, name='customer_update'),
]