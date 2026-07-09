from unittest.mock import patch

from django.contrib.auth.models import Group, Permission, User
from django.test import TestCase
from django.urls import reverse

from accounts.models import AccountProfile
from courses.models import Course
from teachers.forms import AdminTeacherCreateForm, TeacherForm
from teachers.models import Teacher


class TeacherFormTests(TestCase):
    def setUp(self):
        self.password = "StrongPass123"
        self.teacher_user = User.objects.create_user(username="teacher-owner", password=self.password)
        self.teacher_profile = AccountProfile.objects.create(
            user=self.teacher_user,
            role=AccountProfile.Role.TEACHER,
            status=AccountProfile.Status.ACTIVE,
        )

    def test_teacher_form_rejects_negative_experience(self):
        form = TeacherForm(
            data={
                "account": self.teacher_profile.pk,
                "employee_code": "TCH-FORM-NEG",
                "specialization": "Mathematics",
                "years_of_experience": -1,
                "status": Teacher.Status.ACTIVE,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("years_of_experience", form.errors)


class AdminTeacherCreationFlowTests(TestCase):
    def setUp(self):
        self.password = "StrongPass123"

        self.admin_user = User.objects.create_user(username="teacher-admin", password=self.password)
        AccountProfile.objects.create(
            user=self.admin_user,
            role=AccountProfile.Role.ADMIN,
            status=AccountProfile.Status.ACTIVE,
        )
        admin_group, _ = Group.objects.get_or_create(name="Administrator")
        self.admin_user.groups.add(admin_group)
        self.admin_user.user_permissions.add(Permission.objects.get(codename="add_teacher"))

        self.student_user = User.objects.create_user(username="student-role-user", password=self.password)
        AccountProfile.objects.create(
            user=self.student_user,
            role=AccountProfile.Role.STUDENT,
            status=AccountProfile.Status.ACTIVE,
        )

        self.teacher_user = User.objects.create_user(username="teacher-role-user", password=self.password)
        AccountProfile.objects.create(
            user=self.teacher_user,
            role=AccountProfile.Role.TEACHER,
            status=AccountProfile.Status.ACTIVE,
        )

        self.course_1 = Course.objects.create(
            code="CRS-TCH-001",
            title="Teacher Course 1",
            grade_level=Course.GradeLevel.FIRST_PRIMARY,
            branch=Course.Branch.GENERAL,
            status=Course.Status.PUBLISHED,
        )
        self.course_2 = Course.objects.create(
            code="CRS-TCH-002",
            title="Teacher Course 2",
            grade_level=Course.GradeLevel.FIRST_PRIMARY,
            branch=Course.Branch.GENERAL,
            status=Course.Status.PUBLISHED,
        )

    def test_admin_teacher_create_form_does_not_require_email_or_password_confirmation(self):
        form = AdminTeacherCreateForm(
            data={
                "full_name": "New Teacher",
                "username": "new-teacher-form",
                "password": "StrongPass123!",
                "specialization": "Mathematics",
                "years_of_experience": 3,
                "status": Teacher.Status.ACTIVE,
            }
        )
        self.assertTrue(form.is_valid())

    def test_admin_creates_teacher_successfully_with_course_assignment(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse("teachers:teacher_create"),
            data={
                "full_name": "Teacher Created By Admin",
                "username": "teacher-created-by-admin",
                "password": "StrongPass123!",
                "specialization": "Mathematics",
                "years_of_experience": 4,
                "status": Teacher.Status.ACTIVE,
                "courses": [self.course_1.pk, self.course_2.pk],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("teachers:teacher_list"))

        created_user = User.objects.get(username="teacher-created-by-admin")
        profile = AccountProfile.objects.get(user=created_user)
        teacher = Teacher.objects.get(account=profile)

        self.assertEqual(profile.role, AccountProfile.Role.TEACHER)
        self.assertEqual(teacher.status, Teacher.Status.ACTIVE)

        self.course_1.refresh_from_db()
        self.course_2.refresh_from_db()
        self.assertEqual(self.course_1.teacher, teacher)
        self.assertEqual(self.course_2.teacher, teacher)

    def test_student_cannot_create_teacher_accounts(self):
        self.client.force_login(self.student_user)
        response = self.client.post(
            reverse("teachers:teacher_create"),
            data={
                "full_name": "Blocked Teacher",
                "username": "blocked-teacher",
                "password": "StrongPass123!",
                "specialization": "Mathematics",
                "status": Teacher.Status.ACTIVE,
            },
        )
        self.assertIn(response.status_code, (302, 403))
        self.assertFalse(User.objects.filter(username="blocked-teacher").exists())

    def test_teacher_cannot_create_teacher_accounts_without_admin_permission(self):
        self.client.force_login(self.teacher_user)
        response = self.client.post(
            reverse("teachers:teacher_create"),
            data={
                "full_name": "Blocked Teacher 2",
                "username": "blocked-teacher-2",
                "password": "StrongPass123!",
                "specialization": "Mathematics",
                "status": Teacher.Status.ACTIVE,
            },
        )
        self.assertIn(response.status_code, (302, 403))
        self.assertFalse(User.objects.filter(username="blocked-teacher-2").exists())

    def test_anonymous_user_cannot_create_teacher_accounts(self):
        response = self.client.post(
            reverse("teachers:teacher_create"),
            data={
                "full_name": "Blocked Anonymous",
                "username": "blocked-anon-teacher",
                "password": "StrongPass123!",
                "specialization": "Mathematics",
                "status": Teacher.Status.ACTIVE,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(username="blocked-anon-teacher").exists())

    def test_teacher_creation_rolls_back_on_failure(self):
        self.client.force_login(self.admin_user)

        with patch("teachers.views.Teacher.objects.create", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    reverse("teachers:teacher_create"),
                    data={
                        "full_name": "Rollback Teacher",
                        "username": "rollback-teacher",
                        "password": "StrongPass123!",
                        "specialization": "Mathematics",
                        "status": Teacher.Status.ACTIVE,
                    },
                )

        self.assertFalse(User.objects.filter(username="rollback-teacher").exists())
        self.assertFalse(AccountProfile.objects.filter(user__username="rollback-teacher").exists())


class TeacherVisibilityTests(TestCase):
    def setUp(self):
        self.password = "StrongPass123"
        self.teacher_user = User.objects.create_user(username="teacher-visible-self", password=self.password)
        teacher_profile = AccountProfile.objects.create(
            user=self.teacher_user,
            role=AccountProfile.Role.TEACHER,
            status=AccountProfile.Status.ACTIVE,
        )
        self.teacher = Teacher.objects.create(
            account=teacher_profile,
            employee_code="TCH-SELF-001",
            specialization="Mathematics",
            status=Teacher.Status.ACTIVE,
        )

        other_user = User.objects.create_user(username="teacher-visible-other", password=self.password)
        other_profile = AccountProfile.objects.create(
            user=other_user,
            role=AccountProfile.Role.TEACHER,
            status=AccountProfile.Status.ACTIVE,
        )
        self.other_teacher = Teacher.objects.create(
            account=other_profile,
            employee_code="TCH-SELF-002",
            specialization="Physics",
            status=Teacher.Status.ACTIVE,
        )

        self.teacher_user.user_permissions.add(Permission.objects.get(codename="view_teacher"))

    def test_teacher_view_permission_is_scoped_to_own_record(self):
        self.client.force_login(self.teacher_user)

        list_response = self.client.get(reverse("teachers:teacher_list"))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, self.teacher.employee_code)
        self.assertNotContains(list_response, self.other_teacher.employee_code)

        detail_response = self.client.get(reverse("teachers:teacher_detail", args=[self.other_teacher.pk]))
        self.assertEqual(detail_response.status_code, 404)
