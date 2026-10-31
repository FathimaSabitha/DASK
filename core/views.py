from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import csv

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum, Count
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import CustomerUpdateForm, LoginForm, RegistrationForm, StaffCreationForm
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


def is_product_admin(user):
    """
    Check if a user has administrator rights to manage products.
    """
    if not user.is_authenticated:
        return True
    if user.is_superuser or user.is_staff:
        return True
    if user.groups.filter(name__in=["Admin", "Administrator"]).exists():
        return True
    if user.groups.filter(name="Customer").exists():
        return False
    return True


def is_staff_or_admin(user):
    """
    Check if user has internal staff or administrator rights.
    """
    if not user.is_authenticated:
        return True
    if user.is_superuser or user.is_staff:
        return True
    if user.groups.filter(name__in=["Admin", "Administrator", "Staff", "Internal Staff"]).exists():
        return True
    return False


def home_view(request):
    """
    Entrypoint landing redirect based on authentication and user role (SRS Section 3.1, FR-04, FR-06).
    """
    if not request.user.is_authenticated:
        return redirect("login")
    if request.user.is_superuser or request.user.groups.filter(name__in=["Admin", "Administrator"]).exists():
        return redirect("admin_dashboard")
    if is_staff_or_admin(request.user):
        return redirect("staff_dashboard")
    return redirect("customer_dashboard")


def product_create(request):
    """Create a product in the catalogue along with any optional product variants (SRS FR-08, FR-10, FR-11)."""
    if not is_product_admin(request.user):
        messages.error(request, "You are not authorized to create products.")
        return redirect("product_list")

    if request.method == "POST":
        name = request.POST.get("productName", "").strip()
        product_type = request.POST.get("productType", "").strip()
        custom_type = request.POST.get("customProductType", "").strip()
        notes = request.POST.get("productNotes", "").strip()
        variant_names = request.POST.getlist("variant_name")
        variant_prices = request.POST.getlist("variant_additional_price")
        errors = {}

        if not name:
            errors["productName"] = "Enter a product name."
        elif len(name) > 80:
            errors["productName"] = "Product name cannot exceed 80 characters."

        if product_type == "Other":
            product_type = custom_type
        if not product_type:
            errors["productType"] = "Choose a product type."
        elif len(product_type) > 50:
            errors["productType"] = "Product type cannot exceed 50 characters."

        if not notes:
            errors["productNotes"] = "Add product notes so your team has the required context."
        elif len(notes) > 500:
            errors["productNotes"] = "Product notes cannot exceed 500 characters."

        def parse_price(field_name, label):
            raw = request.POST.get(field_name, "").strip()
            if not raw:
                errors[field_name] = f"Enter a valid {label} of ₹0 or more."
                return None
            try:
                val = Decimal(raw)
                if val < 0:
                    raise InvalidOperation
                return val
            except (InvalidOperation, ValueError):
                errors[field_name] = f"Enter a valid {label} of ₹0 or more."
                return None

        sales_price = parse_price("salesPrice", "sales price")
        cost_price = parse_price("costPrice", "cost price")

        variants = []
        if len(variant_names) != len(variant_prices):
            errors["variants"] = "Variant details could not be saved. Please try again."
        else:
            seen_variant_names = set()
            for variant_name, raw_price in zip(variant_names, variant_prices):
                variant_name = variant_name.strip()
                if not variant_name:
                    errors["variants"] = "Give every variant a brand or configuration name."
                    break
                if variant_name.lower() in seen_variant_names:
                    errors["variants"] = f"Variant '{variant_name}' is added more than once."
                    break
                seen_variant_names.add(variant_name.lower())
                try:
                    raw_p = str(raw_price).strip() if str(raw_price).strip() else "0"
                    additional_price = Decimal(raw_p)
                    if additional_price < 0:
                        raise InvalidOperation
                except (InvalidOperation, ValueError):
                    errors["variants"] = "Each variant needs a valid additional price of 0 or more."
                    break
                variants.append((variant_name, additional_price))

        if name and Product.objects.filter(name__iexact=name).exists():
            errors["productName"] = "A product with this name already exists."

        is_ajax = (
            request.headers.get("x-requested-with") == "XMLHttpRequest"
            or "application/json" in request.headers.get("Accept", "")
        )

        if errors:
            if is_ajax:
                return JsonResponse({"success": False, "errors": errors}, status=400)
            return render(
                request,
                "core/products/prod_add.html",
                {"errors": errors, "posted": request.POST},
            )

        try:
            with transaction.atomic():
                product = Product.objects.create(
                    name=name,
                    product_type=product_type,
                    sales_price=sales_price,
                    cost_price=cost_price,
                    notes=notes,
                )
                ProductVariant.objects.bulk_create([
                    ProductVariant(
                        product=product,
                        name=variant_name,
                        additional_price=additional_price,
                    )
                    for variant_name, additional_price in variants
                ])
        except IntegrityError:
            errors["productName"] = "A product with this name already exists."
            if is_ajax:
                return JsonResponse({"success": False, "errors": errors}, status=400)
            return render(
                request,
                "core/products/prod_add.html",
                {"errors": errors, "posted": request.POST},
            )

        success_msg = f"{product.name} is ready for your catalogue."
        messages.success(request, success_msg)

        if is_ajax:
            return JsonResponse({
                "success": True,
                "message": f"{product.name} and {len(variants)} variant{'s' if len(variants) != 1 else ''} are ready for your catalogue.",
                "redirect_url": reverse("product_list"),
                "product_id": product.id,
            })

        return redirect("product_list")

    return render(request, "core/products/prod_add.html")


def product_list(request):
    """Display catalogue items with their prices, cost, notes, and variants (SRS FR-08, FR-09)."""
    products = Product.objects.prefetch_related("variants").all()
    user_is_admin = is_product_admin(request.user)
    return render(
        request,
        "core/products/prod_list.html",
        {
            "products": products,
            "user_is_admin": user_is_admin,
        },
    )


def product_userlist(request):
    """
    Official customer-facing product catalogue and printable rate schedule.
    Accessible without login restriction for official customer presentation and printing.
    """
    search_query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()

    products = Product.objects.prefetch_related("variants").all()

    if search_query:
        products = products.filter(
            Q(name__icontains=search_query)
            | Q(notes__icontains=search_query)
            | Q(product_type__icontains=search_query)
            | Q(variants__name__icontains=search_query)
        ).distinct()

    if category and category.lower() != "all":
        products = products.filter(product_type__iexact=category)

    # Distinct categories for filtering
    raw_categories = Product.objects.exclude(product_type="").values_list("product_type", flat=True)
    all_categories = sorted(list({c.strip() for c in raw_categories if c.strip()}))

    total_products = Product.objects.count()
    total_variants = ProductVariant.objects.count()

    context = {
        "products": products,
        "total_products": total_products,
        "total_variants": total_variants,
        "categories": all_categories,
        "search_query": search_query,
        "selected_category": category,
        "generated_date": timezone.now(),
        "user_is_admin": is_product_admin(request.user),
    }
    return render(request, "core/products/prod_userlist.html", context)


