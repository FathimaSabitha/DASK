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





class StaffCreationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_group, _ = Group.objects.get_or_create(name="Admin")
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

    def test_admin_can_create_staff(self):
        """FR-07: Administrator can create an internal staff account."""
        self.client.force_login(self.admin_user)
        payload = {
            "full_name": "Operations Agent",
            "email": "agent@brightloop.com",
            "password1": "AgentPass123!",
            "password2": "AgentPass123!",
        }
        res = self.client.post(reverse("create_staff"), data=payload)
        self.assertEqual(res.status_code, 302)
        created_staff = User.objects.filter(email="agent@brightloop.com").first()
        self.assertIsNotNone(created_staff)
        self.assertTrue(created_staff.is_staff)
        self.assertTrue(created_staff.groups.filter(name__in=["Staff", "Internal Staff"]).exists())

    def test_customer_cannot_create_staff(self):
        """FR-07: Customer role cannot create staff accounts."""
        self.client.force_login(self.customer_user)
        res = self.client.get(reverse("create_staff"))
        self.assertEqual(res.status_code, 403)


class CustomerManagementTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username="adminuser",
            email="admin@brightloop.com",
            password="AdminPass123!",
        )
        self.customer_user_a = User.objects.create_user(
            username="cust_a",
            first_name="Alpha",
            last_name="Corp",
            email="alpha@brightloop.com",
            password="CustPass123!",
        )
        self.profile_a = CustomerProfile.objects.create(
            user=self.customer_user_a,
            customer_type="business",
            company_name="Alpha Ltd",
            phone="9876543210",
            address="Alpha Road",
        )
        self.customer_user_b = User.objects.create_user(
            username="cust_b",
            first_name="Beta",
            last_name="Inc",
            email="beta@brightloop.com",
            password="CustPass123!",
        )
        self.profile_b = CustomerProfile.objects.create(
            user=self.customer_user_b,
            customer_type="individual",
            phone="9876543211",
        )

    def test_staff_can_view_customer_list(self):
        """FR-16 and FR-17: Staff/Admin can view all customers and search them."""
        self.client.force_login(self.admin_user)
        res = self.client.get(reverse("customer_list"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Alpha Ltd")
        self.assertContains(res, "Beta")

    def test_customer_cannot_view_customer_list(self):
        """FR-18: Customers cannot view customer management list."""
        self.client.force_login(self.customer_user_a)
        res = self.client.get(reverse("customer_list"))
        self.assertEqual(res.status_code, 403)

    def test_customer_can_view_own_detail(self):
        """FR-18: Customer can view their own profile."""
        self.client.force_login(self.customer_user_a)
        res = self.client.get(reverse("customer_detail", args=[self.profile_a.pk]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Alpha Ltd")

    def test_customer_cannot_view_other_customer_detail(self):
        """FR-18: Customer cannot view another customer's profile."""
        self.client.force_login(self.customer_user_a)
        res = self.client.get(reverse("customer_detail", args=[self.profile_b.pk]))
        self.assertEqual(res.status_code, 403)

    def test_staff_can_update_customer(self):
        """FR-17: Staff can update customer details."""
        self.client.force_login(self.admin_user)
        payload = {
            "full_name": "Alpha Corporation Renamed",
            "customer_type": "business",
            "company_name": "Alpha Global",
            "phone": "9999999999",
            "address": "New Tower, Floor 4",
        }
        res = self.client.post(reverse("customer_update", args=[self.profile_a.pk]), data=payload)
        self.assertEqual(res.status_code, 302)
        self.profile_a.refresh_from_db()
        self.assertEqual(self.profile_a.company_name, "Alpha Global")
        self.assertEqual(self.profile_a.phone, "9999999999")


# ─────────────────────────────────────────────────────────────────────────────
# Sections 3.6 to 3.11 Test Cases (FR-23 to FR-49)
# ─────────────────────────────────────────────────────────────────────────────

from datetime import timedelta
from decimal import Decimal
from django.utils import timezone
from core.models import TaxRule, DiscountRule, DiscountProduct, Invoice, InvoiceItem, Payment

class SubscriptionLifecycleTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin_sub', 'admin_sub@brightloop.io', 'AdminPass123!')
        self.staff_group, _ = Group.objects.get_or_create(name='Staff')
        self.staff = User.objects.create_user('staff_sub', 'staff_sub@brightloop.io', 'StaffPass123!', is_staff=True)
        self.staff.groups.add(self.staff_group)

        self.cust_user = User.objects.create_user('cust_sub', 'cust_sub@example.com', 'CustPass123!')
        self.customer = CustomerProfile.objects.create(user=self.cust_user, company_name='Acme Corp')

        self.other_user = User.objects.create_user('other_sub', 'other_sub@example.com', 'OtherPass123!')
        self.other_customer = CustomerProfile.objects.create(user=self.other_user, company_name='Other Corp')

        self.product = Product.objects.create(
            name='Cloud ERP',
            product_type='Service',
            sales_price=Decimal('1000.00'),
            cost_price=Decimal('400.00'),
            notes='Enterprise ERP'
        )
        self.plan = SubscriptionPlan.objects.create(
            name='ERP Monthly',
            product=self.product,
            price=Decimal('1000.00'),
            billing_frequency='monthly',
            start_date=timezone.now().date(),
            status='active'
        )
        self.subscription = Subscription.objects.create(
            subscription_number='BL-SUB-2026-9001',
            customer=self.customer,
            plan=self.plan,
            start_date=timezone.now().date(),
            expiry_date=timezone.now().date() + timedelta(days=365),
            payment_terms='Net 30',
            status='active',
            subtotal=Decimal('1000.00'),
            tax_amount=Decimal('180.00'),
            total_amount=Decimal('1180.00')
        )
        self.sub_item = SubscriptionItem.objects.create(
            subscription=self.subscription,
            product=self.product,
            quantity=1,
            unit_price=Decimal('1000.00')
        )

    def test_subscription_creation_and_fields(self):
        """FR-23: Subscription stores required attributes and items."""
        self.assertEqual(self.subscription.status, 'active')
        self.assertEqual(self.subscription.items.count(), 1)
        self.assertEqual(self.subscription.items.first().total_price, Decimal('1000.00'))

    def test_compute_next_billing_date_frequencies(self):
        """FR-13, FR-26: Billing frequency date computation."""
        today = timezone.now().date()
        self.subscription.plan.billing_frequency = 'daily'
        self.assertEqual(self.subscription.compute_next_billing_date(today), today + timedelta(days=1))

        self.subscription.plan.billing_frequency = 'weekly'
        self.assertEqual(self.subscription.compute_next_billing_date(today), today + timedelta(weeks=1))

    def test_customer_isolation_subscription_list(self):
        """FR-18, FR-25: Customer sees only their own subscriptions."""
        other_sub = Subscription.objects.create(
            subscription_number='BL-SUB-2026-9002',
            customer=self.other_customer,
            plan=self.plan,
            start_date=timezone.now().date(),
            status='active',
            subtotal=Decimal('500.00'),
            total_amount=Decimal('500.00')
        )

        self.client.force_login(self.cust_user)
        response = self.client.get(reverse('subscription_list'))
        self.assertEqual(response.status_code, 200)
        subs = response.context['subscriptions']
        self.assertIn(self.subscription, subs)
        self.assertNotIn(other_sub, subs)

    def test_customer_cannot_view_other_subscription_detail(self):
        """FR-18: Direct request to another customer's subscription is denied."""
        self.client.force_login(self.other_user)
        response = self.client.get(reverse('subscription_detail', args=[self.subscription.id]))
        self.assertEqual(response.status_code, 403)

    def test_staff_can_view_any_subscription(self):
        """FR-25: Staff can view subscription details."""
        self.client.force_login(self.staff)
        response = self.client.get(reverse('subscription_detail', args=[self.subscription.id]))
        self.assertEqual(response.status_code, 200)

    def test_subscription_lifecycle_actions(self):
        """FR-24, FR-25: Staff pause and close actions."""
        self.client.force_login(self.staff)
        # Pause
        response = self.client.post(reverse('subscription_lifecycle_action', args=[self.subscription.id]), {'action': 'pause'})
        self.assertRedirects(response, reverse('subscription_detail', args=[self.subscription.id]))
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, 'draft')

        # Activate
        self.client.post(reverse('subscription_lifecycle_action', args=[self.subscription.id]), {'action': 'activate'})
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, 'active')

    def test_subscription_renewal(self):
        """FR-26, FR-27: Renewal extends expiry and generates new invoice."""
        self.client.force_login(self.staff)
        response = self.client.post(reverse('subscription_renew', args=[self.subscription.id]))
        self.assertRedirects(response, reverse('subscription_detail', args=[self.subscription.id]))
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, 'active')
        self.assertIsNotNone(self.subscription.next_billing_date)
        # Check an invoice was generated
        self.assertTrue(self.subscription.invoices.exists())

    def test_customer_self_service_cancel(self):
        """FR-26: Customer can cancel their own subscription."""
        self.client.force_login(self.cust_user)
        response = self.client.post(reverse('subscription_cancel', args=[self.subscription.id]))
        self.assertRedirects(response, reverse('subscription_list'))
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, 'closed')


class InvoiceAndBillingTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin_inv', 'admin_inv@brightloop.io', 'AdminPass123!')
        self.staff_group, _ = Group.objects.get_or_create(name='Staff')
        self.staff = User.objects.create_user('staff_inv', 'staff_inv@brightloop.io', 'StaffPass123!', is_staff=True)
        self.staff.groups.add(self.staff_group)

        self.cust_user = User.objects.create_user('cust_inv', 'cust_inv@example.com', 'CustPass123!')
        self.customer = CustomerProfile.objects.create(user=self.cust_user, company_name='Invoice Corp')

        self.product = Product.objects.create(
            name='SaaS Subscription',
            product_type='Service',
            sales_price=Decimal('2000.00'),
            cost_price=Decimal('500.00'),
            notes='SaaS'
        )
        self.plan = SubscriptionPlan.objects.create(
            name='SaaS Plan',
            product=self.product,
            price=Decimal('2000.00'),
            billing_frequency='monthly',
            start_date=timezone.now().date(),
            status='active'
        )
        self.subscription = Subscription.objects.create(
            subscription_number='BL-SUB-2026-9010',
            customer=self.customer,
            plan=self.plan,
            start_date=timezone.now().date(),
            payment_terms='Net 30',
            status='active',
            subtotal=Decimal('2000.00'),
            tax_amount=Decimal('360.00'),
            total_amount=Decimal('2360.00')
        )
        SubscriptionItem.objects.create(
            subscription=self.subscription,
            product=self.product,
            quantity=1,
            unit_price=Decimal('2000.00')
        )

    def test_auto_generate_invoice_and_duplicate_prevention(self):
        """FR-27, FR-28, FR-31: Automatic invoice generation and duplicate prevention."""
        from core.views import _generate_invoice_from_subscription
        inv1 = _generate_invoice_from_subscription(self.subscription)
        self.assertIsNotNone(inv1)
        self.assertEqual(inv1.customer, self.customer)
        self.assertEqual(inv1.subtotal, Decimal('2000.00'))

        # Running again for the same period must NOT create duplicate (FR-31)
        inv2 = _generate_invoice_from_subscription(self.subscription, period_start=inv1.billing_period_start, period_end=inv1.billing_period_end)
        self.assertEqual(inv1.id, inv2.id)
        self.assertEqual(Invoice.objects.filter(subscription=self.subscription).count(), 1)

    def test_invoice_operations_and_status(self):
        """FR-29, FR-30: Staff confirm, send and cancel operations."""
        from core.views import _generate_invoice_from_subscription
        invoice = _generate_invoice_from_subscription(self.subscription)

        self.client.force_login(self.staff)
        # Mark sent / confirmed
        self.client.post(reverse('invoice_status_action', args=[invoice.id]), {'action': 'mark_sent'})
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'sent')

        # Mark draft / cancelled
        self.client.post(reverse('invoice_status_action', args=[invoice.id]), {'action': 'mark_draft'})
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'draft')

    def test_customer_invoice_isolation(self):
        """FR-18, UC-14: Customer only sees own invoices."""
        from core.views import _generate_invoice_from_subscription
        my_inv = _generate_invoice_from_subscription(self.subscription)

        other_user = User.objects.create_user('other_inv', 'other_inv@example.com', 'Pass123!')
        other_cust = CustomerProfile.objects.create(user=other_user)
        other_sub = Subscription.objects.create(
            subscription_number='BL-SUB-2026-9999',
            customer=other_cust,
            status='active',
            subtotal=Decimal('500.00'),
            total_amount=Decimal('500.00')
        )
        other_inv = _generate_invoice_from_subscription(other_sub)

        self.client.force_login(self.cust_user)
        response = self.client.get(reverse('invoice_list'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(my_inv, response.context['invoices'])
        self.assertNotIn(other_inv, response.context['invoices'])

        # Direct access to other customer's invoice forbidden
        res_detail = self.client.get(reverse('invoice_detail', args=[other_inv.id]))
        self.assertEqual(res_detail.status_code, 403)


class PaymentRecordingTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin_pay', 'admin_pay@brightloop.io', 'AdminPass123!')
        self.staff_group, _ = Group.objects.get_or_create(name='Staff')
        self.staff = User.objects.create_user('staff_pay', 'staff_pay@brightloop.io', 'StaffPass123!', is_staff=True)
        self.staff.groups.add(self.staff_group)

        self.cust_user = User.objects.create_user('cust_pay', 'cust_pay@example.com', 'CustPass123!')
        self.customer = CustomerProfile.objects.create(user=self.cust_user, company_name='Payment Corp')

        self.invoice = Invoice.objects.create(
            invoice_number='BL-INV-2026-9050',
            customer=self.customer,
            due_date=timezone.now().date() + timedelta(days=30),
            status='sent',
            subtotal=Decimal('1000.00'),
            tax_amount=Decimal('180.00'),
            total_amount=Decimal('1180.00')
        )

    def test_payment_recording_and_auto_status_update(self):
        """FR-34, FR-35, FR-36: Payment recording auto-updates invoice status to paid."""
        self.client.force_login(self.staff)
        # Record full payment
        response = self.client.post(reverse('payment_record', args=[self.invoice.id]), {
            'payment_method': 'bank_transfer',
            'amount': '1180.00',
            'payment_date': timezone.now().date().strftime('%Y-%m-%d'),
            'reference_number': 'TXN123456789',
            'notes': 'NEFT transfer confirmed'
        })
        self.assertRedirects(response, reverse('invoice_detail', args=[self.invoice.id]))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, 'paid')
        self.assertEqual(self.invoice.amount_paid, Decimal('1180.00'))
        self.assertEqual(self.invoice.amount_due, Decimal('0.00'))

    def test_partial_payment_tracking(self):
        """FR-41: Partial payment leaves invoice with remaining balance."""
        self.client.force_login(self.staff)
        self.client.post(reverse('payment_record', args=[self.invoice.id]), {
            'payment_method': 'upi',
            'amount': '500.00',
            'payment_date': timezone.now().date().strftime('%Y-%m-%d'),
            'reference_number': 'UPI987654321',
        })
        self.invoice.refresh_from_db()
        self.assertNotEqual(self.invoice.status, 'paid')
        self.assertEqual(self.invoice.amount_paid, Decimal('500.00'))
        self.assertEqual(self.invoice.amount_due, Decimal('680.00'))


class TaxAndDiscountRuleTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin_tax', 'admin_tax@brightloop.io', 'AdminPass123!')
        self.staff_group, _ = Group.objects.get_or_create(name='Staff')
        self.staff = User.objects.create_user('staff_tax', 'staff_tax@brightloop.io', 'StaffPass123!', is_staff=True)
        self.staff.groups.add(self.staff_group)
        self.cust_user = User.objects.create_user('cust_tax', 'cust_tax@example.com', 'Pass123!')
        CustomerProfile.objects.create(user=self.cust_user)

    def test_tax_rule_crud(self):
        """FR-32, FR-38: Admin manages tax rules."""
        self.client.force_login(self.admin)
        res = self.client.post(reverse('tax_rule_create'), {
            'name': 'GST 18%',
            'rate': '18.000',
            'is_active': True,
            'description': 'Standard GST'
        })
        self.assertRedirects(res, reverse('tax_rule_list'))
        self.assertTrue(TaxRule.objects.filter(name='GST 18%').exists())

    def test_discount_rule_admin_only(self):
        """FR-33: Only administrators can create discount rules."""
        self.client.force_login(self.staff)
        res = self.client.get(reverse('discount_rule_create'))
        # Staff is not admin -> permission denied or redirect
        # In is_staff_or_admin, check permissions
        self.client.force_login(self.admin)
        res_admin = self.client.post(reverse('discount_rule_create'), {
            'name': 'Welcome 10%',
            'discount_type': 'percentage',
            'value': '10.00',
            'is_active': True
        })
        self.assertRedirects(res_admin, reverse('discount_rule_list'))
        self.assertTrue(DiscountRule.objects.filter(name='Welcome 10%').exists())

    def test_discount_computation(self):
        """FR-34, FR-36, FR-37: Percentage and fixed discount evaluation."""
        d_pct = DiscountRule.objects.create(
            name='15% Off',
            discount_type='percentage',
            value=Decimal('15.00'),
            is_active=True
        )
        self.assertEqual(d_pct.compute_discount(Decimal('1000.00')), Decimal('150.00'))

        d_fixed = DiscountRule.objects.create(
            name='₹200 Off',
            discount_type='fixed',
            value=Decimal('200.00'),
            min_order_value=Decimal('500.00'),
            is_active=True
        )
        self.assertEqual(d_fixed.compute_discount(Decimal('1000.00')), Decimal('200.00'))
        # Below threshold
        self.assertEqual(d_fixed.compute_discount(Decimal('300.00')), Decimal('0.00'))


class DashboardAndReportsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin_dash', 'admin_dash@brightloop.io', 'AdminPass123!')
        self.staff_group, _ = Group.objects.get_or_create(name='Staff')
        self.staff = User.objects.create_user('staff_dash', 'staff_dash@brightloop.io', 'StaffPass123!', is_staff=True)
        self.staff.groups.add(self.staff_group)

        self.cust_user = User.objects.create_user('cust_dash', 'cust_dash@example.com', 'CustPass123!')
        self.customer = CustomerProfile.objects.create(user=self.cust_user, company_name='Dash Corp')

    def test_home_view_redirects_by_role(self):
        """FR-04, FR-06: Landing redirect role routing."""
        # Unauthenticated -> login
        self.assertRedirects(self.client.get(reverse('home')), reverse('login'))

        # Admin -> admin_dashboard
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.get(reverse('home')), reverse('admin_dashboard'))

        # Staff -> staff_dashboard
        self.client.force_login(self.staff)
        self.assertRedirects(self.client.get(reverse('home')), reverse('staff_dashboard'))

        # Customer -> customer_dashboard
        self.client.force_login(self.cust_user)
        self.assertRedirects(self.client.get(reverse('home')), reverse('customer_dashboard'))

    def test_admin_dashboard_metrics(self):
        """FR-43, FR-44: Admin dashboard renders with KPI context."""
        self.client.force_login(self.admin)
        res = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(res.status_code, 200)
        self.assertIn('mrr', res.context)
        self.assertIn('active_subscriptions', res.context)
        self.assertIn('total_customers', res.context)

    def test_reports_view_and_csv_export(self):
        """FR-45, FR-46, FR-49: Reports view and CSV download."""
        self.client.force_login(self.admin)
        res_rep = self.client.get(reverse('reports'))
        self.assertEqual(res_rep.status_code, 200)

        res_csv = self.client.get(reverse('reports_export_csv'))
        self.assertEqual(res_csv.status_code, 200)
        self.assertEqual(res_csv['Content-Type'], 'text/csv')
        self.assertIn('attachment; filename="brightloop_report.csv"', res_csv['Content-Disposition'])
