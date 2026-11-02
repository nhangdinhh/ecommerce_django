from django import forms
from django_countries.fields import CountryField
from django_countries.widgets import CountrySelectWidget
from .models import UserProfile

class CheckoutForm(forms.Form):
    recipient_name = forms.CharField(max_length=150, required=True, widget=forms.TextInput(attrs={
        'placeholder': 'Full name of recipient',
        'class': 'form-control',
        'autocomplete': 'name',
        'required': True,
    }))

    phone_number = forms.CharField(max_length=15, required=True, widget=forms.TextInput(attrs={
        'placeholder': 'Your phone number',
        'class': 'form-control',
        'autocomplete': 'tel',
        'inputmode': 'tel',
        'type': 'tel',
        'required': True,
    }))

    street_address = forms.CharField(max_length=100, required=True, widget=forms.TextInput(attrs={
        'placeholder': 'Street, district, city',
        'class': 'form-control',
        'autocomplete': 'street-address',
        'required': True,
    }))

    def clean(self):
        cleaned = super().clean()
        # Validate submitted values on the server too; browser-only checks can be bypassed.
        recipient = (cleaned.get('recipient_name') or '').strip()
        phone = (cleaned.get('phone_number') or '').strip()
        street = (cleaned.get('street_address') or '').strip()
        if not recipient:
            self.add_error('recipient_name', 'Enter the recipient’s full name.')
        elif sum(character.isalpha() for character in recipient) < 2 or any(
            not (character.isalpha() or character.isspace() or character in "-'.’")
            for character in recipient
        ):
            self.add_error('recipient_name', 'Enter a valid name using letters, spaces, apostrophes or hyphens.')

        digits = ''.join(character for character in phone if character.isdigit())
        if not phone:
            self.add_error('phone_number', 'Enter a phone number for delivery.')
        elif (
            len(digits) < 8
            or len(digits) > 15
            or any(character not in '+()- .0123456789' for character in phone)
            or phone.count('+') > 1
            or ('+' in phone and not phone.startswith('+'))
            or not any(character.isdigit() for character in phone)
        ):
            self.add_error('phone_number', 'Enter a valid phone number with 8 to 15 digits.')

        allowed_address_chars = " ,.#/'-"
        if len(street) < 8 or sum(character.isalpha() for character in street) < 3 or any(
            not (character.isalpha() or character.isdigit() or character.isspace() or character in allowed_address_chars)
            for character in street
        ):
            self.add_error('street_address', 'Enter a complete delivery address (at least 8 characters).')
        return cleaned


class CouponForm(forms.Form):
    code = forms.CharField(widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': 'Promo code'
    }))


class RefundForm(forms.Form):
    ref_code = forms.CharField()
    message = forms.CharField(widget=forms.Textarea(attrs={
        'rows': 4
    }))
    email = forms.EmailField()


class ProfileForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150, required=False, label="First name", widget=forms.TextInput(attrs={"class": "profile-input", "autocomplete": "given-name"}))
    last_name = forms.CharField(max_length=150, required=False, label="Last name", widget=forms.TextInput(attrs={"class": "profile-input", "autocomplete": "family-name"}))
    email = forms.EmailField(required=False, label="Email address", widget=forms.EmailInput(attrs={"class": "profile-input", "autocomplete": "email"}))

    class Meta:
        model = UserProfile
        fields = ("phone", "address", "avatar")
        labels = {
            "phone": "Phone number",
            "address": "Delivery address",
            "avatar": "Profile photo",
        }
        widgets = {
            "phone": forms.TextInput(attrs={"class": "profile-input", "autocomplete": "tel", "placeholder": "Your phone number"}),
            "address": forms.Textarea(attrs={"class": "profile-input profile-input--textarea", "rows": 3, "autocomplete": "street-address", "placeholder": "Street, district, city"}),
            "avatar": forms.ClearableFileInput(attrs={"class": "profile-file", "accept": "image/*"}),
        }