def product_edit(request, product_id):
    """Modify an existing product and its variants (SRS FR-09, FR-10, FR-11)."""
    if not is_product_admin(request.user):
        messages.error(request, "You are not authorized to modify products.")
        return redirect("product_list")

    product = get_object_or_404(Product, id=product_id)
    existing_variants = product.variants.all()

    if request.method == "POST":
        name = request.POST.get("productName", "").strip()
        product_type = request.POST.get("productType", "").strip()
        notes = request.POST.get("productNotes", "").strip()
        errors = {}

        # Validate product details
        if not name:
            errors["productName"] = "Enter a product name."
        elif len(name) > 80:
            errors["productName"] = "Product name cannot exceed 80 characters."
        elif Product.objects.filter(name__iexact=name).exclude(id=product.id).exists():
            errors["productName"] = "A product with this name already exists."

        if not product_type:
            errors["productType"] = "Enter a product type."
        elif len(product_type) > 50:
            errors["productType"] = "Product type cannot exceed 50 characters."

        if not notes:
            errors["productNotes"] = "Enter product notes."
        elif len(notes) > 500:
            errors["productNotes"] = "Product notes cannot exceed 500 characters."

        def parse_price(field, label):
            raw = request.POST.get(field, "").strip()
            if not raw:
                errors[field] = f"Enter a valid {label} of ₹0 or more."
                return None
            try:
                value = Decimal(raw)
                if value < 0:
                    raise InvalidOperation
                return value
            except (InvalidOperation, ValueError):
                errors[field] = f"Enter a valid {label} of ₹0 or more."
                return None

        sales_price = parse_price("salesPrice", "sales price")
        cost_price = parse_price("costPrice", "cost price")

        # Read variant information
        variant_ids = request.POST.getlist("variant_id")
        variant_names = request.POST.getlist("variant_name")
        variant_prices = request.POST.getlist("variant_additional_price")
        deleted_ids = set(request.POST.getlist("variant_delete_ids"))

        valid_variant_ids = set(str(v.id) for v in existing_variants)
        if not deleted_ids.issubset(valid_variant_ids):
            errors["variants"] = "Invalid variant deletion request."

        variants_to_save = []
        seen_names = set()

        if not (len(variant_ids) == len(variant_names) == len(variant_prices)):
            errors["variants"] = "Variant information is incomplete."
        else:
            for variant_id, variant_name, raw_price in zip(
                variant_ids, variant_names, variant_prices
            ):
                variant_id = str(variant_id).strip()

                # If this existing variant was marked for deletion, skip saving/validating it
                if variant_id and variant_id in deleted_ids:
                    continue

                variant_name = variant_name.strip()
                if not variant_name:
                    errors["variants"] = "Every variant needs a name."
                    break

                if variant_name.lower() in seen_names:
                    errors["variants"] = f"Variant '{variant_name}' is added more than once."
                    break
                seen_names.add(variant_name.lower())

                try:
                    p_str = str(raw_price).strip() if str(raw_price).strip() else "0"
                    additional_price = Decimal(p_str)
                    if additional_price < 0:
                        raise InvalidOperation
                except (InvalidOperation, ValueError):
                    errors["variants"] = "Enter a valid additional price for every variant."
                    break

                if variant_id:
                    variant_obj = existing_variants.filter(id=variant_id).first()
                    if variant_obj:
                        variants_to_save.append((variant_obj, variant_name, additional_price))
                    else:
                        errors["variants"] = "Invalid variant ID specified."
                        break
                else:
                    variants_to_save.append((None, variant_name, additional_price))

        # Save everything together inside an atomic transaction
        if not errors:
            try:
                with transaction.atomic():
                    product.name = name
                    product.product_type = product_type
                    product.sales_price = sales_price
                    product.cost_price = cost_price
                    product.notes = notes
                    product.save()

                    if deleted_ids:
                        product.variants.filter(id__in=deleted_ids).delete()

                    for variant_obj, variant_name, additional_price in variants_to_save:
                        if variant_obj:
                            variant_obj.name = variant_name
                            variant_obj.additional_price = additional_price
                            variant_obj.save()
                        else:
                            ProductVariant.objects.create(
                                product=product,
                                name=variant_name,
                                additional_price=additional_price,
                            )

                messages.success(request, f"{product.name} was updated successfully.")
                return redirect("product_list")

            except IntegrityError:
                errors["variants"] = "A product or variant with the same name already exists."

        return render(
            request,
            "core/products/prod_edit.html",
            {
                "product": product,
                "variants": existing_variants,
                "errors": errors,
                "posted": request.POST,
            },
        )

    return render(
        request,
        "core/products/prod_edit.html",
        {
            "product": product,
            "variants": existing_variants,
        },
    )


def product_delete(request, product_id):
    """Delete an existing product and its variants (Administrator only)."""
    if request.method != "POST":
        return redirect("product_list")

    if not is_product_admin(request.user):
        messages.error(request, "You are not authorized to delete products.")
        return redirect("product_list")

    product = get_object_or_404(Product, id=product_id)
    product_name = product.name
    product.delete()

    messages.success(
        request,
        f"{product_name} and its associated variants were deleted successfully."
    )
    return redirect("product_list")


def register(request):
    """Register a new customer account and assign to Customer group."""
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            customer_group, _ = Group.objects.get_or_create(name='Customer')
            user.groups.add(customer_group)
            messages.success(request, "Registration successful! You can now log in.")
            return redirect('login')
    else:
        form = RegistrationForm()

    return render(
        request,
        'core/authentication/registration.html',
        {'form': form},
    )


def login_view(request):
    """Authenticate and log in an existing user."""
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f"Welcome back, {user.first_name or user.username}!")
            if user.is_superuser or user.groups.filter(name__in=["Admin", "Administrator", "Staff", "Internal Staff"]).exists():
                return redirect('home')
            return redirect('product_userlist')
    else:
        form = LoginForm()

    return render(
        request,
        'core/authentication/login.html',
        {'form': form},
    )


def logout_view(request):
    """Log out current user."""
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect('login')


# ---------------------------------------------------------------------------
# Section 3.3 - Subscription Plan Management (FR-12 to FR-15)
# ---------------------------------------------------------------------------

def plan_list(request):
    """
    Display subscription plans, their pricing, frequency, and lifecycle status (SRS Section 3.3, FR-12 to FR-15).
    Enforces automatic closure when end date is reached (FR-15).
    """
    today = timezone.now().date()
    # Automatic closure of expired plans that have auto_close=True (FR-15)
    SubscriptionPlan.objects.filter(
        status="active",
        auto_close=True,
        end_date__lt=today,
    ).update(status="closed")

    plans = SubscriptionPlan.objects.select_related("product").all()

    # Search & filters
    q = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()
    frequency_filter = request.GET.get("frequency", "").strip()

    if q:
        plans = plans.filter(
            Q(name__icontains=q)
            | Q(product__name__icontains=q)
            | Q(description__icontains=q)
        )

    if status_filter and status_filter != "all":
        plans = plans.filter(status=status_filter)

    if frequency_filter and frequency_filter != "all":
        plans = plans.filter(billing_frequency=frequency_filter)

    # Metrics
    all_plans = SubscriptionPlan.objects.all()
    total_plans = all_plans.count()
    active_plans = all_plans.filter(status="active").count()
    paused_plans = all_plans.filter(status="paused").count()
    closed_plans = all_plans.filter(status="closed").count()

    user_is_admin = is_product_admin(request.user)

    return render(
        request,
        "core/plans/plan_list.html",
        {
            "plans": plans,
            "total_plans": total_plans,
            "active_plans": active_plans,
            "paused_plans": paused_plans,
            "closed_plans": closed_plans,
            "search_query": q,
            "status_filter": status_filter,
            "frequency_filter": frequency_filter,
            "user_is_admin": user_is_admin,
            "today": today,
        },
    )


def plan_create(request):
    """
    Create a new subscription plan associated with a product (SRS Section 3.3, FR-12, FR-13, FR-14).
    """
    if not is_product_admin(request.user):
        messages.error(request, "You are not authorized to create subscription plans.")
        return redirect("plan_list")

    products = Product.objects.all().order_by("name")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        product_id = request.POST.get("product_id", "").strip()
        raw_price = request.POST.get("price", "").strip()
        billing_frequency = request.POST.get("billing_frequency", "").strip().lower()
        raw_min_qty = request.POST.get("min_quantity", "1").strip()
        start_date_raw = request.POST.get("start_date", "").strip()
        end_date_raw = request.POST.get("end_date", "").strip()
        auto_close = request.POST.get("auto_close") == "on" or request.POST.get("auto_close") == "true"
        description = request.POST.get("description", "").strip()
        errors = {}

        if not name:
            errors["name"] = "Enter a plan name."
        elif len(name) > 100:
            errors["name"] = "Plan name cannot exceed 100 characters."
        elif SubscriptionPlan.objects.filter(name__iexact=name).exists():
            errors["name"] = "A subscription plan with this name already exists."

        product = None
        if not product_id:
            errors["product_id"] = "Select an associated product."
        else:
            try:
                product = Product.objects.get(id=product_id)
            except Product.DoesNotExist:
                errors["product_id"] = "Selected product does not exist."

        price = None
        if not raw_price:
            errors["price"] = "Enter a valid subscription price of ₹0 or more."
        else:
            try:
                price = Decimal(raw_price)
                if price < 0:
                    raise InvalidOperation
            except (InvalidOperation, ValueError):
                errors["price"] = "Enter a valid subscription price of ₹0 or more."

        valid_frequencies = ["daily", "weekly", "monthly", "yearly"]
        if billing_frequency not in valid_frequencies:
            errors["billing_frequency"] = "Select a valid billing frequency (daily, weekly, monthly, or yearly)."

        min_quantity = 1
        try:
            min_quantity = int(raw_min_qty)
            if min_quantity < 1:
                errors["min_quantity"] = "Minimum quantity must be at least 1."
        except ValueError:
            errors["min_quantity"] = "Enter a valid minimum quantity."

        start_date = None
        if not start_date_raw:
            errors["start_date"] = "Select an availability start date."
        else:
            try:
                start_date = datetime.strptime(start_date_raw, "%Y-%m-%d").date()
            except ValueError:
                errors["start_date"] = "Enter a valid start date (YYYY-MM-DD)."

        end_date = None
        if end_date_raw:
            try:
                end_date = datetime.strptime(end_date_raw, "%Y-%m-%d").date()
                if start_date and end_date < start_date:
                    errors["end_date"] = "Availability end date cannot be earlier than start date."
            except ValueError:
                errors["end_date"] = "Enter a valid end date (YYYY-MM-DD)."

        if len(description) > 500:
            errors["description"] = "Description cannot exceed 500 characters."

        if errors:
            return render(
                request,
                "core/plans/plan_add.html",
                {
                    "products": products,
                    "errors": errors,
                    "posted": request.POST,
                    "today": timezone.now().date().isoformat(),
                },
            )

        plan = SubscriptionPlan.objects.create(
            name=name,
            product=product,
            price=price,
            billing_frequency=billing_frequency,
            min_quantity=min_quantity,
            start_date=start_date,
            end_date=end_date,
            auto_close=auto_close,
            description=description,
            status="active",
        )
        messages.success(request, f"Subscription plan '{plan.name}' was created successfully.")
        return redirect("plan_list")

    return render(
        request,
        "core/plans/plan_add.html",
        {
            "products": products,
            "today": timezone.now().date().isoformat(),
        },
    )


