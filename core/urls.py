from django.contrib.auth import views as auth_views
from django.urls import path
from . import views

urlpatterns = [
    # Landing & Dashboard Routing
    path('', views.home_view, name='home'),

    # Section 3.1: Authentication & Authorization (FR-01 to FR-07)
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('staff/create/', views.create_staff, name='create_staff'),

    # Section 3.1: Password Reset (FR-05)
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

    # Section 3.2: Product Management (FR-08 to FR-11)
    path('products/', views.product_list, name='product_list'),
    path('product/', views.product_list, name='product_alias'),
    path('products/create/', views.product_create, name='product_create'),
    path('products/add/', views.product_create, name='product_create_alias'),
    path('products/catalog/', views.product_userlist, name='product_userlist'),
    path('products/userlist/', views.product_userlist, name='product_userlist_alias'),
    path('catalog/', views.product_userlist, name='catalog_alias'),
    path('products/<int:product_id>/edit/', views.product_edit, name='product_edit'),
    path('products/<int:product_id>/delete/', views.product_delete, name='product_delete'),

    # Section 3.3: Subscription Plan Management (FR-12 to FR-15)
    path('plans/', views.plan_list, name='plan_list'),
    path('plans/add/', views.plan_create, name='plan_create'),
    path('plans/create/', views.plan_create, name='plan_create_alias'),
    path('plans/<int:plan_id>/edit/', views.plan_edit, name='plan_edit'),
    path('plans/<int:plan_id>/lifecycle/', views.plan_lifecycle_action, name='plan_lifecycle_action'),
    path('plans/<int:plan_id>/delete/', views.plan_delete, name='plan_delete'),

    # Section 3.4: Customer Management (FR-16 to FR-18)
    path('customers/', views.customer_list, name='customer_list'),
    path('customers/<int:pk>/', views.customer_detail, name='customer_detail'),
    path('customers/<int:pk>/edit/', views.customer_update, name='customer_update'),

    # Section 3.5: Quotation Management (FR-19 to FR-22)
    path('quotations/', views.quotation_list, name='quotation_list'),
    path('quotations/add/', views.quotation_create, name='quotation_create'),
    path('quotations/create/', views.quotation_create, name='quotation_create_alias'),
    path('quotations/<int:quotation_id>/', views.quotation_detail, name='quotation_detail'),
    path('quotations/<int:quotation_id>/status/', views.quotation_status_action, name='quotation_status_action'),
    path('quotations/<int:quotation_id>/convert/', views.quotation_convert, name='quotation_convert'),
    path('quotations/template/api/<int:template_id>/', views.quotation_template_api, name='quotation_template_api'),

    # Section 3.6: Subscription Management (FR-23 to FR-26)
    path('subscriptions/', views.subscription_list, name='subscription_list'),
    path('subscriptions/<int:subscription_id>/', views.subscription_detail, name='subscription_detail'),
    path('subscriptions/<int:subscription_id>/lifecycle/', views.subscription_lifecycle_action, name='subscription_lifecycle_action'),
    path('subscriptions/<int:subscription_id>/cancel/', views.subscription_cancel, name='subscription_cancel'),
    path('subscriptions/<int:subscription_id>/renew/', views.subscription_renew, name='subscription_renew'),

    # Section 3.7: Invoice Management (FR-27 to FR-32)
    path('invoices/', views.invoice_list, name='invoice_list'),
    path('invoices/<int:invoice_id>/', views.invoice_detail, name='invoice_detail'),
    path('invoices/<int:invoice_id>/status/', views.invoice_status_action, name='invoice_status_action'),
    path('invoices/create/<int:subscription_id>/', views.invoice_create, name='invoice_create'),

    # Section 3.8: Tax & Discount Management (FR-33 to FR-37)
    path('tax-rules/', views.tax_rule_list, name='tax_rule_list'),
    path('tax-rules/create/', views.tax_rule_create, name='tax_rule_create'),
    path('tax-rules/<int:pk>/edit/', views.tax_rule_edit, name='tax_rule_edit'),
    path('tax-rules/<int:pk>/delete/', views.tax_rule_delete, name='tax_rule_delete'),
    path('discount-rules/', views.discount_rule_list, name='discount_rule_list'),
    path('discount-rules/create/', views.discount_rule_create, name='discount_rule_create'),
    path('discount-rules/<int:pk>/edit/', views.discount_rule_edit, name='discount_rule_edit'),
    path('discount-rules/<int:pk>/delete/', views.discount_rule_delete, name='discount_rule_delete'),

    # Section 3.9: Payment Management (FR-38 to FR-42)
    path('payments/', views.payment_list, name='payment_list'),
    path('payments/record/<int:invoice_id>/', views.payment_record, name='payment_record'),
    path('payments/<int:payment_id>/delete/', views.payment_delete, name='payment_delete'),

    # Section 3.10: Dashboards & Reporting (FR-43 to FR-48)
    path('dashboard/admin/', views.admin_dashboard, name='admin_dashboard'),
    path('dashboard/staff/', views.staff_dashboard, name='staff_dashboard'),
    path('dashboard/customer/', views.customer_dashboard, name='customer_dashboard'),
    path('reports/', views.reports_view, name='reports'),
    path('reports/export/csv/', views.reports_export_csv, name='reports_export_csv'),
]
