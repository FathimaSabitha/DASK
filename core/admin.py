from django.contrib import admin
from .models import (
    CustomerProfile, Product, ProductVariant, SubscriptionPlan,
    QuotationTemplate, QuotationTemplateItem,
    Quotation, QuotationItem,
    Subscription, SubscriptionItem
)


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "product_type", "sales_price", "cost_price", "created_at")
    search_fields = ("name", "product_type")
    inlines = (ProductVariantInline,)


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ("name", "product", "price", "billing_frequency", "min_quantity", "start_date", "end_date", "status")
    list_filter = ("billing_frequency", "status", "product")
    search_fields = ("name", "product__name", "description")


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "customer_type", "company_name", "phone")
    search_fields = ("user__email", "user__username", "company_name", "phone")


class QuotationTemplateItemInline(admin.TabularInline):
    model = QuotationTemplateItem
    extra = 1


@admin.register(QuotationTemplate)
class QuotationTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "created_by", "created_at")
    search_fields = ("name", "description")
    inlines = (QuotationTemplateItemInline,)


class QuotationItemInline(admin.TabularInline):
    model = QuotationItem
    extra = 0


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = ("quotation_number", "customer", "status", "valid_until", "total_amount", "created_at")
    list_filter = ("status", "quotation_date", "valid_until")
    search_fields = ("quotation_number", "customer__user__email", "customer__company_name")
    inlines = (QuotationItemInline,)


class SubscriptionItemInline(admin.TabularInline):
    model = SubscriptionItem
    extra = 0


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("subscription_number", "customer", "plan", "status", "start_date", "expiry_date", "total_amount")
    list_filter = ("status", "start_date", "expiry_date")
    search_fields = ("subscription_number", "customer__user__email")
    inlines = (SubscriptionItemInline,)
