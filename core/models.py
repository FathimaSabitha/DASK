from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class CustomerProfile(models.Model):
    CUSTOMER_TYPES = [
        ('individual', 'Individual'),
        ('business', 'Business'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='customer_profile',
    )
    customer_type = models.CharField(
        max_length=20,
        choices=CUSTOMER_TYPES,
        default='individual',
    )
    company_name = models.CharField(
        max_length=150,
        blank=True,
        null=True,
    )
    phone = models.CharField(
        max_length=15,
        blank=True,
        null=True,
    )
    address = models.TextField(
        blank=True,
        null=True,
    )
    gst_number = models.CharField(
        max_length=20,
        blank=True,
        null=True,
    )

    @property
    def name(self):
        full = self.user.get_full_name().strip()
        if full:
            return full
        if self.company_name:
            return self.company_name
        return self.user.username

    @property
    def email(self):
        return self.user.email

    def __str__(self):
        return f"{self.name} ({self.user.email or self.user.username})"


class Product(models.Model):
    """A catalogue item that can later be used in plans and quotations."""

    name = models.CharField(max_length=80, unique=True)
    product_type = models.CharField(max_length=50)
    sales_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    notes = models.TextField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class ProductVariant(models.Model):
    """An optional configuration of a product with an additional charge."""

    product = models.ForeignKey(Product, related_name="variants", on_delete=models.CASCADE)
    name = models.CharField(max_length=80)
    additional_price = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["product", "name"], name="unique_variant_name_per_product"),
        ]

    @property
    def sales_price(self):
        return self.product.sales_price + self.additional_price

    def __str__(self):
        return f"{self.product.name} - {self.name}"


class SubscriptionPlan(models.Model):
    """
    A commercial arrangement under which a product is supplied (SRS Section 3.3, FR-12 to FR-15).
    Captures plan name, associated product, subscription price, billing frequency, minimum quantity,
    availability dates, and lifecycle state.
    """

    BILLING_FREQUENCIES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('closed', 'Closed'),
    ]

    name = models.CharField(max_length=100, unique=True)
    product = models.ForeignKey(Product, related_name="plans", on_delete=models.CASCADE)
    price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    billing_frequency = models.CharField(max_length=20, choices=BILLING_FREQUENCIES, default='monthly')
    min_quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    auto_close = models.BooleanField(default=True, help_text="Automatically close plan when end date is reached.")
    description = models.TextField(blank=True, null=True, max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({'end_date': 'Availability end date cannot be earlier than start date.'})

    @property
    def is_available(self):
        from django.utils import timezone
        if self.status != 'active':
            return False
        today = timezone.now().date()
        if self.start_date and today < self.start_date:
            return False
        if self.end_date and today > self.end_date:
            return False
        return True

    @property
    def effective_status(self):
        from django.utils import timezone
        if self.status == 'closed':
            return 'closed'
        if self.status == 'paused':
            return 'paused'
        today = timezone.now().date()
        if self.end_date and today > self.end_date:
            return 'closed' if self.auto_close else 'expired'
        if self.start_date and today < self.start_date:
            return 'scheduled'
        return 'active'

    def pause(self):
        self.status = 'paused'
        self.save()

    def resume(self):
        self.status = 'active'
        self.save()

    def close(self):
        self.status = 'closed'
        self.save()

    def renew(self, new_end_date):
        self.end_date = new_end_date
        self.status = 'active'
        self.save()

    def __str__(self):
        return f"{self.name} ({self.get_billing_frequency_display()}) - {self.product.name}"


Plan = SubscriptionPlan


class QuotationTemplate(models.Model):
    """
    Reusable quotation template containing predefined products and subscription plans (SRS FR-19).
    """
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True, null=True, max_length=500)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_quotation_templates')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class QuotationTemplateItem(models.Model):
    """
    Predefined product/plan line in a quotation template (SRS FR-19, Table 7).
    """
    template = models.ForeignKey(QuotationTemplate, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='template_items')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='template_items')
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True, related_name='template_items')
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    notes = models.CharField(max_length=200, blank=True)

    @property
    def total_price(self):
        return (Decimal(self.quantity) * self.unit_price).quantize(Decimal("0.01"))

    def __str__(self):
        return f"{self.template.name} - {self.product.name} (x{self.quantity})"


class Quotation(models.Model):
    """
    Customer price proposal prepared before a subscription is confirmed (SRS Section 3.5, FR-20 to FR-22).
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('accepted', 'Accepted'),
        ('converted', 'Converted'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
    ]

    quotation_number = models.CharField(max_length=50, unique=True)
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name='quotations')
    template = models.ForeignKey(QuotationTemplate, on_delete=models.SET_NULL, null=True, blank=True, related_name='generated_quotations')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_quotations')
    quotation_date = models.DateField(default=timezone.now)
    valid_until = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("18.00"))
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def issue_date(self):
        return self.quotation_date

    @property
    def is_expired(self):
        today = timezone.now().date()
        return self.valid_until < today and self.status != 'converted'

    @property
    def is_eligible_for_conversion(self):
        has_subscription = hasattr(self, 'converted_subscription') and self.converted_subscription is not None
        return self.status in ['draft', 'sent', 'accepted'] and not self.is_expired and not has_subscription

    def update_totals(self):
        items = self.items.all()
        subtotal = sum((item.total_price for item in items), Decimal("0.00"))
        self.subtotal = subtotal
        tax_rate_multiplier = Decimal(str(self.tax_rate)) / Decimal("100.00")
        self.tax_amount = (subtotal * tax_rate_multiplier).quantize(Decimal("0.01"))
        self.total_amount = (self.subtotal + self.tax_amount).quantize(Decimal("0.01"))
        self.save()

    def __str__(self):
        return f"{self.quotation_number} - {self.customer}"


class QuotationItem(models.Model):
    """
    Individual line item in a quotation (SRS Section 3.5, Table 9).
    """
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='quotation_lines')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='quotation_lines')
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True, related_name='quotation_lines')
    description = models.CharField(max_length=200, blank=True)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    total_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])

    def save(self, *args, **kwargs):
        self.total_price = (Decimal(self.quantity) * self.unit_price).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.quotation.quotation_number}: {self.product.name} (x{self.quantity})"


class Subscription(models.Model):
    """
    A customer's recurring agreement, created directly or converted from a quotation (SRS FR-22, FR-23, FR-24).
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('quotation', 'Quotation'),
        ('confirmed', 'Confirmed'),
        ('active', 'Active'),
        ('closed', 'Closed'),
    ]

    subscription_number = models.CharField(max_length=50, unique=True)
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='subscriptions')
    source_quotation = models.OneToOneField(Quotation, on_delete=models.SET_NULL, null=True, blank=True, related_name='converted_subscription')
    start_date = models.DateField(default=timezone.now)
    expiry_date = models.DateField(null=True, blank=True)
    payment_terms = models.CharField(max_length=50, default='Net 30')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.subscription_number} - {self.customer}"


class SubscriptionItem(models.Model):
    """
    Individual line item in a subscription (SRS Table 11).
    """
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='subscription_lines')
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True, related_name='subscription_lines')
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    total_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])

    def save(self, *args, **kwargs):
        self.total_price = (Decimal(self.quantity) * self.unit_price).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.subscription.subscription_number}: {self.product.name} (x{self.quantity})"

