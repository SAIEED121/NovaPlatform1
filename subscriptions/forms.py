from django import forms

from .models import PlanCourse, StudentSubscription, SubscriptionPlan


class SubscriptionPlanForm(forms.ModelForm):
    class Meta:
        model = SubscriptionPlan
        fields = ["name", "description", "duration_days", "price", "status"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Premium Plan"}),
            "description": forms.Textarea(
                attrs={"class": "form-control", "placeholder": "Plan benefits and notes", "rows": 4}
            ),
            "duration_days": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "30", "min": 1}
            ),
            "price": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "0.00", "step": "0.01", "min": "0"}
            ),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.setdefault("class", css_class)

    def clean_name(self):
        name = self.cleaned_data.get("name", "").strip()
        if not name:
            raise forms.ValidationError("Plan name is required.")
        return name

    def clean_duration_days(self):
        duration_days = self.cleaned_data.get("duration_days")
        if duration_days is None or duration_days <= 0:
            raise forms.ValidationError("Duration must be greater than zero.")
        return duration_days

    def clean_price(self):
        price = self.cleaned_data.get("price")
        if price is None or price < 0:
            raise forms.ValidationError("Price must be a non-negative value.")
        return price


class PlanCourseForm(forms.ModelForm):
    class Meta:
        model = PlanCourse
        fields = ["plan", "course"]
        widgets = {
            "plan": forms.Select(attrs={"class": "form-select"}),
            "course": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.setdefault("class", css_class)

    def clean(self):
        cleaned_data = super().clean()
        plan = cleaned_data.get("plan")
        course = cleaned_data.get("course")

        if plan and course:
            exists = PlanCourse.objects.filter(plan=plan, course=course)
            if self.instance.pk:
                exists = exists.exclude(pk=self.instance.pk)
            if exists.exists():
                raise forms.ValidationError("This course is already linked to the selected plan.")

        return cleaned_data


class StudentSubscriptionForm(forms.ModelForm):
    class Meta:
        model = StudentSubscription
        fields = ["student", "plan", "status", "started_at", "ends_at", "auto_renew"]
        widgets = {
            "student": forms.Select(attrs={"class": "form-select"}),
            "plan": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "started_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "ends_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "auto_renew": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = self.fields["student"].queryset.select_related("account", "account__user")
        self.fields["started_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["ends_at"].input_formats = ["%Y-%m-%dT%H:%M"]

        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
                continue
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.setdefault("class", css_class)

    def clean(self):
        cleaned_data = super().clean()
        started_at = cleaned_data.get("started_at")
        ends_at = cleaned_data.get("ends_at")
        status = cleaned_data.get("status")

        if started_at and ends_at and ends_at <= started_at:
            self.add_error("ends_at", "Subscription end date must be after start date.")

        if status in {StudentSubscription.Status.ACTIVE, StudentSubscription.Status.PENDING} and not cleaned_data.get("plan"):
            self.add_error("plan", "Active or pending subscription must be linked to a plan.")

        if status in {StudentSubscription.Status.PENDING, StudentSubscription.Status.ACTIVE} and started_at and ends_at and ends_at <= started_at:
            self.add_error("status", "Pending or active subscription cannot have an already-expired period.")

        return cleaned_data
