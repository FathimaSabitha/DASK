from django.contrib import admin
from .models import (
    CustomerProfile, Product, ProductVariant, SubscriptionPlan,
    QuotationTemplate, QuotationTemplateItem,
    Quotation, QuotationItem,
    Subscription, SubscriptionItem,
    TaxRule, DiscountRule, DiscountProduct,
    Invoice, InvoiceItem, Payment,
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


@admin.register(TaxRule)
class TaxRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "rate", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)


class DiscountProductInline(admin.TabularInline):
    model = DiscountProduct
    extra = 1


@admin.register(DiscountRule)
class DiscountRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "discount_type", "value", "is_active", "valid_from", "valid_until", "times_used")
    list_filter = ("discount_type", "is_active")
    search_fields = ("name",)
    inlines = (DiscountProductInline,)


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "customer", "status", "issue_date", "due_date", "total_amount")
    list_filter = ("status", "issue_date")
    search_fields = ("invoice_number", "customer__user__email")
    inlines = (InvoiceItemInline,)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("invoice", "amount", "payment_method", "payment_date", "reference_number", "recorded_by")
    list_filter = ("payment_method", "payment_date")
    search_fields = ("invoice__invoice_number", "reference_number")
