from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError

from accounts.models import AccountProfile
from courses.models import Course
from .models import Teacher
from novaplatform_backend.academic_subjects import TEACHER_SPECIALIZATION_CHOICES


User = get_user_model()


class AdminTeacherCreateForm(forms.Form):
    full_name = forms.CharField(max_length=150)
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)
    specialization = forms.ChoiceField(choices=TEACHER_SPECIALIZATION_CHOICES)
    years_of_experience = forms.IntegerField(min_value=0, required=False, initial=0)
    status = forms.ChoiceField(choices=Teacher.Status.choices, initial=Teacher.Status.ACTIVE)
    courses = forms.ModelMultipleChoiceField(
        queryset=Course.objects.order_by("code"),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["full_name"].widget.attrs.update({"class": "form-control", "placeholder": "Teacher full name"})
        self.fields["username"].widget.attrs.update({"class": "form-control", "placeholder": "teacher_username"})
        self.fields["password"].widget.attrs.update({"class": "form-control", "placeholder": "Strong password"})
        self.fields["specialization"].widget.attrs.update({"class": "form-select"})
        self.fields["years_of_experience"].widget.attrs.update({"class": "form-control", "min": 0})
        self.fields["status"].widget.attrs.update({"class": "form-select"})
        self.fields["courses"].widget.attrs.update({"class": "form-select", "size": "8"})

    def clean_full_name(self):
        full_name = self.cleaned_data.get("full_name", "").strip()
        if not full_name:
            raise forms.ValidationError("Full name is required.")
        return full_name

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        if not username:
            raise forms.ValidationError("Username is required.")
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if not password:
            raise forms.ValidationError("Password is required.")
        try:
            password_validation.validate_password(password)
        except DjangoValidationError as exc:
            raise forms.ValidationError(exc.messages)
        return password

    def clean_years_of_experience(self):
        years_of_experience = self.cleaned_data.get("years_of_experience")
        if years_of_experience is None:
            return 0
        if years_of_experience < 0:
            raise forms.ValidationError("Years of experience cannot be negative.")
        return years_of_experience

    def clean_specialization(self):
        specialization = self.cleaned_data.get("specialization")
        allowed_specializations = {choice for choice, _ in TEACHER_SPECIALIZATION_CHOICES}
        if specialization not in allowed_specializations:
            raise forms.ValidationError("Select a supported specialization.")
        return specialization


class TeacherForm(forms.ModelForm):
    class Meta:
        model = Teacher
        fields = [
            "account",
            "employee_code",
            "specialization",
            "bio",
            "years_of_experience",
            "status",
            "hired_at",
        ]
        widgets = {
            "account": forms.Select(attrs={"class": "form-select"}),
            "employee_code": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "EMP-2026-0001",
                }
            ),
            "specialization": forms.Select(attrs={"class": "form-select"}),
            "bio": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "placeholder": "Short professional bio",
                    "rows": 4,
                }
            ),
            "years_of_experience": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "0",
                    "min": 0,
                }
            ),
            "status": forms.Select(attrs={"class": "form-select"}),
            "hired_at": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account"].queryset = AccountProfile.objects.select_related("user")
        for field in self.fields.values():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.setdefault("class", css_class)

        specialization_choices = list(TEACHER_SPECIALIZATION_CHOICES)
        current_specialization = getattr(self.instance, "specialization", "")
        if current_specialization and current_specialization not in dict(specialization_choices):
            specialization_choices.insert(0, (current_specialization, current_specialization))
        self.fields["specialization"].choices = [("", "Select subject specialization")] + specialization_choices
        self.fields["specialization"].help_text = "Teacher assignment is limited to the supported academic subjects."

    def clean_employee_code(self):
        employee_code = self.cleaned_data.get("employee_code", "").strip().upper()
        if not employee_code:
            raise forms.ValidationError("Employee code is required.")
        return employee_code

    def clean_years_of_experience(self):
        years_of_experience = self.cleaned_data.get("years_of_experience")
        if years_of_experience is None:
            return 0
        if years_of_experience < 0:
            raise forms.ValidationError("Years of experience cannot be negative.")
        return years_of_experience

    def clean(self):
        cleaned_data = super().clean()
        specialization = cleaned_data.get("specialization")
        allowed_specializations = {choice for choice, _ in TEACHER_SPECIALIZATION_CHOICES}

        if not specialization:
            self.add_error("specialization", "Specialization is required.")
        elif specialization not in allowed_specializations:
            self.add_error("specialization", "Select a supported specialization.")
        return cleaned_data
