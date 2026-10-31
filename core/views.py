
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.models import User, Group
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction

from .forms import RegistrationForm, StaffCreationForm


# CUSTOMER REGISTRATION

def register(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)

        if form.is_valid():
            user = form.save()

            customer_group, created = Group.objects.get_or_create(
                name='Customer'
            )

            user.groups.add(customer_group)

            messages.success(
                request,
                "Registration successful! You can now log in."
            )

            return redirect('register')

    else:
        form = RegistrationForm()

    return render(
        request,
        'core/authentication/registration.html',
        {'form': form}
    )


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

                staff_group, created = Group.objects.get_or_create(
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
