# apps/portal/forms.py
from decimal import Decimal

from django import forms


class PortalLoginForm(forms.Form):
    phone = forms.CharField(max_length=20, widget=forms.TextInput(attrs={
        'class': 'input',
        'placeholder': '0971234567',
        'autocomplete': 'username',
    }))
    password = forms.CharField(widget=forms.PasswordInput(attrs={
        'class': 'input',
        'placeholder': '••••••••',
        'autocomplete': 'current-password',
    }))


class PortalApplicationForm(forms.Form):
    loan_product = forms.UUIDField(widget=forms.Select(attrs={'class': 'input'}))
    amount = forms.DecimalField(max_digits=15, decimal_places=2, min_value=Decimal('1'), widget=forms.NumberInput(attrs={
        'class': 'input', 'step': '0.01', 'placeholder': 'Amount in ZMW',
    }))
    term_months = forms.IntegerField(min_value=1, max_value=120, widget=forms.NumberInput(attrs={
        'class': 'input', 'placeholder': 'Months',
    }))
    purpose = forms.ChoiceField(choices=[
        ('BUSINESS_CAPITAL', 'Business Capital'),
        ('EQUIPMENT', 'Equipment Purchase'),
        ('INVENTORY', 'Inventory / Stock'),
        ('AGRICULTURE', 'Agriculture / Farming'),
        ('EDUCATION', 'Education'),
        ('MEDICAL', 'Medical'),
        ('EMERGENCY', 'Emergency'),
        ('OTHER', 'Other'),
    ], widget=forms.Select(attrs={'class': 'input'}))
    purpose_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={
        'class': 'input', 'rows': 3, 'placeholder': 'Describe how you will use the funds...',
    }))