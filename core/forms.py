from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from .models import CustomerProfile

from django.contrib.auth.decorators import login_required




# CUSTOMER REGISTRATION

class RegistrationForm(forms.Form):
    full_name = forms.CharField(
        max_length=150,
        label="Full Name",
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter your full name',
            'autocomplete': 'name',
        }),
    )

    email = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(attrs={
            'placeholder': 'Enter your email',
            'autocomplete': 'email',
        }),
    )

    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Create a password',
            'autocomplete': 'new-password',
        }),
    )

    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Confirm your password',
            'autocomplete': 'new-password',
        }),
    )

    customer_type = forms.ChoiceField(
        choices=CustomerProfile.CUSTOMER_TYPES,
        label="Customer Type",
    )

    company_name = forms.CharField(
        max_length=150,
        required=False,
        label="Company Name",
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter company name',
        }),
    )

    phone = forms.CharField(
        max_length=15,
        required=False,
        label="Phone Number",
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter phone number',
        }),
    )

    address = forms.CharField(
        required=False,
        label="Address",
        widget=forms.Textarea(attrs={
            'placeholder': 'Enter your address',
            'rows': 3,
        }),
    )

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Email already registered")

        if User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError("Email already registered")

        return email

    def clean_password1(self):
        password = self.cleaned_data['password1']

        if len(password) <= 8:
            raise forms.ValidationError("Password must be more than 8 characters")

        if not any(c.isupper() for c in password):
            raise forms.ValidationError("Include an uppercase letter")

        if not any(c.islower() for c in password):
            raise forms.ValidationError("Include a lowercase letter")

        if not any(not c.isalnum() for c in password):
            raise forms.ValidationError("Include a special character")

        return password

    def clean(self):
        cleaned_data = super().clean()



        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')

        if password1 and password2 and password1 != password2:

            self.add_error('password2', "Passwords do not match")

        return cleaned_data

    def save(self):
        email = self.cleaned_data['email']

        user = User.objects.create_user(
            username=email,
            email=email,
            first_name=self.cleaned_data['full_name'],
            password=self.cleaned_data['password1'],
        )

        CustomerProfile.objects.create(
            user=user,
            customer_type=self.cleaned_data['customer_type'],
            company_name=self.cleaned_data['company_name'],
            phone=self.cleaned_data['phone'],
            address=self.cleaned_data['address'],
        )

        return user


class LoginForm(forms.Form):
    email = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(attrs={
            'placeholder': 'Enter your email',
            'autocomplete': 'email',
        }),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Enter your password',
            'autocomplete': 'current-password',
        }),
    )

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email', '').strip().lower()
        password = cleaned_data.get('password', '')

        if email and password:
            user = authenticate(username=email, password=password)
            if not user:
                raise forms.ValidationError("Invalid email or password.")
            self.user_cache = user

        return cleaned_data

    def get_user(self):
        return getattr(self, 'user_cache', None)

#

#staff


class StaffCreationForm(forms.Form):

    full_name = forms.CharField(
        max_length=150,
        label="Full Name"
    )

    email = forms.EmailField(
        label="Email Address"
    )

    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput
    )

    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput
    )

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Email already registered")

        if User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError("Email already registered")

        return email

    def clean_password1(self):
        password = self.cleaned_data['password1']

        if len(password) <= 8:
            raise forms.ValidationError(
                "Password must be more than 8 characters"
            )

        if not any(c.isupper() for c in password):
            raise forms.ValidationError(
                "Include an uppercase letter"
            )

        if not any(c.islower() for c in password):
            raise forms.ValidationError(
                "Include a lowercase letter"
            )

        if not any(not c.isalnum() for c in password):
            raise forms.ValidationError(
                "Include a special character"
            )

        return password

    def clean(self):
        cleaned_data = super().clean()

        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')

        if password1 and password2 and password1 != password2:
            self.add_error(
                'password2',
                "Passwords do not match"
            )

        return cleaned_data

        return user

