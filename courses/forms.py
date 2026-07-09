from django import forms
from django.utils import timezone

from .models import Category, Course, Enrollment, HomeworkSubmission, Lesson, Schedule
from novaplatform_backend.academic_subjects import (
    BRANCHED_SECONDARY_GRADES,
    GENERAL_BRANCH,
    GENERAL_ONLY_GRADES,
    LITERARY_BRANCH,
    SCIENCE_BRANCH,
    branch_validation_error,
)


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "description", "status"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Mathematics"}),
            "description": forms.Textarea(
                attrs={"class": "form-control", "placeholder": "Category description", "rows": 3}
            ),
            "status": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_name(self):
        name = self.cleaned_data.get("name", "").strip()
        if not name:
            raise forms.ValidationError("Category name is required.")
        return name


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = [
            "code",
            "title",
            "description",
            "category",
            "teacher",
            "grade_level",
            "branch",
            "price",
            "status",
            "start_date",
            "end_date",
        ]
        widgets = {
            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": "CRS-001"}),
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Course title"}),
            "description": forms.Textarea(
                attrs={"class": "form-control", "placeholder": "Course description", "rows": 4}
            ),
            "category": forms.Select(attrs={"class": "form-select"}),
            "teacher": forms.Select(attrs={"class": "form-select"}),
            "grade_level": forms.Select(attrs={"class": "form-select"}),
            "branch": forms.Select(attrs={"class": "form-select"}),
            "price": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "0.00", "step": "0.01", "min": "0"}
            ),
            "status": forms.Select(attrs={"class": "form-select"}),
            "start_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "end_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["teacher"].queryset = self.fields["teacher"].queryset.select_related("account", "account__user")
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

    def clean_code(self):
        code = self.cleaned_data.get("code", "").strip().upper()
        if not code:
            raise forms.ValidationError("Course code is required.")
        return code

    def clean_title(self):
        title = self.cleaned_data.get("title", "").strip()
        if not title:
            raise forms.ValidationError("Course title is required.")
        return title

    def clean_price(self):
        price = self.cleaned_data.get("price")
        if price is None or price < 0:
            raise forms.ValidationError("Price must be a non-negative value.")
        return price

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", "End date must be after or equal to start date.")

        branch_error = branch_validation_error(cleaned_data.get("grade_level"), cleaned_data.get("branch"))
        if branch_error:
            self.add_error("branch", branch_error)
        return cleaned_data


class EnrollmentForm(forms.ModelForm):
    class Meta:
        model = Enrollment
        fields = ["student", "course", "status", "progress_percent", "completed_at"]
        widgets = {
            "student": forms.Select(attrs={"class": "form-select"}),
            "course": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "progress_percent": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "0-100", "min": 0, "max": 100}
            ),
            "completed_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["completed_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["student"].queryset = self.fields["student"].queryset.select_related("account", "account__user")
        for field in self.fields.values():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.setdefault("class", css_class)

    def clean_progress_percent(self):
        progress_percent = self.cleaned_data.get("progress_percent")
        if progress_percent is None or progress_percent < 0 or progress_percent > 100:
            raise forms.ValidationError("Progress must be between 0 and 100.")
        return progress_percent

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get("status")
        completed_at = cleaned_data.get("completed_at")

        if status == Enrollment.Status.COMPLETED and not completed_at:
            self.add_error("completed_at", "Completed at is required when status is completed.")

        if completed_at and completed_at > timezone.now():
            self.add_error("completed_at", "Completed at cannot be in the future.")

        return cleaned_data


