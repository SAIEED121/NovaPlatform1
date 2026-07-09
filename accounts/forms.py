import re

from django import forms

from .models import AccountProfile


class AccountProfileForm(forms.ModelForm):
    user_email = forms.EmailField(required=True)

    class Meta:
        model = AccountProfile
        fields = ["user", "user_email", "role", "status", "phone_number", "country"]
        widgets = {
            "user": forms.Select(attrs={"class": "form-select"}),
            "role": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "phone_number": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "+9639XXXXXXXX",
                }
            ),
            "country": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Syria",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["user_email"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": "user@example.com",
            }
        )

        if self.instance and self.instance.pk:
            self.fields["user_email"].initial = self.instance.user.email

        for field in self.fields.values():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.setdefault("class", css_class)

    def clean_user_email(self):
        email = self.cleaned_data.get("user_email", "").strip().lower()
        if not email:
            raise forms.ValidationError("Email is required.")
        return email

    def clean_phone_number(self):
        phone_number = self.cleaned_data.get("phone_number", "").strip()
        if phone_number and not re.fullmatch(r"^\+?[0-9]{8,15}$", phone_number):
            raise forms.ValidationError("Phone number must contain 8-15 digits and may start with +.")
        return phone_number

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get("role")
        status = cleaned_data.get("status")
        if not role:
            self.add_error("role", "Role is required.")
        if not status:
            self.add_error("status", "Status is required.")
        return cleaned_data

    def save(self, commit=True):
        profile = super().save(commit=False)
        email = self.cleaned_data.get("user_email", "").strip().lower()

        if profile.user.email != email:
            profile.user.email = email
            if commit:
                profile.user.save(update_fields=["email"])

        if commit:
            profile.save()
            self.save_m2m()

        return profile


class ProfilePhotoForm(forms.ModelForm):
    class Meta:
        model = AccountProfile
        fields = ["profile_photo"]
        widgets = {
            "profile_photo": forms.ClearableFileInput(
                attrs={
                    "class": "w-full p-3 bg-[#111] border border-gray-800 rounded-xl text-white",
                    "accept": "image/png,image/jpeg,image/webp,image/gif",
                }
            ),
        }
