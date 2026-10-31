from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import Client, TestCase
from django.urls import reverse

from .models import (
    CustomerProfile,
    Product,
    ProductVariant,
    Quotation,
    QuotationItem,
    QuotationTemplate,
    QuotationTemplateItem,
    Subscription,
    SubscriptionItem,
    SubscriptionPlan,
)


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
        self.admin_group, _ = Group.objects.get_or_create(name="Admin")
        self.customer_group, _ = Group.objects.get_or_create(name="Customer")
        self.admin_user = User.objects.create_superuser(
            username="adminuser",
            email="admin@brightloop.com",
            password="AdminPass123!",
        )
        self.customer_user = User.objects.create_user(
            username="custuser",
            email="cust@brightloop.com",
            password="CustPass123!",
        )
        self.customer_user.groups.add(self.customer_group)

    def test_get_product_create_page(self):
        response = self.client.get(reverse("product_create"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/products/prod_add.html")
        self.assertContains(response, "Create a product")

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
        self.assertContains(response, "Edit")

    def test_get_product_edit_page(self):
        product = Product.objects.create(
            name="Brightloop Helpdesk",
            product_type="Service",
            sales_price=Decimal("400.00"),
            cost_price=Decimal("150.00"),
            notes="Customer support ticketing.",
        )
        response = self.client.get(reverse("product_edit", args=[product.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/products/prod_edit.html")
        self.assertContains(response, "Brightloop Helpdesk")

    def test_post_product_edit_success(self):
        product = Product.objects.create(
            name="Brightloop ERP",
            product_type="Software",
            sales_price=Decimal("3000.00"),
            cost_price=Decimal("1000.00"),
            notes="ERP core suite.",
        )
        v1 = ProductVariant.objects.create(
            product=product,
            name="Basic Tier",
            additional_price=Decimal("0.00"),
        )
        v2 = ProductVariant.objects.create(
            product=product,
            name="Pro Tier",
            additional_price=Decimal("500.00"),
        )

        # Update product, modify v1, delete v2, and add new variant v3
        payload = {
            "productName": "Brightloop ERP NextGen",
            "productType": "SaaS / Cloud Service",
            "salesPrice": "3500.00",
            "costPrice": "1200.00",
            "productNotes": "Next generation cloud ERP.",
            "variant_id": [str(v1.id), str(v2.id), ""],
            "variant_name": ["Basic Tier V2", "Pro Tier", "Enterprise Addon"],
            "variant_additional_price": ["100.00", "500.00", "1500.00"],
            "variant_delete_ids": [str(v2.id)],
        }

        response = self.client.post(reverse("product_edit", args=[product.id]), data=payload)
        self.assertRedirects(response, reverse("product_list"))

        product.refresh_from_db()
        self.assertEqual(product.name, "Brightloop ERP NextGen")
        self.assertEqual(product.product_type, "SaaS / Cloud Service")
        self.assertEqual(product.sales_price, Decimal("3500.00"))
        self.assertEqual(product.cost_price, Decimal("1200.00"))

        # v1 should be updated
        v1.refresh_from_db()
        self.assertEqual(v1.name, "Basic Tier V2")
        self.assertEqual(v1.additional_price, Decimal("100.00"))

        # v2 should be deleted
        self.assertFalse(ProductVariant.objects.filter(id=v2.id).exists())

        # new variant should exist
        self.assertTrue(product.variants.filter(name="Enterprise Addon").exists())

    def test_post_product_delete(self):
        product = Product.objects.create(
            name="Temporary Product",
            product_type="Software",
            sales_price=Decimal("100.00"),
            cost_price=Decimal("50.00"),
            notes="To be deleted.",
        )
        ProductVariant.objects.create(
            product=product,
            name="Temp Variant",
            additional_price=Decimal("20.00"),
        )

        response = self.client.post(reverse("product_delete", args=[product.id]))
        self.assertRedirects(response, reverse("product_list"))
        self.assertFalse(Product.objects.filter(id=product.id).exists())
        self.assertEqual(ProductVariant.objects.filter(name="Temp Variant").count(), 0)

    def test_customer_cannot_edit_or_delete_product(self):
        product = Product.objects.create(
            name="Protected Item",
            product_type="Software",
            sales_price=Decimal("500.00"),
            cost_price=Decimal("200.00"),
            notes="Admin only.",
        )
        self.client.force_login(self.customer_user)

        edit_response = self.client.get(reverse("product_edit", args=[product.id]))
        self.assertRedirects(edit_response, reverse("product_list"))

        delete_response = self.client.post(reverse("product_delete", args=[product.id]))
        self.assertRedirects(delete_response, reverse("product_list"))
        self.assertTrue(Product.objects.filter(id=product.id).exists())


class AuthenticationTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_get_registration_page(self):
        response = self.client.get(reverse("register"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/authentication/registration.html")

    def test_post_registration_success(self):
        payload = {
            "full_name": "Bob Smith",
            "email": "bob@example.com",
            "password1": "StrongPass@123",
            "password2": "StrongPass@123",
            "customer_type": "business",
            "company_name": "Acme Corp",
            "phone": "9876543210",
            "address": "456 Market St",
        }
        response = self.client.post(reverse("register"), data=payload)
        self.assertRedirects(response, reverse("login"))

        user = User.objects.get(email="bob@example.com")
        self.assertEqual(user.first_name, "Bob Smith")
        self.assertTrue(user.groups.filter(name="Customer").exists())

    def test_login_and_logout_flow(self):
        User.objects.create_user(
            username="user@example.com",
            email="user@example.com",
            password="ValidPass#2026",
            first_name="Jane",
        )
        login_res = self.client.post(reverse("login"), {
            "email": "user@example.com",
            "password": "ValidPass#2026",
        })
        self.assertRedirects(login_res, reverse("product_userlist"))

        logout_res = self.client.get(reverse("logout"))
        self.assertRedirects(logout_res, reverse("login"))


class ProductUserlistTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.customer_group, _ = Group.objects.get_or_create(name="Customer")
        self.customer_user = User.objects.create_user(
            username="client@example.com",
            email="client@example.com",
            password="ClientPass123!",
        )
        self.customer_user.groups.add(self.customer_group)

        self.prod_software = Product.objects.create(
            name="Cloud ERP",
            product_type="Software",
            sales_price=Decimal("5000.00"),
            cost_price=Decimal("1500.00"),
            notes="Enterprise cloud ERP system.",
        )
        self.var_odoo = ProductVariant.objects.create(
            product=self.prod_software,
            name="Odoo Edition",
            additional_price=Decimal("560.00"),
        )

        self.prod_service = Product.objects.create(
            name="Premium Support",
            product_type="Service",
            sales_price=Decimal("1000.00"),
            cost_price=Decimal("200.00"),
            notes="24/7 dedicated support.",
        )

    def test_unauthenticated_access_allowed(self):
        """prod_userlist is accessible without login restriction for customer printing."""
        response = self.client.get(reverse("product_userlist"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/products/prod_userlist.html")
        self.assertContains(response, "Cloud ERP")
        self.assertContains(response, "Premium Support")
        self.assertContains(response, "Odoo Edition")

    def test_customer_role_access_allowed(self):
        """Logged-in customer accounts can freely access the customer catalogue and see Buy options."""
        self.client.force_login(self.customer_user)
        response = self.client.get(reverse("product_userlist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Customer Pricing Schedule")
        self.assertContains(response, "Buy Now")

    def test_variant_and_base_price_presentation(self):
        """Verifies base rate and variant effective price (sales_price + additional_price) are displayed."""
        response = self.client.get(reverse("product_userlist"))
        self.assertEqual(response.status_code, 200)
        # Base price 5000.00
        self.assertContains(response, "5000.00")
        # Variant add-on 560.00
        self.assertContains(response, "560.00")
        # Final price 5560.00
        self.assertContains(response, "5560.00")

    def test_search_and_category_filter(self):
        """Verifies searching by query and filtering by category."""
        # Search for 'ERP'
        res_search = self.client.get(reverse("product_userlist") + "?q=ERP")
        self.assertContains(res_search, "Cloud ERP")
        self.assertNotContains(res_search, "Premium Support")

        # Category filter 'Service'
        res_cat = self.client.get(reverse("product_userlist") + "?category=Service")
        self.assertContains(res_cat, "Premium Support")
        self.assertNotContains(res_cat, "Cloud ERP")


class SubscriptionPlanModelTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            name="Payroll Suite",
            product_type="Software",
            sales_price=Decimal("1000.00"),
            cost_price=Decimal("400.00"),
            notes="Cloud payroll application.",
        )

    def test_plan_creation_and_frequencies(self):
        """FR-12, FR-13: Supports plan creation and daily, weekly, monthly, yearly frequencies."""
        frequencies = ["daily", "weekly", "monthly", "yearly"]
        for freq in frequencies:
            plan = SubscriptionPlan.objects.create(
                name=f"Payroll {freq.capitalize()}",
                product=self.product,
                price=Decimal("250.00"),
                billing_frequency=freq,
                min_quantity=2,
                start_date=date.today(),
            )
            self.assertEqual(plan.billing_frequency, freq)
            self.assertEqual(plan.min_quantity, 2)
            self.assertTrue(plan.is_available)

    def test_invalid_date_range_rejected(self):
        """FR-14: End date cannot be earlier than start date."""
        plan = SubscriptionPlan(
            name="Invalid Date Plan",
            product=self.product,
            price=Decimal("100.00"),
            billing_frequency="monthly",
            min_quantity=1,
            start_date=date.today(),
            end_date=date.today() - timedelta(days=5),
        )
        with self.assertRaises(ValidationError):
            plan.clean()

    def test_unique_plan_name(self):
        """FR-14: Plan name must be unique."""
        SubscriptionPlan.objects.create(
            name="Unique Plan",
            product=self.product,
            price=Decimal("100.00"),
            billing_frequency="monthly",
            min_quantity=1,
            start_date=date.today(),
        )
        with self.assertRaises(IntegrityError):
            SubscriptionPlan.objects.create(
                name="Unique Plan",
                product=self.product,
                price=Decimal("200.00"),
                billing_frequency="yearly",
                min_quantity=1,
                start_date=date.today(),
            )

    def test_lifecycle_states_and_actions(self):
        """FR-15: Supports pause, resume, close, renew and automatic closure."""
        plan = SubscriptionPlan.objects.create(
            name="Lifecycle Plan",
            product=self.product,
            price=Decimal("500.00"),
            billing_frequency="monthly",
            min_quantity=1,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
            status="active",
        )
        self.assertEqual(plan.effective_status, "active")

        # Pause
        plan.pause()
        self.assertEqual(plan.status, "paused")
        self.assertFalse(plan.is_available)
        self.assertEqual(plan.effective_status, "paused")

        # Resume
        plan.resume()
        self.assertEqual(plan.status, "active")
        self.assertTrue(plan.is_available)

        # Close
        plan.close()
        self.assertEqual(plan.status, "closed")
        self.assertFalse(plan.is_available)
        self.assertEqual(plan.effective_status, "closed")

        # Renew
        new_date = date.today() + timedelta(days=60)
        plan.renew(new_date)
        self.assertEqual(plan.status, "active")
        self.assertEqual(plan.end_date, new_date)
        self.assertTrue(plan.is_available)


class SubscriptionPlanViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_group, _ = Group.objects.get_or_create(name="Admin")
        self.customer_group, _ = Group.objects.get_or_create(name="Customer")
        self.admin_user = User.objects.create_superuser(
            username="planadmin",
            email="admin@brightloop.io",
            password="AdminPass123!",
        )
        self.customer_user = User.objects.create_user(
            username="plancustomer",
            email="customer@brightloop.io",
            password="CustomerPass123!",
        )
        self.customer_user.groups.add(self.customer_group)

        self.product = Product.objects.create(
            name="Cloud Storage Pro",
            product_type="SaaS / Cloud Service",
            sales_price=Decimal("800.00"),
            cost_price=Decimal("200.00"),
            notes="Secure high availability cloud storage.",
        )

        self.plan = SubscriptionPlan.objects.create(
            name="Storage Monthly Tier 1",
            product=self.product,
            price=Decimal("750.00"),
            billing_frequency="monthly",
            min_quantity=1,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=90),
            status="active",
            description="Tier 1 enterprise cloud storage.",
        )

    def test_plan_list_view(self):
        """FR-12, FR-14: plan_list renders plans and metrics."""
        response = self.client.get(reverse("plan_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/plans/plan_list.html")
        self.assertContains(response, "Storage Monthly Tier 1")
        self.assertContains(response, "Cloud Storage Pro")
        self.assertContains(response, "Monthly")

    def test_plan_create_get_and_post(self):
        """FR-12, FR-14: Admin creates a valid subscription plan."""
        self.client.force_login(self.admin_user)
        # GET form
        response = self.client.get(reverse("plan_create"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/plans/plan_add.html")

        # POST valid plan
        payload = {
            "name": "Storage Annual Elite",
            "product_id": self.product.id,
            "price": "7500.00",
            "billing_frequency": "yearly",
            "min_quantity": "5",
            "start_date": date.today().isoformat(),
            "end_date": (date.today() + timedelta(days=365)).isoformat(),
            "auto_close": "on",
            "description": "Annual enterprise package with 2 months free.",
        }
        res_post = self.client.post(reverse("plan_create"), data=payload)
        self.assertRedirects(res_post, reverse("plan_list"))
        self.assertTrue(SubscriptionPlan.objects.filter(name="Storage Annual Elite").exists())
        created_plan = SubscriptionPlan.objects.get(name="Storage Annual Elite")
        self.assertEqual(created_plan.price, Decimal("7500.00"))
        self.assertEqual(created_plan.billing_frequency, "yearly")
        self.assertEqual(created_plan.min_quantity, 5)

    def test_plan_create_invalid_dates_rejected(self):
        """FR-14: End date earlier than start date displays validation error."""
        self.client.force_login(self.admin_user)
        payload = {
            "name": "Bad Date Plan",
            "product_id": self.product.id,
            "price": "500.00",
            "billing_frequency": "monthly",
            "min_quantity": "1",
            "start_date": "2026-10-31",
            "end_date": "2026-10-15",  # earlier than start
        }
        response = self.client.post(reverse("plan_create"), data=payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Availability end date cannot be earlier than start date.")
        self.assertFalse(SubscriptionPlan.objects.filter(name="Bad Date Plan").exists())

    def test_plan_edit_view(self):
        """FR-14: Admin modifies an existing subscription plan."""
        self.client.force_login(self.admin_user)
        payload = {
            "name": "Storage Monthly Updated",
            "product_id": self.product.id,
            "price": "899.00",
            "billing_frequency": "monthly",
            "min_quantity": "2",
            "start_date": date.today().isoformat(),
            "end_date": (date.today() + timedelta(days=120)).isoformat(),
            "status": "active",
            "description": "Updated commercial description.",
        }
        response = self.client.post(reverse("plan_edit", args=[self.plan.id]), data=payload)
        self.assertRedirects(response, reverse("plan_list"))
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.name, "Storage Monthly Updated")
        self.assertEqual(self.plan.price, Decimal("899.00"))
        self.assertEqual(self.plan.min_quantity, 2)

    def test_plan_lifecycle_actions(self):
        """FR-15: Pause, activate, close, and renew via lifecycle endpoint."""
        self.client.force_login(self.admin_user)

        # Pause
        self.client.post(reverse("plan_lifecycle_action", args=[self.plan.id]), data={"action": "pause"})
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, "paused")

        # Activate
        self.client.post(reverse("plan_lifecycle_action", args=[self.plan.id]), data={"action": "activate"})
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, "active")

        # Close
        self.client.post(reverse("plan_lifecycle_action", args=[self.plan.id]), data={"action": "close"})
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, "closed")

        # Renew
        new_date = (date.today() + timedelta(days=180)).isoformat()
        self.client.post(reverse("plan_lifecycle_action", args=[self.plan.id]), data={"action": "renew", "new_end_date": new_date})
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, "active")
        self.assertEqual(self.plan.end_date.isoformat(), new_date)

    def test_plan_auto_closure_on_list(self):
        """FR-15: Automatic closure when a plan reaches its configured end date."""
        past_plan = SubscriptionPlan.objects.create(
            name="Past Expired Plan",
            product=self.product,
            price=Decimal("100.00"),
            billing_frequency="daily",
            min_quantity=1,
            start_date=date.today() - timedelta(days=30),
            end_date=date.today() - timedelta(days=1),
            auto_close=True,
            status="active",
        )
        response = self.client.get(reverse("plan_list"))
        self.assertEqual(response.status_code, 200)
        past_plan.refresh_from_db()
        self.assertEqual(past_plan.status, "closed")

    def test_customer_role_cannot_manage_plans(self):
        """FR-06: Customer accounts cannot create, edit, or delete plans."""
        self.client.force_login(self.customer_user)

        create_res = self.client.get(reverse("plan_create"))
        self.assertRedirects(create_res, reverse("plan_list"))

        edit_res = self.client.get(reverse("plan_edit", args=[self.plan.id]))
        self.assertRedirects(edit_res, reverse("plan_list"))

        delete_res = self.client.post(reverse("plan_delete", args=[self.plan.id]))
        self.assertRedirects(delete_res, reverse("plan_list"))
        self.assertTrue(SubscriptionPlan.objects.filter(id=self.plan.id).exists())


class QuotationModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            first_name="Acme",
            last_name="Corp",
            email="test@brightloop.com",
        )
        self.customer = CustomerProfile.objects.create(
            user=self.user,
            customer_type="business",
            company_name="Acme Corp",
            phone="+91 9876543210",
            address="123 Industrial Area, Bengaluru",
            gst_number="29AAACB1234F1Z5",
        )
        self.product = Product.objects.create(
            name="Brightloop Billing Pro",
            product_type="Software",
            sales_price=Decimal("1000.00"),
            cost_price=Decimal("400.00"),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            name="Enterprise Edition",
            additional_price=Decimal("500.00"),
        )
        self.plan = SubscriptionPlan.objects.create(
            name="Billing Annual Plan",
            product=self.product,
            price=Decimal("1500.00"),
            billing_frequency="yearly",
            min_quantity=1,
            start_date=date.today(),
            status="active",
        )

    def test_create_quotation_template_and_items(self):
        """FR-19: Reusable quotation template with predefined items."""
        template = QuotationTemplate.objects.create(
            name="Standard SaaS Starter",
            description="Pre-configured bundle for small enterprise clients",
        )
        item = QuotationTemplateItem.objects.create(
            template=template,
            product=self.product,
            plan=self.plan,
            variant=self.variant,
            quantity=2,
            unit_price=Decimal("1500.00"),
        )
        self.assertEqual(template.items.count(), 1)
        self.assertEqual(item.total_price, Decimal("3000.00"))
        self.assertIn("Standard SaaS Starter", str(template))

    def test_create_quotation_and_items_with_tax(self):
        """FR-20: Quotation creation with lines, subtotal, 18% GST, and total."""
        quotation = Quotation.objects.create(
            quotation_number="BL-QTE-2026-0001",
            customer=self.customer,
            quotation_date=date.today(),
            valid_until=date.today() + timedelta(days=30),
            status="draft",
            subtotal=Decimal("3000.00"),
            tax_amount=Decimal("540.00"),
            total_amount=Decimal("3540.00"),
            created_by=self.user,
        )
        item = QuotationItem.objects.create(
            quotation=quotation,
            product=self.product,
            plan=self.plan,
            variant=self.variant,
            quantity=2,
            unit_price=Decimal("1500.00"),
            total_price=Decimal("3000.00"),
        )
        self.assertEqual(quotation.items.count(), 1)
        self.assertEqual(quotation.total_amount, Decimal("3540.00"))
        self.assertFalse(quotation.is_expired)

    def test_quotation_validity_and_expiration(self):
        """FR-21: Quotation validity period and automatic expiration detection."""
        active_quote = Quotation.objects.create(
            quotation_number="BL-QTE-2026-0002",
            customer=self.customer,
            quotation_date=date.today(),
            valid_until=date.today() + timedelta(days=15),
            status="sent",
        )
        self.assertFalse(active_quote.is_expired)

        expired_quote = Quotation.objects.create(
            quotation_number="BL-QTE-2026-0003",
            customer=self.customer,
            quotation_date=date.today() - timedelta(days=40),
            valid_until=date.today() - timedelta(days=1),
            status="sent",
        )
        self.assertTrue(expired_quote.is_expired)

    def test_quotation_conversion_eligibility(self):
        """FR-22: Eligibility check for quotation conversion."""
        quote = Quotation.objects.create(
            quotation_number="BL-QTE-2026-0004",
            customer=self.customer,
            quotation_date=date.today(),
            valid_until=date.today() + timedelta(days=10),
            status="accepted",
        )
        self.assertTrue(quote.is_eligible_for_conversion)

        # Draft is eligible (can be converted directly by staff)
        quote.status = "draft"
        self.assertTrue(quote.is_eligible_for_conversion)

        # Rejected is not eligible
        quote.status = "rejected"
        self.assertFalse(quote.is_eligible_for_conversion)

        # Converted is not eligible
        quote.status = "converted"
        self.assertFalse(quote.is_eligible_for_conversion)

        # Expired is not eligible
        quote.status = "accepted"
        quote.valid_until = date.today() - timedelta(days=1)
        self.assertFalse(quote.is_eligible_for_conversion)


class QuotationViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_group, _ = Group.objects.get_or_create(name="Admin")
        self.staff_group, _ = Group.objects.get_or_create(name="Staff")
        self.customer_group, _ = Group.objects.get_or_create(name="Customer")

        # Admin User
        self.admin_user = User.objects.create_superuser(
            username="adminuser",
            email="admin@brightloop.com",
            password="AdminPass123!",
        )

        # Customer A
        self.customer_user_a = User.objects.create_user(
            username="cust_a",
            first_name="Alpha",
            last_name="Corp",
            email="cust_a@alpha.com",
            password="CustPass123!",
        )
        self.customer_user_a.groups.add(self.customer_group)
        self.customer_profile_a = CustomerProfile.objects.create(
            user=self.customer_user_a,
            customer_type="business",
            company_name="Alpha Corp",
            phone="+91 9111111111",
            address="Alpha Tower, MG Road, Bengaluru",
            gst_number="29ALPHA1234F1Z1",
        )

        # Customer B
        self.customer_user_b = User.objects.create_user(
            username="cust_b",
            first_name="Beta",
            last_name="Ltd",
            email="cust_b@beta.com",
            password="CustPass123!",
        )
        self.customer_user_b.groups.add(self.customer_group)
        self.customer_profile_b = CustomerProfile.objects.create(
            user=self.customer_user_b,
            customer_type="business",
            company_name="Beta Ltd",
            phone="+91 9222222222",
            address="Beta Hub, Electronic City, Bengaluru",
            gst_number="29BETA1234F1Z2",
        )

        # Product & Plan
        self.product = Product.objects.create(
            name="Brightloop Analytics",
            product_type="Software",
            sales_price=Decimal("2000.00"),
            cost_price=Decimal("800.00"),
        )
        self.plan = SubscriptionPlan.objects.create(
            name="Analytics Monthly",
            product=self.product,
            price=Decimal("2000.00"),
            billing_frequency="monthly",
            min_quantity=1,
            start_date=date.today(),
            status="active",
        )

        # Quotation for Customer A
        self.quote_a = Quotation.objects.create(
            quotation_number="BL-QTE-2026-0010",
            customer=self.customer_profile_a,
            quotation_date=date.today(),
            valid_until=date.today() + timedelta(days=30),
            status="sent",
            subtotal=Decimal("2000.00"),
            tax_amount=Decimal("360.00"),
            total_amount=Decimal("2360.00"),
            created_by=self.admin_user,
        )
        QuotationItem.objects.create(
            quotation=self.quote_a,
            product=self.product,
            plan=self.plan,
            quantity=1,
            unit_price=Decimal("2000.00"),
            total_price=Decimal("2000.00"),
        )

        # Quotation for Customer B
        self.quote_b = Quotation.objects.create(
            quotation_number="BL-QTE-2026-0020",
            customer=self.customer_profile_b,
            quotation_date=date.today(),
            valid_until=date.today() + timedelta(days=30),
            status="draft",
            subtotal=Decimal("4000.00"),
            tax_amount=Decimal("720.00"),
            total_amount=Decimal("4720.00"),
            created_by=self.admin_user,
        )

    def test_quotation_list_staff(self):
        """Staff can view all quotations and summary KPIs."""
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse("quotation_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/quotation/q_list.html")
        self.assertContains(response, "BL-QTE-2026-0010")
        self.assertContains(response, "BL-QTE-2026-0020")
        self.assertEqual(response.context["total_quotes"], 2)

    def test_quotation_list_customer_isolation(self):
        """FR-18: Customer A only sees their own quotations, not Customer B's."""
        self.client.force_login(self.customer_user_a)
        response = self.client.get(reverse("quotation_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "BL-QTE-2026-0010")
        self.assertNotContains(response, "BL-QTE-2026-0020")
        self.assertEqual(response.context["total_quotes"], 1)

    def test_quotation_create_get(self):
        """Staff can access quotation creation form."""
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse("quotation_create"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/quotation/q_add.html")
        self.assertContains(response, "Create quotation")

    def test_quotation_create_post_valid(self):
        """FR-20: Creating a quotation calculates 18% GST and saves line items."""
        self.client.force_login(self.admin_user)
        payload = {
            "customer_id": str(self.customer_profile_a.id),
            "valid_until": (date.today() + timedelta(days=20)).isoformat(),
            "notes": "Annual enterprise contract with special onboarding support.",
            "product_id": [str(self.product.id)],
            "plan_id": [str(self.plan.id)],
            "variant_id": [""],
            "quantity": ["3"],
            "unit_price": ["2000.00"],
        }
        response = self.client.post(reverse("quotation_create"), data=payload)
        self.assertEqual(response.status_code, 302)

        # Verify created quotation in DB
        created_quote = Quotation.objects.filter(customer=self.customer_profile_a).order_by("-id").first()
        self.assertIsNotNone(created_quote)
        self.assertEqual(created_quote.items.count(), 1)
        self.assertEqual(created_quote.subtotal, Decimal("6000.00"))
        self.assertEqual(created_quote.tax_amount, Decimal("1080.00"))  # 18% GST
        self.assertEqual(created_quote.total_amount, Decimal("7080.00"))

    def test_quotation_create_unauthorized_customer(self):
        """Customer cannot create quotations."""
        self.client.force_login(self.customer_user_a)
        response = self.client.get(reverse("quotation_create"))
        self.assertRedirects(response, reverse("quotation_list"))

    def test_quotation_detail_owner_can_view(self):
        """Customer A can view their own quotation detail sheet."""
        self.client.force_login(self.customer_user_a)
        response = self.client.get(reverse("quotation_detail", args=[self.quote_a.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/quotation/q_detail.html")
        self.assertContains(response, "BL-QTE-2026-0010")
        self.assertContains(response, "Brightloop Analytics")

    def test_quotation_detail_other_customer_blocked(self):
        """FR-18 Customer Isolation: Customer B cannot view Customer A's quotation."""
        self.client.force_login(self.customer_user_b)
        response = self.client.get(reverse("quotation_detail", args=[self.quote_a.id]))
        self.assertRedirects(response, reverse("quotation_list"))

    def test_quotation_status_action_send_accept_reject(self):
        """Staff can update quotation status."""
        self.client.force_login(self.admin_user)

        # Mark as sent
        self.client.post(reverse("quotation_status_action", args=[self.quote_b.id]), data={"action": "send"})
        self.quote_b.refresh_from_db()
        self.assertEqual(self.quote_b.status, "sent")

        # Mark as accepted
        self.client.post(reverse("quotation_status_action", args=[self.quote_b.id]), data={"action": "accept"})
        self.quote_b.refresh_from_db()
        self.assertEqual(self.quote_b.status, "accepted")

        # Mark as rejected
        self.client.post(reverse("quotation_status_action", args=[self.quote_b.id]), data={"action": "reject"})
        self.quote_b.refresh_from_db()
        self.assertEqual(self.quote_b.status, "rejected")

    def test_quotation_convert_to_subscription(self):
        """FR-22: Convert quotation to active subscription and copy line items."""
        self.client.force_login(self.admin_user)
        self.quote_a.status = "accepted"
        self.quote_a.save()

        response = self.client.post(reverse("quotation_convert", args=[self.quote_a.id]))
        self.assertEqual(response.status_code, 302)

        self.quote_a.refresh_from_db()
        self.assertEqual(self.quote_a.status, "converted")
        self.assertTrue(hasattr(self.quote_a, "converted_subscription"))
        subscription = self.quote_a.converted_subscription
        self.assertIsNotNone(subscription)
        self.assertEqual(subscription.customer, self.customer_profile_a)
        self.assertEqual(subscription.status, "active")
        self.assertEqual(subscription.subtotal, Decimal("2000.00"))
        self.assertEqual(subscription.total_amount, Decimal("2360.00"))
        self.assertEqual(subscription.items.count(), 1)
        self.assertEqual(subscription.plan, self.plan)
        sub_item = subscription.items.first()
        self.assertEqual(sub_item.product, self.product)

    def test_quotation_convert_expired_blocked(self):
        """FR-21 & FR-22: Cannot convert expired quotations."""
        self.client.force_login(self.admin_user)
        self.quote_a.status = "accepted"
        self.quote_a.valid_until = date.today() - timedelta(days=2)
        self.quote_a.save()

        response = self.client.post(reverse("quotation_convert", args=[self.quote_a.id]))
        self.assertEqual(response.status_code, 302)
        self.quote_a.refresh_from_db()
        self.assertNotEqual(self.quote_a.status, "converted")

    def test_quotation_template_api(self):
        """Quotation template API endpoint returns pre-configured lines."""
        template = QuotationTemplate.objects.create(name="Enterprise Standard")
        QuotationTemplateItem.objects.create(
            template=template,
            product=self.product,
            plan=self.plan,
            quantity=5,
            unit_price=Decimal("1800.00"),
        )
        response = self.client.get(reverse("quotation_template_api", args=[template.id]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["quantity"], 5)
        self.assertEqual(data["items"][0]["unit_price"], "1800.00")



