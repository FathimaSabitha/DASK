"""
URL configuration for DASK project.
"""
from django.contrib import admin
from django.urls import path, include

from core import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.product_list, name='home'),
    path('products/', views.product_list, name='product_list'),
    path('product/', views.product_list, name='product_alias'),
    path('product.html', views.product_list, name='product_html_alias'),
    path('products/create/', views.product_create, name='product_create'),
    path('products/add/', views.product_create, name='product_add_alias'),
    path('products/catalog/', views.product_userlist, name='product_userlist_dask'),
    path('products/userlist/', views.product_userlist, name='product_userlist_alias_dask'),

    # Plans aliases
    path('plans/', views.plan_list, name='plan_list_dask'),
    path('plans/add/', views.plan_create, name='plan_add_dask'),
    path('plans/create/', views.plan_create, name='plan_create_dask'),

    # Quotations aliases
    path('quotations/', views.quotation_list, name='quotation_list_dask'),
    path('quotations/add/', views.quotation_create, name='quotation_add_dask'),
    path('quotations/create/', views.quotation_create, name='quotation_create_dask'),

    path('', include('core.urls')),
]
