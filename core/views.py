
from decimal import Decimal, InvalidOperation
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User, Group
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q

from .forms import LoginForm, RegistrationForm, StaffCreationForm, CustomerUpdateForm
from .models import Product, ProductVariant, CustomerProfile


# PRODUCT CREATION

def product_create(request):
    """Create a product in the catalogue along with optional variants."""

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
    """Display catalogue items with their prices, cost, notes, and variants."""

    products = Product.objects.prefetch_related("variants").all()

    return render(
        request,
        "core/products/prod_list.html",
        {"products": products}
    )


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

            return redirect('product_list')

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