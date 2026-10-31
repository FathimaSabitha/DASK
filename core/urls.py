from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
urlpatterns = [
    path('register/', views.register, name='register'),
    path('staff/create/', views.create_staff, name='create_staff'),
    
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Product management (Section 3.2)
    path('products/catalog/', views.product_userlist, name='product_userlist'),
    path('products/userlist/', views.product_userlist, name='product_userlist_alias'),
    path('catalog/', views.product_userlist, name='catalog_alias'),
    path('products/<int:product_id>/edit/', views.product_edit, name='product_edit'),
    path('products/<int:product_id>/delete/', views.product_delete, name='product_delete'),

    # Subscription Plan Management (Section 3.3, FR-12 to FR-15)
    path('plans/', views.plan_list, name='plan_list'),
    path('plans/add/', views.plan_create, name='plan_create'),
    path('plans/create/', views.plan_create, name='plan_create_alias'),
    path('plans/<int:plan_id>/edit/', views.plan_edit, name='plan_edit'),
    path('plans/<int:plan_id>/lifecycle/', views.plan_lifecycle_action, name='plan_lifecycle_action'),
    path('plans/<int:plan_id>/delete/', views.plan_delete, name='plan_delete'),

    # Quotation Management (Section 3.5, FR-19 to FR-22)
    path('quotations/', views.quotation_list, name='quotation_list'),
    path('quotations/add/', views.quotation_create, name='quotation_create'),
    path('quotations/create/', views.quotation_create, name='quotation_create_alias'),
    path('quotations/<int:quotation_id>/', views.quotation_detail, name='quotation_detail'),
    path('quotations/<int:quotation_id>/status/', views.quotation_status_action, name='quotation_status_action'),
    path('quotations/<int:quotation_id>/convert/', views.quotation_convert, name='quotation_convert'),
    path('quotations/template/api/<int:template_id>/', views.quotation_template_api, name='quotation_template_api'),
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