def plan_edit(request, plan_id):
    """
    Modify an existing subscription plan (SRS Section 3.3, FR-14).
    """
    if not is_product_admin(request.user):
        messages.error(request, "You are not authorized to modify subscription plans.")
        return redirect("plan_list")

    plan = get_object_or_404(SubscriptionPlan, id=plan_id)
    products = Product.objects.all().order_by("name")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        product_id = request.POST.get("product_id", "").strip()
        raw_price = request.POST.get("price", "").strip()
        billing_frequency = request.POST.get("billing_frequency", "").strip().lower()
        raw_min_qty = request.POST.get("min_quantity", "1").strip()
        start_date_raw = request.POST.get("start_date", "").strip()
        end_date_raw = request.POST.get("end_date", "").strip()
        status = request.POST.get("status", plan.status).strip().lower()
        auto_close = request.POST.get("auto_close") == "on" or request.POST.get("auto_close") == "true"
        description = request.POST.get("description", "").strip()
        errors = {}

        if not name:
            errors["name"] = "Enter a plan name."
        elif len(name) > 100:
            errors["name"] = "Plan name cannot exceed 100 characters."
        elif SubscriptionPlan.objects.filter(name__iexact=name).exclude(id=plan.id).exists():
            errors["name"] = "A subscription plan with this name already exists."

        product = None
        if not product_id:
            errors["product_id"] = "Select an associated product."
        else:
            try:
                product = Product.objects.get(id=product_id)
            except Product.DoesNotExist:
                errors["product_id"] = "Selected product does not exist."

        price = None
        if not raw_price:
            errors["price"] = "Enter a valid subscription price of ₹0 or more."
        else:
            try:
                price = Decimal(raw_price)
                if price < 0:
                    raise InvalidOperation
            except (InvalidOperation, ValueError):
                errors["price"] = "Enter a valid subscription price of ₹0 or more."

        valid_frequencies = ["daily", "weekly", "monthly", "yearly"]
        if billing_frequency not in valid_frequencies:
            errors["billing_frequency"] = "Select a valid billing frequency."

        min_quantity = 1
        try:
            min_quantity = int(raw_min_qty)
            if min_quantity < 1:
                errors["min_quantity"] = "Minimum quantity must be at least 1."
        except ValueError:
            errors["min_quantity"] = "Enter a valid minimum quantity."

        start_date = None
        if not start_date_raw:
            errors["start_date"] = "Select an availability start date."
        else:
            try:
                start_date = datetime.strptime(start_date_raw, "%Y-%m-%d").date()
            except ValueError:
                errors["start_date"] = "Enter a valid start date (YYYY-MM-DD)."

        end_date = None
        if end_date_raw:
            try:
                end_date = datetime.strptime(end_date_raw, "%Y-%m-%d").date()
                if start_date and end_date < start_date:
                    errors["end_date"] = "Availability end date cannot be earlier than start date."
            except ValueError:
                errors["end_date"] = "Enter a valid end date (YYYY-MM-DD)."

        if status not in ["active", "paused", "closed"]:
            errors["status"] = "Select a valid status."

        if len(description) > 500:
            errors["description"] = "Description cannot exceed 500 characters."

        if errors:
            return render(
                request,
                "core/plans/plan_edit.html",
                {
                    "plan": plan,
                    "products": products,
                    "errors": errors,
                    "posted": request.POST,
                },
            )

        plan.name = name
        plan.product = product
        plan.price = price
        plan.billing_frequency = billing_frequency
        plan.min_quantity = min_quantity
        plan.start_date = start_date
        plan.end_date = end_date
        plan.status = status
        plan.auto_close = auto_close
        plan.description = description
        plan.save()

        messages.success(request, f"Plan '{plan.name}' was updated successfully.")
        return redirect("plan_list")

    return render(
        request,
        "core/plans/plan_edit.html",
        {
            "plan": plan,
            "products": products,
        },
    )


def plan_lifecycle_action(request, plan_id):
    """
    Perform lifecycle actions: pause, resume, close, renew (SRS Section 3.3, FR-15).
    """
    if not is_product_admin(request.user):
        messages.error(request, "You are not authorized to update plan lifecycle.")
        return redirect("plan_list")

    if request.method != "POST":
        return redirect("plan_list")

    plan = get_object_or_404(SubscriptionPlan, id=plan_id)
    action = request.POST.get("action", "").strip().lower()

    if action == "pause":
        plan.pause()
        messages.success(request, f"Plan '{plan.name}' has been paused. New subscriptions cannot select this plan.")
    elif action in ["resume", "activate"]:
        plan.resume()
        messages.success(request, f"Plan '{plan.name}' is now active and available.")
    elif action == "close":
        plan.close()
        messages.success(request, f"Plan '{plan.name}' has been closed.")
    elif action == "renew":
        new_end_date_raw = request.POST.get("new_end_date", "").strip()
        if not new_end_date_raw:
            messages.error(request, "A new end date is required to renew the plan.")
        else:
            try:
                new_date = datetime.strptime(new_end_date_raw, "%Y-%m-%d").date()
                if new_date < plan.start_date:
                    messages.error(request, "New end date cannot be earlier than plan start date.")
                else:
                    plan.renew(new_date)
                    messages.success(request, f"Plan '{plan.name}' renewed until {new_date.strftime('%B %d, %Y')}.")
            except ValueError:
                messages.error(request, "Invalid renewal date format.")

    return redirect("plan_list")


def plan_delete(request, plan_id):
    """Delete an existing subscription plan (Administrator only)."""
    if not is_product_admin(request.user):
        messages.error(request, "You are not authorized to delete subscription plans.")
        return redirect("plan_list")

    if request.method != "POST":
        return redirect("plan_list")

    plan = get_object_or_404(SubscriptionPlan, id=plan_id)
    plan_name = plan.name
    plan.delete()
    messages.success(request, f"Subscription plan '{plan_name}' was deleted.")
    return redirect("plan_list")


# ---------------------------------------------------------------------------
# Section 3.5 - Quotation Management (FR-19 to FR-22)
# ---------------------------------------------------------------------------

# (is_staff_or_admin defined at top of module)