class LessonForm(forms.ModelForm):
    class Meta:
        model = Lesson
        fields = [
            "course",
            "title",
            "description",
            "order",
            "duration_minutes",
            "video_url",
            "is_published",
            "due_date",
        ]
        widgets = {
            "course": forms.Select(attrs={"class": "form-select"}),
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Lesson title"}),
            "description": forms.Textarea(
                attrs={"class": "form-control", "placeholder": "Lesson description", "rows": 3}
            ),
            "order": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "duration_minutes": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "video_url": forms.URLInput(attrs={"class": "form-control", "placeholder": "https://..."}),
            "is_published": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "due_date": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["due_date"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["course"].queryset = self.fields["course"].queryset.only("id", "code", "title")

    def clean_title(self):
        title = self.cleaned_data.get("title", "").strip()
        if not title:
            raise forms.ValidationError("Lesson title is required.")
        return title

    def clean_order(self):
        order = self.cleaned_data.get("order")
        if order is None or order < 1:
            raise forms.ValidationError("Lesson order must be at least 1.")
        return order


class ScheduleForm(forms.ModelForm):
    class Meta:
        model = Schedule
        fields = ["course", "lesson", "title", "starts_at", "ends_at", "meeting_url", "is_live", "notes"]
        widgets = {
            "course": forms.Select(attrs={"class": "form-select"}),
            "lesson": forms.Select(attrs={"class": "form-select"}),
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Session title"}),
            "starts_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "ends_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "meeting_url": forms.URLInput(attrs={"class": "form-control", "placeholder": "https://..."}),
            "is_live": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Notes"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["starts_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["ends_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["course"].queryset = self.fields["course"].queryset.only("id", "code", "title")
        self.fields["lesson"].queryset = self.fields["lesson"].queryset.select_related("course").only(
            "id", "title", "order", "course__id", "course__code"
        )

    def clean_title(self):
        title = self.cleaned_data.get("title", "").strip()
        if not title:
            raise forms.ValidationError("Schedule title is required.")
        return title

    def clean(self):
        cleaned_data = super().clean()
        starts_at = cleaned_data.get("starts_at")
        ends_at = cleaned_data.get("ends_at")
        course = cleaned_data.get("course")
        lesson = cleaned_data.get("lesson")

        if starts_at and ends_at and ends_at <= starts_at:
            self.add_error("ends_at", "End datetime must be after start datetime.")

        if lesson and course and lesson.course_id != course.id:
            self.add_error("lesson", "Selected lesson does not belong to selected course.")

        return cleaned_data


class TeacherAssignmentForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ["teacher"]
        widgets = {
            "teacher": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["teacher"].queryset = self.fields["teacher"].queryset.select_related("account", "account__user")


class HomeworkSubmissionForm(forms.ModelForm):
    class Meta:
        model = HomeworkSubmission
        fields = ["enrollment", "lesson", "title", "description", "attachment", "status", "grade", "feedback"]
        widgets = {
            "enrollment": forms.Select(attrs={"class": "form-select"}),
            "lesson": forms.Select(attrs={"class": "form-select"}),
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Homework title"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Description"}),
            "attachment": forms.ClearableFileInput(
                attrs={
                    "class": "form-control",
                    "accept": ".jpg,.jpeg,.png,.webp,.gif,.pdf",
                }
            ),
            "status": forms.Select(attrs={"class": "form-select"}),
            "grade": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "feedback": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Feedback"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["enrollment"].queryset = self.fields["enrollment"].queryset.select_related("student", "course")
        self.fields["lesson"].queryset = self.fields["lesson"].queryset.select_related("course").only(
            "id", "title", "order", "course__id", "course__code"
        )
        for field in self.fields.values():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.setdefault("class", css_class)

    def clean_title(self):
        title = self.cleaned_data.get("title", "").strip()
        if not title:
            raise forms.ValidationError("Homework title is required.")
        return title

    def clean_grade(self):
        grade = self.cleaned_data.get("grade")
        if grade is not None and grade < 0:
            raise forms.ValidationError("Grade cannot be negative.")
        return grade

    def clean(self):
        cleaned_data = super().clean()
        enrollment = cleaned_data.get("enrollment")
        lesson = cleaned_data.get("lesson")

        if lesson and enrollment and lesson.course_id != enrollment.course_id:
            self.add_error("lesson", "Selected lesson does not belong to the enrollment course.")

        return cleaned_data
