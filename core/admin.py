from django.contrib import admin
from .models import CustomerProfile

from .models import Product, ProductVariant


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "product_type", "sales_price", "cost_price", "created_at")
    search_fields = ("name", "product_type")
    inlines = (ProductVariantInline,)
admin.site.register(CustomerProfile)