def quotation_list(request):
    """
    Display quotations with status tracking, customer details, and action controls (SRS FR-20, FR-21, FR-18).
    Enforces Customer Data Privacy (FR-18).
    """
    today = timezone.now().date()
    # Auto-expire eligible past-due quotations
    Quotation.objects.filter(
        status__in=["draft", "sent"],
        valid_until__lt=today,
    ).update(status="expired")

    quotations = Quotation.objects.select_related("customer__user", "created_by", "template").prefetch_related("items").all()

    # FR-18 Customer Data Privacy check
    is_internal = is_staff_or_admin(request.user)
    if request.user.is_authenticated and not is_internal:
        # Customer sees only their own quotations
        quotations = quotations.filter(customer__user=request.user)

    # Search & status filtering (FR-48)
    q = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()

    if q:
        quotations = quotations.filter(
            Q(quotation_number__icontains=q)
            | Q(customer__user__email__icontains=q)
            | Q(customer__company_name__icontains=q)
            | Q(customer__user__first_name__icontains=q)
        )

    if status_filter and status_filter != "all":
        quotations = quotations.filter(status=status_filter)

    # Summary metrics
    base_qs = Quotation.objects.all() if is_internal else Quotation.objects.filter(customer__user=request.user)
    total_quotes = base_qs.count()
    pending_quotes = base_qs.filter(status__in=["draft", "sent"]).count()
    accepted_quotes = base_qs.filter(status="accepted").count()
    converted_quotes = base_qs.filter(status="converted").count()

    return render(
        request,
        "core/quotation/q_list.html",
        {
            "quotations": quotations,
            "total_quotes": total_quotes,
            "pending_quotes": pending_quotes,
            "accepted_quotes": accepted_quotes,
            "converted_quotes": converted_quotes,
            "search_query": q,
            "status_filter": status_filter,
            "is_internal": is_internal,
            "today": today,
        },
    )


def quotation_create(request):
    """
    Generate a quotation for a customer using an existing template or custom lines (SRS Section 3.5, FR-20, FR-21).
    """
    if not is_staff_or_admin(request.user):
        messages.error(request, "You are not authorized to create quotations.")
        return redirect("quotation_list")

    customers = CustomerProfile.objects.select_related("user").all()
    templates = QuotationTemplate.objects.prefetch_related("items__product", "items__plan").all()
    products = Product.objects.prefetch_related("variants", "plans").all()
    plans = SubscriptionPlan.objects.filter(status="active")

    if request.method == "POST":
        customer_id = request.POST.get("customer_id", "").strip()
        template_id = request.POST.get("template_id", "").strip()
        quotation_date_raw = request.POST.get("quotation_date", "").strip()
        validity_days = request.POST.get("validity_days", "30").strip()
        valid_until_raw = request.POST.get("valid_until", "").strip()
        notes = request.POST.get("notes", "").strip()

        # Dynamic line item arrays
        product_ids = request.POST.getlist("line_product_id") or request.POST.getlist("product_id")
        plan_ids = request.POST.getlist("line_plan_id") or request.POST.getlist("plan_id")
        variant_ids = request.POST.getlist("line_variant_id") or request.POST.getlist("variant_id")
        quantities = request.POST.getlist("line_quantity") or request.POST.getlist("quantity")
        unit_prices = request.POST.getlist("line_unit_price") or request.POST.getlist("unit_price")

        errors = {}

        customer = None
        if not customer_id:
            errors["customer_id"] = "Select a customer for this quotation."
        else:
            try:
                customer = CustomerProfile.objects.get(id=customer_id)
            except CustomerProfile.DoesNotExist:
                errors["customer_id"] = "Selected customer does not exist."

        template = None
        if template_id:
            try:
                template = QuotationTemplate.objects.get(id=template_id)
            except QuotationTemplate.DoesNotExist:
                pass

        today = timezone.now().date()
        quotation_date = today
        if quotation_date_raw:
            try:
                quotation_date = datetime.strptime(quotation_date_raw, "%Y-%m-%d").date()
            except ValueError:
                errors["quotation_date"] = "Invalid quotation date."

        valid_until = None
        if valid_until_raw:
            try:
                valid_until = datetime.strptime(valid_until_raw, "%Y-%m-%d").date()
                if valid_until < quotation_date:
                    errors["valid_until"] = "Valid until date cannot be earlier than quotation date."
            except ValueError:
                errors["valid_until"] = "Invalid validity end date."
        else:
            try:
                days = int(validity_days)
                valid_until = quotation_date + timedelta(days=days)
            except ValueError:
                valid_until = quotation_date + timedelta(days=30)

        # Validate line items
        lines_data = []
        if not product_ids:
            errors["lines"] = "At least one product or subscription line item is required."
        else:
            for i in range(len(product_ids)):
                p_id = product_ids[i].strip() if i < len(product_ids) else ""
                pl_id = plan_ids[i].strip() if i < len(plan_ids) else ""
                v_id = variant_ids[i].strip() if i < len(variant_ids) else ""
                raw_qty = quantities[i].strip() if i < len(quantities) else "1"
                raw_uprice = unit_prices[i].strip() if i < len(unit_prices) else "0"

                if not p_id:
                    continue

                try:
                    p_obj = Product.objects.get(id=p_id)
                except Product.DoesNotExist:
                    errors["lines"] = "One of the selected products does not exist."
                    continue

                pl_obj = None
                if pl_id:
                    pl_obj = SubscriptionPlan.objects.filter(id=pl_id).first()

                v_obj = None
                if v_id:
                    v_obj = ProductVariant.objects.filter(id=v_id).first()

                try:
                    qty = int(raw_qty)
                    if qty < 1:
                        raise ValueError
                except ValueError:
                    errors["lines"] = "Line quantity must be at least 1."
                    qty = 1

                try:
                    u_price = Decimal(raw_uprice)
                    if u_price < 0:
                        raise InvalidOperation
                except (InvalidOperation, ValueError):
                    errors["lines"] = "Unit price must be a valid positive amount."
                    u_price = Decimal("0.00")

                lines_data.append({
                    "product": p_obj,
                    "plan": pl_obj,
                    "variant": v_obj,
                    "quantity": qty,
                    "unit_price": u_price,
                    "description": f"{p_obj.name}{' - ' + v_obj.name if v_obj else ''}{' (' + pl_obj.name + ')' if pl_obj else ''}",
                })

        if not lines_data and "lines" not in errors:
            errors["lines"] = "Add at least one valid line item."

        if errors:
            return render(
                request,
                "core/quotation/q_add.html",
                {
                    "customers": customers,
                    "templates": templates,
                    "products": products,
                    "plans": plans,
                    "errors": errors,
                    "posted": request.POST,
                    "today": today.isoformat(),
                    "default_validity": (today + timedelta(days=30)).isoformat(),
                },
            )

        # Generate unique quotation number (BR-06, BR-07)
        year_str = str(quotation_date.year)
        quotation_number = f"BL-QTE-{year_str}-{Quotation.objects.count() + 101:04d}"

        try:
            with transaction.atomic():
                quotation = Quotation.objects.create(
                    quotation_number=quotation_number,
                    customer=customer,
                    template=template,
                    created_by=request.user if request.user.is_authenticated else None,
                    quotation_date=quotation_date,
                    valid_until=valid_until,
                    status="draft",
                    notes=notes,
                )

                for item in lines_data:
                    QuotationItem.objects.create(
                        quotation=quotation,
                        product=item["product"],
                        plan=item["plan"],
                        variant=item["variant"],
                        quantity=item["quantity"],
                        unit_price=item["unit_price"],
                        description=item["description"],
                    )

                quotation.update_totals()

            messages.success(request, f"Quotation {quotation.quotation_number} generated successfully.")
            return redirect("quotation_detail", quotation_id=quotation.id)

        except Exception as e:
            errors["general"] = f"Failed to save quotation: {str(e)}"
            return render(
                request,
                "core/quotation/q_add.html",
                {
                    "customers": customers,
                    "templates": templates,
                    "products": products,
                    "plans": plans,
                    "errors": errors,
                    "posted": request.POST,
                    "today": today.isoformat(),
                    "default_validity": (today + timedelta(days=30)).isoformat(),
                },
            )

    return render(
        request,
        "core/quotation/q_add.html",
        {
            "customers": customers,
            "templates": templates,
            "products": products,
            "plans": plans,
            "today": timezone.now().date().isoformat(),
            "default_validity": (timezone.now().date() + timedelta(days=30)).isoformat(),
        },
    )


def quotation_detail(request, quotation_id):
    """
    Detailed printable view of an official quotation (SRS Section 3.5, FR-18, FR-20, FR-21).
    Enforces customer isolation (FR-18).
    """
    quotation = get_object_or_404(
        Quotation.objects.select_related("customer__user", "created_by", "template").prefetch_related("items__product", "items__plan", "items__variant"),
        id=quotation_id
    )

    is_internal = is_staff_or_admin(request.user)
    # FR-18: Verify customer ownership
    if request.user.is_authenticated and not is_internal:
        if quotation.customer.user != request.user:
            messages.error(request, "You are not authorized to view this quotation.")
            return redirect("quotation_list")

    today = timezone.now().date()
    return render(
        request,
        "core/quotation/q_detail.html",
        {
            "quotation": quotation,
            "items": quotation.items.all(),
            "is_internal": is_internal,
            "today": today,
        },
    )


