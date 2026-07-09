from django import forms

from .models import Notification
from students.models import Student
from teachers.models import Teacher


class NotificationForm(forms.ModelForm):
    class Meta:
        model = Notification
        fields = [
            "title",
            "message",
            "channel",
            "recipient_type",
            "admin_user",
            "student",
            "teacher",
            "status",
            "sent_at",
            "read_at",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Notification title"}),
            "message": forms.Textarea(
                attrs={"class": "form-control", "placeholder": "Write the notification body", "rows": 4}
            ),
            "channel": forms.Select(attrs={"class": "form-select"}),
            "recipient_type": forms.Select(attrs={"class": "form-select"}),
            "admin_user": forms.Select(attrs={"class": "form-select"}),
            "student": forms.Select(attrs={"class": "form-select"}),
            "teacher": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "sent_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "read_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sent_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["read_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["student"].queryset = Student.objects.select_related("account", "account__user")
        self.fields["teacher"].queryset = Teacher.objects.select_related("account", "account__user")

        for field in self.fields.values():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.setdefault("class", css_class)

    def clean_title(self):
        title = self.cleaned_data.get("title", "").strip()
        if not title:
            raise forms.ValidationError("Title is required.")
        return title

    def clean_message(self):
        message = self.cleaned_data.get("message", "").strip()
        if not message:
            raise forms.ValidationError("Message body is required.")
        return message

    def clean(self):
        cleaned_data = super().clean()

        recipient_type = cleaned_data.get("recipient_type")
        admin_user = cleaned_data.get("admin_user")
        student = cleaned_data.get("student")
        teacher = cleaned_data.get("teacher")
        channel = cleaned_data.get("channel")

        if recipient_type == Notification.RecipientType.ADMIN and not admin_user:
            self.add_error("admin_user", "Admin recipient is required.")

        if recipient_type == Notification.RecipientType.STUDENT and not student:
            self.add_error("student", "Student recipient is required.")

        if recipient_type == Notification.RecipientType.TEACHER and not teacher:
            self.add_error("teacher", "Teacher recipient is required.")

        if recipient_type == Notification.RecipientType.SYSTEM and (admin_user or student or teacher):
            self.add_error("recipient_type", "System notifications cannot target a specific recipient.")

        if recipient_type != Notification.RecipientType.ADMIN:
            cleaned_data["admin_user"] = None
        if recipient_type != Notification.RecipientType.STUDENT:
            cleaned_data["student"] = None
        if recipient_type != Notification.RecipientType.TEACHER:
            cleaned_data["teacher"] = None

        if channel == Notification.Channel.EMAIL:
            if recipient_type == Notification.RecipientType.STUDENT and student:
                user_email = student.account.user.email
                if not user_email:
                    self.add_error("student", "Selected student does not have an email address.")
            if recipient_type == Notification.RecipientType.TEACHER and teacher:
                user_email = teacher.account.user.email
                if not user_email:
                    self.add_error("teacher", "Selected teacher does not have an email address.")

        return cleaned_data
