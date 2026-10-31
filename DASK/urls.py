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
    path('', include('core.urls')),
]