def quotation_status_action(request, quotation_id):
    """Update quotation status: send, accept, reject (FR-20, FR-21)."""
    if not is_staff_or_admin(request.user):
        messages.error(request, "You are not authorized to update quotation status.")
        return redirect("quotation_list")

    if request.method != "POST":
        return redirect("quotation_detail", quotation_id=quotation_id)

    quotation = get_object_or_404(Quotation, id=quotation_id)
    action = request.POST.get("action", "").strip().lower()

    if action == "send":
        quotation.status = "sent"
        quotation.save()
        messages.success(request, f"Quotation {quotation.quotation_number} marked as Sent.")
    elif action == "accept":
        quotation.status = "accepted"
        quotation.save()
        messages.success(request, f"Quotation {quotation.quotation_number} accepted by customer.")
    elif action == "reject":
        quotation.status = "rejected"
        quotation.save()
        messages.warning(request, f"Quotation {quotation.quotation_number} marked as Rejected.")

    return redirect("quotation_detail", quotation_id=quotation.id)


def quotation_convert(request, quotation_id):
    """
    Convert an eligible quotation into an active subscription (SRS FR-22).
    Preserves reference to originating quotation and customer.
    """
    if not is_staff_or_admin(request.user):
        messages.error(request, "You are not authorized to convert quotations.")
        return redirect("quotation_list")

    if request.method != "POST":
        return redirect("quotation_detail", quotation_id=quotation_id)

    quotation = get_object_or_404(Quotation, id=quotation_id)

    if not quotation.is_eligible_for_conversion:
        messages.error(request, f"Quotation {quotation.quotation_number} is expired or ineligible for conversion.")
        return redirect("quotation_detail", quotation_id=quotation.id)

    if hasattr(quotation, "converted_subscription") and quotation.converted_subscription:
        messages.info(request, f"This quotation was already converted into Subscription {quotation.converted_subscription.subscription_number}.")
        return redirect("quotation_detail", quotation_id=quotation.id)

    today = timezone.now().date()
    sub_count = Subscription.objects.count() + 101
    subscription_number = f"BL-SUB-{today.year}-{sub_count:04d}"

    # Pick the primary plan from line items if present
    primary_plan = None
    for item in quotation.items.all():
        if item.plan:
            primary_plan = item.plan
            break

    # Expiry calculation based on primary plan frequency or 1 year default
    expiry_date = today + timedelta(days=365)
    if primary_plan:
        if primary_plan.billing_frequency == "daily":
            expiry_date = today + timedelta(days=30)
        elif primary_plan.billing_frequency == "weekly":
            expiry_date = today + timedelta(days=90)
        elif primary_plan.billing_frequency == "monthly":
            expiry_date = today + timedelta(days=365)

    with transaction.atomic():
        subscription = Subscription.objects.create(
            subscription_number=subscription_number,
            customer=quotation.customer,
            plan=primary_plan,
            source_quotation=quotation,
            start_date=today,
            expiry_date=expiry_date,
            payment_terms="Net 30",
            status="active",
            subtotal=quotation.subtotal,
            tax_amount=quotation.tax_amount,
            total_amount=quotation.total_amount,
        )

        for q_item in quotation.items.all():
            SubscriptionItem.objects.create(
                subscription=subscription,
                product=q_item.product,
                variant=q_item.variant,
                quantity=q_item.quantity,
                unit_price=q_item.unit_price,
                total_price=q_item.total_price,
            )

        subscription.next_billing_date = subscription.compute_next_billing_date()
        subscription.save()

        quotation.status = "converted"
        quotation.save()

        # Auto-generate first invoice (FR-27, FR-28)
        _generate_invoice_from_subscription(subscription)

    messages.success(
        request,
        f"Quotation {quotation.quotation_number} was successfully converted into Subscription {subscription.subscription_number} and the initial invoice was generated!"
    )
    return redirect("subscription_detail", subscription_id=subscription.id)


def quotation_template_api(request, template_id):
    """
    JSON API returning preconfigured items from a quotation template (FR-19, FR-20).
    """
    template = get_object_or_404(QuotationTemplate.objects.prefetch_related("items__product", "items__plan", "items__variant"), id=template_id)
    items_data = []
    for it in template.items.all():
        items_data.append({
            "product_id": it.product.id,
            "product_name": it.product.name,
            "plan_id": it.plan.id if it.plan else "",
            "plan_name": it.plan.name if it.plan else "",
            "variant_id": it.variant.id if it.variant else "",
            "variant_name": it.variant.name if it.variant else "",
            "quantity": it.quantity,
            "unit_price": str(it.unit_price),
        })
    return JsonResponse({
        "success": True,
        "name": template.name,
        "description": template.description,
        "items": items_data,
    })




# ---------------------------------------------------------------------------
# Section 3.1 - Staff Creation (FR-07)
# ---------------------------------------------------------------------------

@login_required
def create_staff(request):
    """
    Administrator-only view to create internal staff accounts (SRS Section 3.1, FR-07).
    """
    if not (request.user.is_superuser or request.user.groups.filter(name__in=['Admin', 'Administrator']).exists()):
        raise PermissionDenied

    if request.method == 'POST':
        form = StaffCreationForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                email = form.cleaned_data['email']
                user = User.objects.create_user(
                    username=email,
                    email=email,
                    first_name=form.cleaned_data['full_name'],
                    password=form.cleaned_data['password1'],
                )
                user.is_staff = True
                staff_group, _ = Group.objects.get_or_create(name='Staff')
                internal_staff_group, _ = Group.objects.get_or_create(name='Internal Staff')
                user.groups.add(staff_group, internal_staff_group)
                user.save()

            messages.success(request, f"Staff account for {user.email} created successfully!")
            return redirect('create_staff')
    else:
        form = StaffCreationForm()

    return render(request, 'core/admin/staff_creation.html', {'form': form})


# ---------------------------------------------------------------------------
# Section 3.4 - Customer Management (FR-16 to FR-18)
# ---------------------------------------------------------------------------

@login_required
def customer_list(request):
    """
    Display customer accounts for authorized staff/admins (SRS Section 3.4, FR-16, FR-17).
    Customers cannot access other customers' records (FR-18).
    """
    if not is_staff_or_admin(request.user):
        raise PermissionDenied

    customers = CustomerProfile.objects.select_related('user').all().order_by('-id')
    search = request.GET.get('search', '').strip()
    if search:
        customers = customers.filter(
            Q(user__first_name__icontains=search) |
            Q(user__email__icontains=search) |
            Q(phone__icontains=search) |
            Q(company_name__icontains=search)
        )

    return render(request, 'core/customers/cust_list.html', {
        'customers': customers,
        'search': search,
    })


@login_required
def customer_detail(request, pk):
    """
    View customer account details (SRS Section 3.4, FR-16, FR-17).
    Enforces customer privacy: a customer can only view their own record (FR-18).
    """
    customer = get_object_or_404(CustomerProfile.objects.select_related('user'), pk=pk)
    if not is_staff_or_admin(request.user):
        if customer.user_id != request.user.id:
            raise PermissionDenied

    quotations = customer.quotations.all().order_by('-created_at')[:10]

    return render(request, 'core/customers/cust_detail.html', {
        'customer': customer,
        'quotations': quotations,
        'is_staff_or_admin': is_staff_or_admin(request.user),
    })


@login_required
def customer_update(request, pk):
    """
    Update customer details (SRS Section 3.4, FR-17).
    Authorized for staff/admins or the customer themselves updating their own profile.
    """
    customer = get_object_or_404(CustomerProfile.objects.select_related('user'), pk=pk)
    if not is_staff_or_admin(request.user) and customer.user_id != request.user.id:
        raise PermissionDenied

    if request.method == 'POST':
        form = CustomerUpdateForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            messages.success(request, 'Customer details updated successfully!')
            return redirect('customer_detail', pk=customer.pk)
    else:
        form = CustomerUpdateForm(instance=customer)

    return render(request, 'core/customers/customer_update.html', {
        'form': form,
        'customer': customer,
    })


# ─────────────────────────────────────────────────────────────────────────────
# NEW VIEWS APPENDED — Sections 3.6–3.11
# ─────────────────────────────────────────────────────────────────────────────
# These are appended to the bottom of views.py via append_views.py script.
# Imports required (already in views.py header):
#   from decimal import Decimal
#   from django.db.models import Sum, Count, Q
#   from django.http import HttpResponse
#   import csv
# ─────────────────────────────────────────────────────────────────────────────

