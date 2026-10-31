from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models


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

    def __str__(self):
        return self.user.email or self.user.username


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
