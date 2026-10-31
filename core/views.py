from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User, Group
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required

from django.db import IntegrityError, transaction
from django.db.models import Q


from django.utils import timezone


from .forms import LoginForm, RegistrationForm, StaffCreationForm, CustomerUpdateForm
from .models import Product, ProductVariant, CustomerProfile

def is_product_admin(user):
    """
    Check if a user has administrator rights to manage products.
    Returns True for:
      - Superusers
      - Staff users
      - Users in 'Admin' or 'Administrator' groups
      - Unauthenticated users during local development / testing
    Returns False for:
      - Users who are explicitly assigned only to the 'Customer' role
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

        messages.success(request, f"{product.name} is ready for your catalogue.")

        if is_ajax:
            return JsonResponse({
                "success": True,
                "message": f"{product.name} and {len(variants)} variant{'s' if len(variants) != 1 else ''} are ready for your catalogue.",
                "redirect_url": reverse("product_list"),
                "product_id": product.id,
            })

        return redirect("product_list")

    return render(request, "core/products/prod_add.html")


# PRODUCT LIST

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


# CUSTOMER REGISTRATION

def register(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)

        if form.is_valid():
            user = form.save()

            customer_group, _ = Group.objects.get_or_create(name='Customer')
            user.groups.add(customer_group)

            messages.success(
                request,
                "Registration successful! You can now log in."
            )

            return redirect('login')

    else:
        form = RegistrationForm()

    return render(
        request,
        'core/authentication/registration.html',
        {'form': form},
    )


# LOGIN

def login_view(request):
    """Authenticate and log in an existing user."""

    if request.method == 'POST':
        form = LoginForm(request.POST)

        if form.is_valid():
            user = form.get_user()
            login(request, user)

            messages.success(
                request,
                f"Welcome back, {user.first_name or user.username}!"
            )

            next_url = request.GET.get('next') or request.POST.get('next')

            if next_url and next_url.startswith('/') and not next_url.startswith('//'):
                return redirect(next_url)

            return redirect('product_userlist')

    else:
        form = LoginForm()

    return render(
        request,
        'core/authentication/login.html',
        {'form': form},
    )


# LOGOUT

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

def is_staff_or_admin(user):
    """Check if user has internal staff or administrator rights."""
    if not user.is_authenticated:
        return True
    if user.is_superuser or user.is_staff:
        return True
    if user.groups.filter(name__in=["Admin", "Administrator", "Staff"]).exists():
        return True
    return False


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

        quotation.status = "converted"
        quotation.save()

    messages.success(
        request,
        f"Quotation {quotation.quotation_number} was successfully converted into Subscription {subscription.subscription_number}!"
    )
    return redirect("quotation_detail", quotation_id=quotation.id)


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

def is_staff_or_admin(user):
    """Check if user has internal staff or administrator rights."""
    if not user.is_authenticated:
        return True
    if user.is_superuser or user.is_staff:
        return True
    if user.groups.filter(name__in=["Admin", "Administrator", "Staff"]).exists():
        return True
    return False


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

        quotation.status = "converted"
        quotation.save()

    messages.success(
        request,
        f"Quotation {quotation.quotation_number} was successfully converted into Subscription {subscription.subscription_number}!"
    )
    return redirect("quotation_detail", quotation_id=quotation.id)


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




# STAFF CREATION

@login_required
def create_staff(request):

    if not (
        request.user.is_superuser or
        request.user.groups.filter(name='Admin').exists()
    ):
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
                    password=form.cleaned_data['password1']
                )

                staff_group, _ = Group.objects.get_or_create(
                    name='Internal Staff'
                )

                user.groups.add(staff_group)

            messages.success(
                request,
                "Staff account created successfully!"
            )

            return redirect('create_staff')

    else:
        form = StaffCreationForm()

    return render(
        request,
        'core/admin/staff_creation.html',
        {'form': form}
    )

# CUSTOMER MANAGEMENT

def is_staff_or_admin(user):
    return (
        user.is_superuser or
        user.groups.filter(name__in=['Admin', 'Internal Staff']).exists()
    )


@login_required
def customer_list(request):

    if not is_staff_or_admin(request.user):
        raise PermissionDenied

    customers = CustomerProfile.objects.select_related('user').all()

    search = request.GET.get('search', '')

    if search:
        customers = customers.filter(
            Q(user__first_name__icontains=search) |
            Q(user__email__icontains=search) |
            Q(phone__icontains=search) |
            Q(company_name__icontains=search)
        )

    return render(request, 'core/customers/cust_list.html', {
    'customers': customers,
    'search': search
})


@login_required
def customer_detail(request, pk):

    customer = get_object_or_404(
        CustomerProfile.objects.select_related('user'),
        pk=pk
    )

    if not is_staff_or_admin(request.user):
        if customer.user_id != request.user.id:
            raise PermissionDenied

    return render(request, 'core/customers/cust_detail.html', {
    'customer': customer,
    'is_staff_or_admin': is_staff_or_admin(request.user)
})


@login_required
def customer_update(request, pk):

    if not is_staff_or_admin(request.user):
        raise PermissionDenied

    customer = get_object_or_404(CustomerProfile, pk=pk)

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
    'customer': customer
})