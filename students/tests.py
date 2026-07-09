from unittest.mock import patch

from django.contrib.auth.models import Group, Permission, User
from django.test import TestCase
from django.urls import reverse

from accounts.models import AccountProfile
from courses.models import Course, Enrollment
from students.forms import AdminStudentCreateForm, StudentForm
from students.models import Student
from subscriptions.models import StudentSubscription, SubscriptionPlan


class StudentFormTests(TestCase):
    def setUp(self):
        self.password = "StrongPass123"
        self.student_user = User.objects.create_user(username="student-owner", password=self.password)
        self.student_profile = AccountProfile.objects.create(
            user=self.student_user,
            role=AccountProfile.Role.STUDENT,
            status=AccountProfile.Status.ACTIVE,
        )

    def test_student_form_validates_guardian_dependency(self):
        form = StudentForm(
            data={
                "account": self.student_profile.pk,
                "student_code": "stu-form-001",
                "grade_level": Student.GradeLevel.FIRST_PRIMARY,
                "branch": Student.Branch.GENERAL,
                "status": Student.Status.ACTIVE,
                "guardian_name": "",
                "guardian_phone": "+963987654321",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("guardian_name", form.errors)


class AdminStudentCreationFlowTests(TestCase):
    def setUp(self):
        self.password = "StrongPass123"

        self.admin_user = User.objects.create_user(username="student-admin", password=self.password)
        AccountProfile.objects.create(
            user=self.admin_user,
            role=AccountProfile.Role.ADMIN,
            status=AccountProfile.Status.ACTIVE,
        )
        admin_group, _ = Group.objects.get_or_create(name="Administrator")
        self.admin_user.groups.add(admin_group)
        self.admin_user.user_permissions.add(Permission.objects.get(codename="add_student"))

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
            code="CRS-STU-001",
            title="Student Course 1",
            grade_level=Course.GradeLevel.FIRST_PRIMARY,
            branch=Course.Branch.GENERAL,
            status=Course.Status.PUBLISHED,
        )
        self.course_2 = Course.objects.create(
            code="CRS-STU-002",
            title="Student Course 2",
            grade_level=Course.GradeLevel.FIRST_PRIMARY,
            branch=Course.Branch.GENERAL,
            status=Course.Status.PUBLISHED,
        )
        self.plan = SubscriptionPlan.objects.create(
            name="Student Starter",
            duration_days=30,
            price="50000.00",
            status=SubscriptionPlan.Status.ACTIVE,
        )

    def test_admin_student_create_form_does_not_require_email_or_password_confirmation(self):
        form = AdminStudentCreateForm(
            data={
                "full_name": "New Student",
                "username": "new-student-form",
                "password": "StrongPass123!",
                "phone_number": "+963955551111",
                "grade_level": Student.GradeLevel.FIRST_PRIMARY,
                "branch": Student.Branch.GENERAL,
                "student_status": Student.Status.ACTIVE,
            }
        )
        self.assertTrue(form.is_valid())

    def test_admin_creates_student_successfully_with_subscription_and_enrollments(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse("students:student_create"),
            data={
                "full_name": "Student Created By Admin",
                "username": "student-created-by-admin",
                "password": "StrongPass123!",
                "phone_number": "+963955552222",
                "grade_level": Student.GradeLevel.FIRST_PRIMARY,
                "branch": Student.Branch.GENERAL,
                "guardian_name": "Guardian Name",
                "guardian_phone": "+963955553333",
                "subscription_plan": self.plan.pk,
                "student_status": Student.Status.ACTIVE,
                "courses": [self.course_1.pk, self.course_2.pk],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("students:student_list"))

        created_user = User.objects.get(username="student-created-by-admin")
        profile = AccountProfile.objects.get(user=created_user)
        student = Student.objects.get(account=profile)

        self.assertEqual(profile.role, AccountProfile.Role.STUDENT)
        self.assertEqual(student.status, Student.Status.ACTIVE)

        self.assertEqual(
            StudentSubscription.objects.filter(student=student, plan=self.plan).count(),
            1,
        )
        self.assertEqual(Enrollment.objects.filter(student=student).count(), 2)

    def test_student_cannot_create_accounts(self):
        self.client.force_login(self.student_user)
        response = self.client.post(
            reverse("students:student_create"),
            data={
                "full_name": "Blocked Student",
                "username": "blocked-student",
                "password": "StrongPass123!",
                "grade_level": Student.GradeLevel.FIRST_PRIMARY,
                "branch": Student.Branch.GENERAL,
                "student_status": Student.Status.ACTIVE,
            },
        )
        self.assertIn(response.status_code, (302, 403))
        self.assertFalse(User.objects.filter(username="blocked-student").exists())

    def test_teacher_cannot_create_student_accounts(self):
        self.client.force_login(self.teacher_user)
        response = self.client.post(
            reverse("students:student_create"),
            data={
                "full_name": "Blocked By Teacher",
                "username": "blocked-by-teacher",
                "password": "StrongPass123!",
                "grade_level": Student.GradeLevel.FIRST_PRIMARY,
                "branch": Student.Branch.GENERAL,
                "student_status": Student.Status.ACTIVE,
            },
        )
        self.assertIn(response.status_code, (302, 403))
        self.assertFalse(User.objects.filter(username="blocked-by-teacher").exists())

    def test_anonymous_user_cannot_create_student_accounts(self):
        response = self.client.post(
            reverse("students:student_create"),
            data={
                "full_name": "Blocked Anonymous",
                "username": "blocked-anonymous",
                "password": "StrongPass123!",
                "grade_level": Student.GradeLevel.FIRST_PRIMARY,
                "branch": Student.Branch.GENERAL,
                "student_status": Student.Status.ACTIVE,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(username="blocked-anonymous").exists())

    def test_student_creation_rolls_back_on_failure(self):
        self.client.force_login(self.admin_user)

        with patch("students.views.Student.objects.create", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    reverse("students:student_create"),
                    data={
                        "full_name": "Rollback Student",
                        "username": "rollback-student",
                        "password": "StrongPass123!",
                        "grade_level": Student.GradeLevel.FIRST_PRIMARY,
                        "branch": Student.Branch.GENERAL,
                        "student_status": Student.Status.ACTIVE,
                    },
                )

        self.assertFalse(User.objects.filter(username="rollback-student").exists())
        self.assertFalse(AccountProfile.objects.filter(user__username="rollback-student").exists())

    def test_student_view_permission_is_scoped_to_own_profile(self):
        self.student_user.user_permissions.add(Permission.objects.get(codename="view_student"))

        own_student = Student.objects.create(
            account=AccountProfile.objects.get(user=self.student_user),
            student_code="STU-SELF-001",
            grade_level=Student.GradeLevel.FIRST_PRIMARY,
            branch=Student.Branch.GENERAL,
            status=Student.Status.ACTIVE,
        )

        other_user = User.objects.create_user(username="student-scope-other", password=self.password)
        other_profile = AccountProfile.objects.create(
            user=other_user,
            role=AccountProfile.Role.STUDENT,
            status=AccountProfile.Status.ACTIVE,
        )
        other_student = Student.objects.create(
            account=other_profile,
            student_code="STU-OTHER-001",
            grade_level=Student.GradeLevel.FIRST_PRIMARY,
            branch=Student.Branch.GENERAL,
            status=Student.Status.ACTIVE,
        )

        self.client.force_login(self.student_user)

        list_response = self.client.get(reverse("students:student_list"))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, own_student.student_code)
        self.assertNotContains(list_response, other_student.student_code)

        detail_response = self.client.get(reverse("students:student_detail", args=[other_student.pk]))
        self.assertEqual(detail_response.status_code, 404)
