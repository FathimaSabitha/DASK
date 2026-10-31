from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.models import Group
from .forms import RegistrationForm


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