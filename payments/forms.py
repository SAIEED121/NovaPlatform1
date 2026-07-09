import re

from django import forms

from .models import Payment
from students.models import Student
from subscriptions.models import StudentSubscription


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = [
            "student",
            "requested_by",
            "approved_by",
            "subscription",
            "amount",
            "currency",
            "method",
            "status",
            "transaction_reference",
            "paid_at",
            "approved_at",
            "notes",
        ]
        widgets = {
            "student": forms.Select(attrs={"class": "form-select"}),
            "requested_by": forms.Select(attrs={"class": "form-select"}),
            "approved_by": forms.Select(attrs={"class": "form-select"}),
            "subscription": forms.Select(attrs={"class": "form-select"}),
            "amount": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "0.00", "step": "0.01", "min": "0.01"}
            ),
            "currency": forms.TextInput(attrs={"class": "form-control", "placeholder": "SYP"}),
            "method": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "transaction_reference": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "TXN-2026-000001"}
            ),
            "paid_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "approved_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "notes": forms.Textarea(
                attrs={"class": "form-control", "placeholder": "Optional notes", "rows": 3}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["paid_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["approved_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["student"].queryset = Student.objects.select_related("account", "account__user")
        self.fields["subscription"].queryset = StudentSubscription.objects.select_related("student", "plan")

        for field in self.fields.values():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.setdefault("class", css_class)

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is None or amount <= 0:
            raise forms.ValidationError("Payment amount must be greater than zero.")
        return amount

    def clean_currency(self):
        currency = self.cleaned_data.get("currency", "").strip().upper()
        if not re.fullmatch(r"^[A-Z]{3}$", currency):
            raise forms.ValidationError("Currency must be a 3-letter ISO code.")
        return currency

    def clean_transaction_reference(self):
        transaction_reference = (self.cleaned_data.get("transaction_reference") or "").strip()
        return transaction_reference or None

    def clean(self):
        cleaned_data = super().clean()
        student = cleaned_data.get("student")
        subscription = cleaned_data.get("subscription")
        method = cleaned_data.get("method")
        status = cleaned_data.get("status")
        transaction_reference = cleaned_data.get("transaction_reference")
        paid_at = cleaned_data.get("paid_at")

        if subscription and student and subscription.student_id != student.id:
            self.add_error(
                "subscription",
                "Selected subscription must belong to the selected student.",
            )

        if method != Payment.Method.CASH and not transaction_reference:
            self.add_error(
                "transaction_reference",
                "Transaction reference is required for non-cash payments.",
            )

        if status == Payment.Status.SUCCESSFUL and not paid_at:
            self.add_error("paid_at", "Paid at is required for successful payments.")

        return cleaned_data


class PaymentRequestForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        queryset = StudentSubscription.objects.select_related("student", "plan")
        if self.user and self.user.is_authenticated:
            queryset = queryset.filter(student__account__user=self.user)
        else:
            queryset = queryset.none()
        self.fields["subscription"].queryset = queryset

    class Meta:
        model = Payment
        fields = ["subscription", "amount", "currency", "method", "transaction_reference", "notes"]
        widgets = {
            "subscription": forms.Select(attrs={"class": "form-select"}),
            "amount": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "0.00", "step": "0.01", "min": "0.01"}
            ),
            "currency": forms.TextInput(attrs={"class": "form-control", "placeholder": "SYP"}),
            "method": forms.Select(attrs={"class": "form-select"}),
            "transaction_reference": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "TXN-2026-000001"}
            ),
            "notes": forms.Textarea(
                attrs={"class": "form-control", "placeholder": "Payment request notes", "rows": 3}
            ),
        }

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is None or amount <= 0:
            raise forms.ValidationError("Payment amount must be greater than zero.")
        return amount

    def clean_currency(self):
        currency = self.cleaned_data.get("currency", "").strip().upper()
        if not re.fullmatch(r"^[A-Z]{3}$", currency):
            raise forms.ValidationError("Currency must be a 3-letter ISO code.")
        return currency

    def clean_transaction_reference(self):
        return (self.cleaned_data.get("transaction_reference") or "").strip() or None

    def clean_subscription(self):
        subscription = self.cleaned_data.get("subscription")
        if subscription is None:
            return None
        if self.user is None or not self.user.is_authenticated:
            raise forms.ValidationError("You must be signed in to use a subscription.")
        if subscription.student.account.user_id != self.user.id:
            raise forms.ValidationError("You can only attach your own subscription.")
        return subscription

    def clean(self):
        cleaned_data = super().clean()
        method = cleaned_data.get("method")
        transaction_reference = cleaned_data.get("transaction_reference")
        if method != Payment.Method.CASH and not transaction_reference:
            self.add_error(
                "transaction_reference",
                "Transaction reference is required for non-cash payment requests.",
            )
        return cleaned_data


class PaymentApprovalForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["status", "notes", "paid_at"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-select"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "paid_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["paid_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["status"].choices = [
            (Payment.Status.SUCCESSFUL, Payment.Status.SUCCESSFUL.label),
            (Payment.Status.FAILED, Payment.Status.FAILED.label),
            (Payment.Status.REFUNDED, Payment.Status.REFUNDED.label),
        ]

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get("status")
        paid_at = cleaned_data.get("paid_at")

        if status == Payment.Status.SUCCESSFUL and not paid_at:
            self.add_error("paid_at", "Paid at is required when approving payment.")

        return cleaned_data
