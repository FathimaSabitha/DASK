from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import Client, TestCase
from django.urls import reverse

from .models import Product, ProductVariant


class ProductModelTests(TestCase):
    def test_create_product_and_variants(self):
        product = Product.objects.create(
            name="Brightloop Payroll",
            product_type="Software",
            sales_price=Decimal("1200.00"),
            cost_price=Decimal("450.00"),
            notes="Cloud payroll software with multi-entity support.",
        )
        self.assertEqual(str(product), "Brightloop Payroll")

        # Test variant creation and price calculation (SRS FR-11: e.g. Odoo adds ₹560)
        variant_odoo = ProductVariant.objects.create(
            product=product,
            name="Odoo",
            additional_price=Decimal("560.00"),
        )
        variant_tally = ProductVariant.objects.create(
            product=product,
            name="TallyPrime",
            additional_price=Decimal("0.00"),
        )

        self.assertEqual(variant_odoo.sales_price, Decimal("1760.00"))
        self.assertEqual(variant_tally.sales_price, Decimal("1200.00"))
        self.assertEqual(product.variants.count(), 2)

    def test_product_name_unique(self):
        Product.objects.create(
            name="Unique Product",
            product_type="Software",
            sales_price=Decimal("100.00"),
            cost_price=Decimal("50.00"),
            notes="First",
        )
        with self.assertRaises(IntegrityError):
            Product.objects.create(
                name="Unique Product",
                product_type="Service",
                sales_price=Decimal("200.00"),
                cost_price=Decimal("100.00"),
                notes="Second duplicate",
            )

    def test_product_variant_unique_per_product(self):
        product = Product.objects.create(
            name="Product A",
            product_type="Software",
            sales_price=Decimal("100.00"),
            cost_price=Decimal("50.00"),
            notes="Test",
        )
        ProductVariant.objects.create(
            product=product,
            name="Edition X",
            additional_price=Decimal("10.00"),
        )
        with self.assertRaises(IntegrityError):
            ProductVariant.objects.create(
                product=product,
                name="Edition X",
                additional_price=Decimal("20.00"),
            )


class ProductViewTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_get_product_create_page(self):
        response = self.client.get(reverse("product_create"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/products/prod_add.html")
        self.assertContains(response, "Create a product")
        self.assertContains(response, "FR-08 · Product creation")
        self.assertContains(response, "Product variants")

    def test_post_product_create_standard(self):
        payload = {
            "productName": "Brightloop CRM",
            "productType": "SaaS / Cloud Service",
            "salesPrice": "1500.00",
            "costPrice": "600.00",
            "productNotes": "Customer relationship management software.",
            "variant_name": ["Odoo", "Zoho Books"],
            "variant_additional_price": ["560.00", "250.00"],
        }
        response = self.client.post(reverse("product_create"), data=payload)
        self.assertRedirects(response, reverse("product_list"))

        product = Product.objects.get(name="Brightloop CRM")
        self.assertEqual(product.product_type, "SaaS / Cloud Service")
        self.assertEqual(product.sales_price, Decimal("1500.00"))
        self.assertEqual(product.cost_price, Decimal("600.00"))
        self.assertEqual(product.variants.count(), 2)

        odoo_variant = product.variants.get(name="Odoo")
        self.assertEqual(odoo_variant.additional_price, Decimal("560.00"))
        self.assertEqual(odoo_variant.sales_price, Decimal("2060.00"))

    def test_post_product_create_with_custom_type(self):
        payload = {
            "productName": "Custom Implementation",
            "productType": "Other",
            "customProductType": "On-premise Deployment Kit",
            "salesPrice": "5000.00",
            "costPrice": "2000.00",
            "productNotes": "Deployment kit and architecture consulting.",
        }
        response = self.client.post(reverse("product_create"), data=payload)
        self.assertRedirects(response, reverse("product_list"))

        product = Product.objects.get(name="Custom Implementation")
        self.assertEqual(product.product_type, "On-premise Deployment Kit")

    def test_post_product_create_ajax(self):
        payload = {
            "productName": "Brightloop Invoicing",
            "productType": "Subscription / License",
            "salesPrice": "899.00",
            "costPrice": "300.00",
            "productNotes": "Recurring invoicing module.",
            "variant_name": ["TallyPrime"],
            "variant_additional_price": ["0.00"],
        }
        response = self.client.post(
            reverse("product_create"),
            data=payload,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("redirect_url"), reverse("product_list"))
        self.assertTrue(Product.objects.filter(name="Brightloop Invoicing").exists())

    def test_post_product_create_validation_error(self):
        # Missing product name and invalid price
        payload = {
            "productName": "",
            "productType": "Software",
            "salesPrice": "-10.00",
            "costPrice": "20.00",
            "productNotes": "Some notes",
        }
        response = self.client.post(reverse("product_create"), data=payload)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/products/prod_add.html")
        self.assertIn("productName", response.context["errors"])
        self.assertIn("salesPrice", response.context["errors"])
        self.assertEqual(Product.objects.count(), 0)

    def test_get_product_list_page(self):
        product = Product.objects.create(
            name="Brightloop Analytics",
            product_type="Software",
            sales_price=Decimal("2500.00"),
            cost_price=Decimal("800.00"),
            notes="Business intelligence dashboard suite.",
        )
        ProductVariant.objects.create(
            product=product,
            name="Enterprise",
            additional_price=Decimal("1000.00"),
        )
        response = self.client.get(reverse("product_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/products/prod_list.html")
        self.assertContains(response, "Brightloop Analytics")
        self.assertContains(response, "2500.00")
        self.assertContains(response, "Enterprise")
        self.assertContains(response, "1000.00")