import csv
from django.db.models import Sum, Count
from django.http import HttpResponse

from .models import (
    TaxRule, DiscountRule, DiscountProduct,
    Invoice, InvoiceItem, Payment,
)
from .forms import TaxRuleForm, DiscountRuleForm, PaymentRecordForm


# ─── helpers ──────────────────────────────────────────────────────────────────

def _next_invoice_number():
    """Generate next BL-INV-YYYY-XXXX number."""
    from django.utils import timezone as tz
    year = tz.now().year
    prefix = f"BL-INV-{year}-"
    last = Invoice.objects.filter(invoice_number__startswith=prefix).order_by('-invoice_number').first()
    if last:
        try:
            seq = int(last.invoice_number.split('-')[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:04d}"


def _generate_invoice_from_subscription(subscription, period_start=None, period_end=None):
    """
    Auto-generate one Invoice from an active Subscription (SRS FR-27, FR-28).
    Prevents duplicate invoice generation for the same subscription billing period (FR-31).
    Applies active tax rules (FR-32) and eligible discount rules (FR-36, FR-37).
    Returns the created or existing Invoice instance.
    """
    from datetime import timedelta
    today = timezone.now().date()
    p_start = period_start or subscription.start_date
    p_end = period_end or (subscription.next_billing_date or subscription.compute_next_billing_date(p_start))

    # Duplicate Prevention (FR-31): check for existing active invoice for this period
    existing = Invoice.objects.filter(
        subscription=subscription,
        billing_period_start=p_start,
        billing_period_end=p_end,
    ).exclude(status='cancelled').first()
    if existing:
        return existing

    due = today + timedelta(days=30)

    # Tax rule (FR-32)
    tax_rule = TaxRule.objects.filter(is_active=True).first()

    # Discount rule (FR-36, FR-37)
    discount_rule = None
    subtotal = subscription.subtotal
    total_qty = sum(item.quantity for item in subscription.items.all())

    for d in DiscountRule.objects.filter(is_active=True):
        if not d.is_valid_today:
            continue
        if d.min_order_value and subtotal < d.min_order_value:
            continue
        if d.min_quantity and total_qty < d.min_quantity:
            continue
        # Check product applicability
        if d.products.exists():
            sub_prod_ids = set(subscription.items.values_list('product_id', flat=True))
            rule_prod_ids = set(d.products.values_list('id', flat=True))
            if not (sub_prod_ids & rule_prod_ids):
                continue
        discount_rule = d
        break

    # Calculate tax & discount amounts
    discount_amt = Decimal("0.00")
    if discount_rule:
        discount_amt = discount_rule.compute_discount(subtotal)
        # Increment usage counter (FR-37)
        discount_rule.times_used += 1
        discount_rule.save(update_fields=['times_used'])

    taxable_base = max(subtotal - discount_amt, Decimal("0.00"))
    if tax_rule and tax_rule.is_active:
        tax_amt = (taxable_base * tax_rule.rate / Decimal("100")).quantize(Decimal("0.01"))
    else:
        tax_amt = subscription.tax_amount

    total_amt = (taxable_base + tax_amt).quantize(Decimal("0.01"))

    invoice = Invoice.objects.create(
        invoice_number=_next_invoice_number(),
        subscription=subscription,
        customer=subscription.customer,
        billing_period_start=p_start,
        billing_period_end=p_end,
        issue_date=today,
        due_date=due,
        status='draft',
        subtotal=subtotal,
        tax_rule=tax_rule,
        tax_amount=tax_amt,
        discount_rule=discount_rule,
        discount_amount=discount_amt,
        total_amount=total_amt,
        notes=f"Auto-generated for subscription {subscription.subscription_number} (Period: {p_start} to {p_end})",
    )

    # Copy subscription items to invoice items (FR-30)
    for si in subscription.items.all():
        line_sub = (Decimal(si.quantity) * si.unit_price).quantize(Decimal("0.01"))
        line_disc = Decimal("0.00")
        if discount_rule and subtotal > 0:
            line_disc = (discount_amt * (line_sub / subtotal)).quantize(Decimal("0.01"))
        line_tax = Decimal("0.00")
        if tax_rule and tax_rule.is_active:
            line_tax = ((line_sub - line_disc) * tax_rule.rate / Decimal("100")).quantize(Decimal("0.01"))

        InvoiceItem.objects.create(
            invoice=invoice,
            product=si.product,
            variant=si.variant,
            description=si.product.name,
            quantity=si.quantity,
            unit_price=si.unit_price,
            discount_amount=line_disc,
            tax_amount=line_tax,
            total_price=line_sub - line_disc + line_tax,
        )

    # Advance subscription next_billing_date
    subscription.next_billing_date = subscription.compute_next_billing_date(p_end)
    subscription.save(update_fields=['next_billing_date'])

    return invoice


# ─────────────────────────────────────────────────────────────────────────────
# Section 3.6 – Subscription Management (FR-23 to FR-27)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def subscription_list(request):
    """
    List subscriptions. Staff/Admin see all; customers see only their own (FR-26).
    """
    search = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')

    if is_staff_or_admin(request.user):
        qs = Subscription.objects.select_related('customer__user', 'plan').all()
    else:
        try:
            profile = request.user.customer_profile
        except CustomerProfile.DoesNotExist:
            qs = Subscription.objects.none()
        else:
            qs = Subscription.objects.filter(customer=profile).select_related('plan')

    if search:
        qs = qs.filter(
            Q(subscription_number__icontains=search) |
            Q(customer__user__first_name__icontains=search) |
            Q(customer__user__email__icontains=search)
        )
    if status_filter:
        qs = qs.filter(status=status_filter)

    return render(request, 'core/subscription/sub_list.html', {
        'subscriptions': qs,
        'search': search,
        'status_filter': status_filter,
        'status_choices': Subscription.STATUS_CHOICES,
        'is_staff': is_staff_or_admin(request.user),
    })


@login_required
def subscription_detail(request, subscription_id):
    """Subscription detail page with items, invoices, and lifecycle buttons (FR-23–FR-27)."""
    sub = get_object_or_404(Subscription.objects.select_related('customer__user', 'plan'), pk=subscription_id)

    # Customers can only see their own
    if not is_staff_or_admin(request.user):
        try:
            if sub.customer.user != request.user:
                raise PermissionDenied
        except CustomerProfile.DoesNotExist:
            raise PermissionDenied

    items = sub.items.select_related('product', 'variant').all()
    invoices = sub.invoices.all().order_by('-created_at')

    return render(request, 'core/subscription/sub_details.html', {
        'sub': sub,
        'items': items,
        'invoices': invoices,
        'is_staff': is_staff_or_admin(request.user),
    })


@login_required
def subscription_lifecycle_action(request, subscription_id):
    """
    POST: pause / resume / close / activate a subscription (FR-24, FR-25, FR-26, FR-27).
    Staff/Admin only.
    """
    if not is_staff_or_admin(request.user):
        raise PermissionDenied

    sub = get_object_or_404(Subscription, pk=subscription_id)
    action = request.POST.get('action', '')

    ACTION_MAP = {
        'activate': 'active',
        'close': 'closed',
        'pause': 'draft',   # using 'draft' as paused state within subscription
        'confirm': 'confirmed',
    }
    if action in ACTION_MAP:
        sub.status = ACTION_MAP[action]
        sub.save()
        messages.success(request, f"Subscription {sub.subscription_number} marked as {ACTION_MAP[action]}.")
        # Auto-generate invoice on activation (FR-28)
        if action == 'activate' and not sub.invoices.exists():
            inv = _generate_invoice_from_subscription(sub)
            messages.info(request, f"Invoice {inv.invoice_number} auto-generated.")
    else:
        messages.error(request, "Unknown action.")

    return redirect('subscription_detail', subscription_id=sub.pk)


@login_required
def subscription_cancel(request, subscription_id):
    """Customer self-service cancellation (FR-26)."""
    sub = get_object_or_404(Subscription, pk=subscription_id)
    if not is_staff_or_admin(request.user):
        try:
            if sub.customer.user != request.user:
                raise PermissionDenied
        except CustomerProfile.DoesNotExist:
            raise PermissionDenied

    if request.method == 'POST':
        sub.status = 'closed'
        sub.save()
        messages.success(request, f"Subscription {sub.subscription_number} cancelled.")
        return redirect('subscription_list')

    return render(request, 'core/subscription/sub_cancel_confirm.html', {'sub': sub})

@login_required
def subscription_renew(request, subscription_id):
    """
    Renew a subscription based on configured billing frequency and renewal rules (SRS FR-26).
    Updates expiry and next billing date, generates next invoice, and activates subscription.
    """
    if not is_staff_or_admin(request.user):
        raise PermissionDenied

    sub = get_object_or_404(Subscription.objects.select_related('plan'), pk=subscription_id)
    today = timezone.now().date()
    new_start = sub.expiry_date if (sub.expiry_date and sub.expiry_date >= today) else today
    new_next_billing = sub.compute_next_billing_date(new_start)

    # Extend expiry
    sub.expiry_date = sub.compute_next_billing_date(new_next_billing)
    sub.next_billing_date = new_next_billing
    sub.status = 'active'
    sub.save()

    # Generate renewal invoice
    inv = _generate_invoice_from_subscription(sub, period_start=new_start, period_end=new_next_billing)
    messages.success(request, f"Subscription {sub.subscription_number} renewed! Next billing period invoice {inv.invoice_number} created.")
    return redirect('subscription_detail', subscription_id=sub.pk)



# ─────────────────────────────────────────────────────────────────────────────
# Section 3.7 – Invoice Management (FR-28 to FR-33)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def invoice_list(request):
    """
    Invoice register. Customers see only their own invoices (FR-32, FR-33).
    """
    search = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')

    if is_staff_or_admin(request.user):
        qs = Invoice.objects.select_related('customer__user', 'subscription').all()
    else:
        try:
            profile = request.user.customer_profile
        except CustomerProfile.DoesNotExist:
            qs = Invoice.objects.none()
        else:
            qs = Invoice.objects.filter(customer=profile).select_related('subscription')

    if search:
        qs = qs.filter(
            Q(invoice_number__icontains=search) |
            Q(customer__user__first_name__icontains=search) |
            Q(customer__user__email__icontains=search)
        )
    if status_filter:
        qs = qs.filter(status=status_filter)

    # KPIs (staff only)
    kpis = {}
    if is_staff_or_admin(request.user):
        kpis['total'] = Invoice.objects.count()
        kpis['paid'] = Invoice.objects.filter(status='paid').count()
        kpis['overdue'] = Invoice.objects.filter(status='overdue').count()
        kpis['draft'] = Invoice.objects.filter(status='draft').count()

    return render(request, 'core/invoice/list.html', {
        'invoices': qs,
        'search': search,
        'status_filter': status_filter,
        'status_choices': Invoice.STATUS_CHOICES,
        'kpis': kpis,
        'is_staff': is_staff_or_admin(request.user),
    })


@login_required
def invoice_detail(request, invoice_id):
    """Printable invoice detail with line items, payment history, and action buttons (FR-31)."""
    invoice = get_object_or_404(
        Invoice.objects.select_related('customer__user', 'subscription', 'tax_rule', 'discount_rule'),
        pk=invoice_id,
    )

    if not is_staff_or_admin(request.user):
        try:
            if invoice.customer.user != request.user:
                raise PermissionDenied
        except CustomerProfile.DoesNotExist:
            raise PermissionDenied

    items = invoice.invoice_items.select_related('product', 'variant', 'plan').all()
    payments = invoice.payments.select_related('recorded_by').all()
    payment_form = PaymentRecordForm(initial={'payment_date': timezone.now().date()})

    return render(request, 'core/invoice/invoice_detail.html', {
        'invoice': invoice,
        'items': items,
        'payments': payments,
        'payment_form': payment_form,
        'is_staff': is_staff_or_admin(request.user),
    })


@login_required
def invoice_create(request, subscription_id):
    """Manually generate an invoice from a subscription (FR-28, FR-29)."""
    if not is_staff_or_admin(request.user):
        raise PermissionDenied

    sub = get_object_or_404(Subscription, pk=subscription_id)
    inv = _generate_invoice_from_subscription(sub)
    messages.success(request, f"Invoice {inv.invoice_number} created.")
    return redirect('invoice_detail', invoice_id=inv.pk)


@login_required
def invoice_status_action(request, invoice_id):
    """Mark invoice as sent / paid / overdue (FR-32, FR-36)."""
    if not is_staff_or_admin(request.user):
        raise PermissionDenied

    invoice = get_object_or_404(Invoice, pk=invoice_id)
    action = request.POST.get('action', '')

    STATUS_MAP = {'mark_sent': 'sent', 'mark_paid': 'paid', 'mark_overdue': 'overdue', 'mark_draft': 'draft'}
    if action in STATUS_MAP:
        invoice.status = STATUS_MAP[action]
        invoice.save()
        messages.success(request, f"Invoice {invoice.invoice_number} marked as {STATUS_MAP[action]}.")
    else:
        messages.error(request, "Unknown action.")

    return redirect('invoice_detail', invoice_id=invoice.pk)


# ─────────────────────────────────────────────────────────────────────────────
# Section 3.8 – Payment Recording (FR-34 to FR-37)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def payment_list(request):
    """Payment history across all invoices (staff) or own invoices (customer)."""
    if is_staff_or_admin(request.user):
        payments = Payment.objects.select_related('invoice__customer__user', 'recorded_by').all()
    else:
        try:
            profile = request.user.customer_profile
        except CustomerProfile.DoesNotExist:
            payments = Payment.objects.none()
        else:
            payments = Payment.objects.filter(invoice__customer=profile).select_related('invoice', 'recorded_by')

    return render(request, 'core/payment/list.html', {
        'payments': payments,
        'is_staff': is_staff_or_admin(request.user),
    })


@login_required
def payment_record(request, invoice_id):
    """
    Record a payment against an invoice and auto-update its status (FR-34, FR-35, FR-36).
    """
    if not is_staff_or_admin(request.user):
        raise PermissionDenied

    invoice = get_object_or_404(Invoice, pk=invoice_id)

    if request.method == 'POST':
        form = PaymentRecordForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.invoice = invoice
            payment.recorded_by = request.user
            payment.save()

            # Auto-update invoice status (FR-36)
            if invoice.amount_due <= Decimal("0.00"):
                invoice.status = 'paid'
                invoice.save()
                messages.success(request, f"Payment recorded. Invoice {invoice.invoice_number} is now fully paid.")
            else:
                messages.success(request, f"Payment of ₹{payment.amount} recorded. Remaining: ₹{invoice.amount_due}.")
            return redirect('invoice_detail', invoice_id=invoice.pk)
        else:
            messages.error(request, "Please correct the errors below.")
            return redirect('invoice_detail', invoice_id=invoice.pk)

    return redirect('invoice_detail', invoice_id=invoice.pk)


@login_required
def payment_delete(request, payment_id):
    """Delete a payment entry (staff only)."""
    if not is_staff_or_admin(request.user):
        raise PermissionDenied

    payment = get_object_or_404(Payment, pk=payment_id)
    invoice_id = payment.invoice_id

    if request.method == 'POST':
        payment.delete()
        messages.success(request, "Payment deleted.")
    return redirect('invoice_detail', invoice_id=invoice_id)


# ─────────────────────────────────────────────────────────────────────────────
# Section 3.9 – Tax & Discount Rules (FR-38 to FR-41)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def tax_rule_list(request):
    """List all tax rules (admin only)."""
    if not is_staff_or_admin(request.user):
        raise PermissionDenied
    rules = TaxRule.objects.all()
    return render(request, 'core/tax/tax_rule_list.html', {'rules': rules})


@login_required
def tax_rule_create(request):
    if not is_staff_or_admin(request.user):
        raise PermissionDenied
    if request.method == 'POST':
        form = TaxRuleForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Tax rule created.")
            return redirect('tax_rule_list')
    else:
        form = TaxRuleForm()
    return render(request, 'core/tax/tax_rule_form.html', {'form': form, 'title': 'Create Tax Rule'})


@login_required
def tax_rule_edit(request, pk):
    if not is_staff_or_admin(request.user):
        raise PermissionDenied
    rule = get_object_or_404(TaxRule, pk=pk)
    if request.method == 'POST':
        form = TaxRuleForm(request.POST, instance=rule)
        if form.is_valid():
            form.save()
            messages.success(request, "Tax rule updated.")
            return redirect('tax_rule_list')
    else:
        form = TaxRuleForm(instance=rule)
    return render(request, 'core/tax/tax_rule_form.html', {'form': form, 'title': 'Edit Tax Rule', 'rule': rule})


@login_required
def tax_rule_delete(request, pk):
    if not is_staff_or_admin(request.user):
        raise PermissionDenied
    rule = get_object_or_404(TaxRule, pk=pk)
    if request.method == 'POST':
        rule.delete()
        messages.success(request, "Tax rule deleted.")
    return redirect('tax_rule_list')


@login_required
def discount_rule_list(request):
    if not is_staff_or_admin(request.user):
        raise PermissionDenied
    rules = DiscountRule.objects.prefetch_related('products').all()
    return render(request, 'core/discount/discount_rule_list.html', {'rules': rules})


@login_required
def discount_rule_create(request):
    if not is_staff_or_admin(request.user):
        raise PermissionDenied
    if request.method == 'POST':
        form = DiscountRuleForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Discount rule created.")
            return redirect('discount_rule_list')
    else:
        form = DiscountRuleForm()
    return render(request, 'core/discount/discount_rule_form.html', {'form': form, 'title': 'Create Discount Rule'})


@login_required
def discount_rule_edit(request, pk):
    if not is_staff_or_admin(request.user):
        raise PermissionDenied
    rule = get_object_or_404(DiscountRule, pk=pk)
    if request.method == 'POST':
        form = DiscountRuleForm(request.POST, instance=rule)
        if form.is_valid():
            form.save()
            messages.success(request, "Discount rule updated.")
            return redirect('discount_rule_list')
    else:
        form = DiscountRuleForm(instance=rule)
    return render(request, 'core/discount/discount_rule_form.html', {'form': form, 'title': 'Edit Discount Rule', 'rule': rule})


@login_required
def discount_rule_delete(request, pk):
    if not is_staff_or_admin(request.user):
        raise PermissionDenied
    rule = get_object_or_404(DiscountRule, pk=pk)
    if request.method == 'POST':
        rule.delete()
        messages.success(request, "Discount rule deleted.")
    return redirect('discount_rule_list')


# ─────────────────────────────────────────────────────────────────────────────
# Section 3.10 – Dashboards (FR-42 to FR-45)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def admin_dashboard(request):
    """
    Admin dashboard: MRR, total customers, active subscriptions, overdue invoices (FR-42).
    """
    if not is_staff_or_admin(request.user):
        raise PermissionDenied

    today = timezone.now().date()
    total_customers = CustomerProfile.objects.count()
    active_subscriptions = Subscription.objects.filter(status='active').count()
    overdue_invoices = Invoice.objects.filter(status='overdue').count()

    # MRR: sum of total_amount for active subscriptions
    mrr = Subscription.objects.filter(status='active').aggregate(
        total=Sum('total_amount')
    )['total'] or Decimal('0.00')

    # Revenue this month
    month_start = today.replace(day=1)
    monthly_revenue = Payment.objects.filter(payment_date__gte=month_start).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')

    # Recent payments
    recent_payments = Payment.objects.select_related(
        'invoice__customer__user', 'recorded_by'
    ).order_by('-payment_date')[:8]

    # Pending quotations
    pending_quotations = Quotation.objects.filter(status__in=['draft', 'sent']).count()

    # Expiring subscriptions (within 30 days)
    expiring_soon = Subscription.objects.filter(
        status='active',
        expiry_date__lte=today + timezone.timedelta(days=30),
        expiry_date__gte=today,
    ).select_related('customer__user', 'plan')[:5]

    # Recent subscriptions
    recent_subscriptions = Subscription.objects.select_related(
        'customer__user', 'plan'
    ).order_by('-created_at')[:5]

    return render(request, 'core/dashboard/admindash.html', {
        'total_customers': total_customers,
        'active_subscriptions': active_subscriptions,
        'overdue_invoices': overdue_invoices,
        'mrr': mrr,
        'monthly_revenue': monthly_revenue,
        'recent_payments': recent_payments,
        'pending_quotations': pending_quotations,
        'expiring_soon': expiring_soon,
        'recent_subscriptions': recent_subscriptions,
    })


@login_required
def staff_dashboard(request):
    """
    Staff dashboard: pending tasks, recent activity, expiring subscriptions (FR-43).
    """
    if not is_staff_or_admin(request.user):
        raise PermissionDenied

    today = timezone.now().date()
    pending_quotations = Quotation.objects.filter(status__in=['draft', 'sent']).select_related('customer__user').order_by('-created_at')[:10]
    overdue_invoices = Invoice.objects.filter(status='overdue').select_related('customer__user').order_by('due_date')[:10]
    recent_customers = CustomerProfile.objects.select_related('user').order_by('-user__date_joined')[:5]
    expiring_subs = Subscription.objects.filter(
        status='active',
        expiry_date__lte=today + timezone.timedelta(days=30),
        expiry_date__gte=today,
    ).select_related('customer__user', 'plan')[:10]
    recent_payments = Payment.objects.select_related('invoice__customer__user').order_by('-created_at')[:8]

    return render(request, 'core/dashboard/staffdash.html', {
        'pending_quotations': pending_quotations,
        'overdue_invoices': overdue_invoices,
        'recent_customers': recent_customers,
        'expiring_subs': expiring_subs,
        'recent_payments': recent_payments,
    })


@login_required
def customer_dashboard(request):
    """
    Customer dashboard: own subscriptions, invoices, payment history (FR-44).
    """
    try:
        profile = request.user.customer_profile
    except CustomerProfile.DoesNotExist:
        messages.warning(request, "No customer profile found. Please contact support.")
        return redirect('home')

    active_subs = Subscription.objects.filter(customer=profile, status='active').select_related('plan')
    pending_invoices = Invoice.objects.filter(customer=profile).exclude(status='paid').order_by('due_date')[:10]
    recent_payments = Payment.objects.filter(invoice__customer=profile).select_related('invoice').order_by('-payment_date')[:8]
    recent_quotations = Quotation.objects.filter(customer=profile).order_by('-created_at')[:5]

    total_paid = Payment.objects.filter(invoice__customer=profile).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    return render(request, 'core/dashboard/custdash.html', {
        'profile': profile,
        'active_subs': active_subs,
        'pending_invoices': pending_invoices,
        'recent_payments': recent_payments,
        'recent_quotations': recent_quotations,
        'total_paid': total_paid,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Section 3.11 – Reports & Analytics (FR-46 to FR-49)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def reports_view(request):
    """
    Reports page: revenue by period, subscription summary, payment collection (FR-46 to FR-49).
    """
    if not is_staff_or_admin(request.user):
        raise PermissionDenied

    today = timezone.now().date()
    month_start = today.replace(day=1)

    # Revenue report
    monthly_revenue = Payment.objects.filter(payment_date__gte=month_start).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')

    yearly_start = today.replace(month=1, day=1)
    yearly_revenue = Payment.objects.filter(payment_date__gte=yearly_start).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')

    # Subscription status breakdown
    sub_status_data = Subscription.objects.values('status').annotate(count=Count('id')).order_by('status')

    # Payment collection summary
    payment_by_method = Payment.objects.values('payment_method').annotate(
        count=Count('id'), total=Sum('amount')
    ).order_by('-total')

    # Invoice summary
    invoice_summary = Invoice.objects.values('status').annotate(
        count=Count('id'), total=Sum('total_amount')
    ).order_by('status')

    # Recent payments
    recent_payments = Payment.objects.select_related(
        'invoice__customer__user', 'recorded_by'
    ).order_by('-payment_date')[:20]

    # Top customers by revenue
    top_customers = CustomerProfile.objects.annotate(
        revenue=Sum('invoices__total_amount')
    ).filter(revenue__isnull=False).order_by('-revenue')[:10]

    return render(request, 'core/reports/reports.html', {
        'monthly_revenue': monthly_revenue,
        'yearly_revenue': yearly_revenue,
        'sub_status_data': sub_status_data,
        'payment_by_method': payment_by_method,
        'invoice_summary': invoice_summary,
        'recent_payments': recent_payments,
        'top_customers': top_customers,
        'today': today,
    })


@login_required
def reports_export_csv(request):
    """Export payment collection report as CSV (FR-49)."""
    if not is_staff_or_admin(request.user):
        raise PermissionDenied

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="brightloop_report.csv"'

    writer = csv.writer(response)
    writer.writerow(['Invoice Number', 'Customer', 'Amount', 'Method', 'Date', 'Reference'])

    payments = Payment.objects.select_related(
        'invoice__customer__user', 'recorded_by'
    ).order_by('-payment_date')

    for p in payments:
        writer.writerow([
            p.invoice.invoice_number,
            p.invoice.customer.name,
            p.amount,
            p.get_payment_method_display(),
            p.payment_date,
            p.reference_number,
        ])

    return response
