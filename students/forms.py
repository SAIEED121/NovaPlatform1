import re

from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError

from accounts.models import AccountProfile
from courses.models import Course
from subscriptions.models import SubscriptionPlan
from .models import Student
from novaplatform_backend.academic_subjects import (
    BRANCHED_SECONDARY_GRADES,
    GENERAL_BRANCH,
    GENERAL_ONLY_GRADES,
    LITERARY_BRANCH,
    SCIENCE_BRANCH,
    branch_validation_error,
)


User = get_user_model()


class AdminStudentCreateForm(forms.Form):
    full_name = forms.CharField(max_length=150)
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)
    phone_number = forms.CharField(max_length=20, required=False)
    grade_level = forms.ChoiceField(choices=Student.GradeLevel.choices)
    branch = forms.ChoiceField(choices=Student.Branch.choices, required=False)
    guardian_name = forms.CharField(max_length=150, required=False)
    guardian_phone = forms.CharField(max_length=20, required=False)
    subscription_plan = forms.ModelChoiceField(
        queryset=SubscriptionPlan.objects.filter(status=SubscriptionPlan.Status.ACTIVE).order_by("name"),
        required=False,
    )
    student_status = forms.ChoiceField(choices=Student.Status.choices, initial=Student.Status.ACTIVE)
    courses = forms.ModelMultipleChoiceField(
        queryset=Course.objects.order_by("code"),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["full_name"].widget.attrs.update({"class": "form-control", "placeholder": "Student full name"})
        self.fields["username"].widget.attrs.update({"class": "form-control", "placeholder": "student_username"})
        self.fields["password"].widget.attrs.update({"class": "form-control", "placeholder": "Strong password"})
        self.fields["phone_number"].widget.attrs.update({"class": "form-control", "placeholder": "+9639XXXXXXXX"})
        self.fields["grade_level"].widget.attrs.update({"class": "form-select"})
        self.fields["branch"].widget.attrs.update({"class": "form-select"})
        self.fields["guardian_name"].widget.attrs.update({"class": "form-control", "placeholder": "Guardian name"})
        self.fields["guardian_phone"].widget.attrs.update({"class": "form-control", "placeholder": "+9639XXXXXXXX"})
        self.fields["subscription_plan"].widget.attrs.update({"class": "form-select"})
        self.fields["student_status"].widget.attrs.update({"class": "form-select"})
        self.fields["courses"].widget.attrs.update({"class": "form-select", "size": "8"})

        grade_level = self.data.get("grade_level")
        self._configure_branch_field(grade_level)

    def _configure_branch_field(self, grade_level):
        if grade_level in GENERAL_ONLY_GRADES:
            self.fields["branch"].choices = [(GENERAL_BRANCH, "General")]
            self.fields["branch"].help_text = "This grade remains general and does not use Science/Literary branches."
        elif grade_level in BRANCHED_SECONDARY_GRADES:
            self.fields["branch"].choices = [
                (SCIENCE_BRANCH, "Science"),
                (LITERARY_BRANCH, "Literary"),
            ]
            self.fields["branch"].help_text = "Second and third secondary grades must choose either Science or Literary."
        else:
            self.fields["branch"].help_text = ""

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

    def clean_phone_number(self):
        phone_number = self.cleaned_data.get("phone_number", "").strip()
        if phone_number and not re.fullmatch(r"^\+?[0-9]{8,15}$", phone_number):
            raise forms.ValidationError("Phone number must contain 8-15 digits and may start with +.")
        return phone_number

    def clean_guardian_phone(self):
        guardian_phone = self.cleaned_data.get("guardian_phone", "").strip()
        if guardian_phone and not re.fullmatch(r"^\+?[0-9]{8,15}$", guardian_phone):
            raise forms.ValidationError("Guardian phone must contain 8-15 digits and may start with +.")
        return guardian_phone

    def clean(self):
        cleaned_data = super().clean()
        grade_level = cleaned_data.get("grade_level")
        branch = cleaned_data.get("branch") or Student.Branch.GENERAL
        guardian_name = (cleaned_data.get("guardian_name") or "").strip()
        guardian_phone = (cleaned_data.get("guardian_phone") or "").strip()

        if guardian_phone and not guardian_name:
            self.add_error("guardian_name", "Guardian name is required when guardian phone is provided.")

        branch_error = branch_validation_error(grade_level, branch)
        if branch_error:
            self.add_error("branch", branch_error)

        cleaned_data["branch"] = branch
        return cleaned_data


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = [
            "account",
            "student_code",
            "grade_level",
            "branch",
            "status",
            "date_of_birth",
            "guardian_name",
            "guardian_phone",
        ]
        widgets = {
            "account": forms.Select(attrs={"class": "form-select"}),
            "student_code": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "STD-2026-0001",
                }
            ),
            "grade_level": forms.Select(attrs={"class": "form-select"}),
            "branch": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "date_of_birth": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),
            "guardian_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Guardian full name",
                }
            ),
            "guardian_phone": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "+9639XXXXXXXX",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account"].queryset = AccountProfile.objects.select_related("user")
        for field in self.fields.values():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.setdefault("class", css_class)

        grade_level = self.data.get("grade_level") or getattr(self.instance, "grade_level", None)
        self._configure_branch_field(grade_level)

    def _configure_branch_field(self, grade_level):
        if grade_level in GENERAL_ONLY_GRADES:
            self.fields["branch"].choices = [(GENERAL_BRANCH, "General")]
            self.fields["branch"].help_text = "This grade remains general and does not use Science/Literary branches."
        elif grade_level in BRANCHED_SECONDARY_GRADES:
            self.fields["branch"].choices = [
                (SCIENCE_BRANCH, "Science"),
                (LITERARY_BRANCH, "Literary"),
            ]
            self.fields["branch"].help_text = "Second and third secondary grades must choose either Science or Literary."
        else:
            self.fields["branch"].help_text = ""

    def clean_student_code(self):
        student_code = self.cleaned_data.get("student_code", "").strip().upper()
        if not student_code:
            raise forms.ValidationError("Student code is required.")
        return student_code

    def clean_guardian_phone(self):
        guardian_phone = self.cleaned_data.get("guardian_phone", "").strip()
        if guardian_phone and not re.fullmatch(r"^\+?[0-9]{8,15}$", guardian_phone):
            raise forms.ValidationError("Guardian phone must contain 8-15 digits and may start with +.")
        return guardian_phone

    def clean(self):
        cleaned_data = super().clean()
        guardian_name = (cleaned_data.get("guardian_name") or "").strip()
        guardian_phone = (cleaned_data.get("guardian_phone") or "").strip()

        if guardian_phone and not guardian_name:
            self.add_error("guardian_name", "Guardian name is required when guardian phone is provided.")

        if not cleaned_data.get("grade_level"):
            self.add_error("grade_level", "Grade level is required.")

        branch_error = branch_validation_error(cleaned_data.get("grade_level"), cleaned_data.get("branch"))
        if branch_error:
            self.add_error("branch", branch_error)

        return cleaned_data
