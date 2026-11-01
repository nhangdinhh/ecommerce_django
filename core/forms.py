from django import forms
from django_countries.fields import CountryField
from django_countries.widgets import CountrySelectWidget
from .models import UserProfile, BillingAddress


class AddressSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        address = getattr(value, 'instance', None)
        if address:
            option['attrs'].update({
                'data-recipient': address.recipient_name,
                'data-phone': address.phone_number,
                'data-street': address.street_address,
            })
        return option

class CheckoutForm(forms.Form):
    saved_address = forms.ModelChoiceField(queryset=BillingAddress.objects.none(), required=False, label='Saved delivery address', widget=AddressSelect(attrs={'class': 'form-control'}))
    recipient_name = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={
        'placeholder': 'Full name of recipient',
        'class': 'form-control',
        'autocomplete': 'name',
    }))

    phone_number = forms.CharField(max_length=15, required=False, widget=forms.TextInput(attrs={
        'placeholder': 'Your phone number',
        'class': 'form-control'
    }))

    street_address = forms.CharField(max_length=100, required=False, widget=forms.TextInput(attrs={
        'placeholder': '1234 Main St',
        'class': 'form-control'
    }))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['saved_address'].queryset = BillingAddress.objects.filter(user=user) if user and user.is_authenticated else BillingAddress.objects.none()

    def clean(self):
        cleaned = super().clean()
        address = cleaned.get('saved_address')
        if address:
            cleaned['recipient_name'] = address.recipient_name
            cleaned['phone_number'] = address.phone_number
            cleaned['street_address'] = address.street_address
        elif not all((cleaned.get('recipient_name'), cleaned.get('phone_number'), cleaned.get('street_address'))):
            raise forms.ValidationError('Choose a saved address or complete the delivery details.')
        return cleaned

    def clean_phone_number(self):
        phone = (self.cleaned_data.get('phone_number') or '').strip()
        if not phone:
            return phone
        digits = ''.join(character for character in phone if character.isdigit())
        if len(digits) < 8 or len(digits) > 15:
            raise forms.ValidationError('Enter a valid phone number with 8 to 15 digits.')
        if any(character not in '+()- .0123456789' for character in phone):
            raise forms.ValidationError('Use digits and common phone separators only.')
        return phone


class BillingAddressForm(forms.ModelForm):
    class Meta:
        model = BillingAddress
        fields = ('recipient_name', 'phone_number', 'street_address', 'default')
        widgets = {
            'recipient_name': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'name'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'tel'}),
            'street_address': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'street-address'}),
        }

    def clean_phone_number(self):
        phone = self.cleaned_data['phone_number'].strip()
        digits = ''.join(character for character in phone if character.isdigit())
        if len(digits) < 8 or len(digits) > 15 or any(c not in '+()- .0123456789' for c in phone):
            raise forms.ValidationError('Enter a valid phone number with 8 to 15 digits.')
        return phone


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
