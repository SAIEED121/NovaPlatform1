from django.contrib.auth.models import Group, Permission, User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from accounts.models import AccountProfile, CustomPermission, RoleCustomPermission
from courses.models import Course
from exams.models import Choice, Exam, Question, StudentExam
from payments.models import Payment
from students.models import Student
from teachers.models import Teacher


class DashboardViewsTests(TestCase):
	def setUp(self):
		cache.clear()
		self.password = "StrongPass123"
		self.admin_user = User.objects.create_user(username="dash-admin", password=self.password)
		AccountProfile.objects.create(
			user=self.admin_user,
			role=AccountProfile.Role.ADMIN,
			status=AccountProfile.Status.ACTIVE,
		)
		admin_group, _ = Group.objects.get_or_create(name="Administrator")
		self.admin_user.groups.add(admin_group)

		view_profile_perm = Permission.objects.get(codename="view_accountprofile")
		self.admin_user.user_permissions.add(view_profile_perm)

		portal_perm, _ = CustomPermission.objects.get_or_create(
			code="access.portal.administrator",
			defaults={"name": "Access Administrator Portal", "is_active": True},
		)
		RoleCustomPermission.objects.update_or_create(
			role=AccountProfile.Role.ADMIN,
			permission=portal_perm,
			defaults={"is_granted": True},
		)

		student_user = User.objects.create_user(username="dash-student", password=self.password)
		student_profile = AccountProfile.objects.create(
			user=student_user,
			role=AccountProfile.Role.STUDENT,
			status=AccountProfile.Status.ACTIVE,
		)
		self.student = Student.objects.create(
			account=student_profile,
			student_code="STU-DASH-001",
			grade_level=Student.GradeLevel.FIRST_PRIMARY,
			branch=Student.Branch.GENERAL,
			status=Student.Status.ACTIVE,
		)

		teacher_user = User.objects.create_user(username="dash-teacher", password=self.password)
		teacher_profile = AccountProfile.objects.create(
			user=teacher_user,
			role=AccountProfile.Role.TEACHER,
			status=AccountProfile.Status.ACTIVE,
		)
		self.teacher = Teacher.objects.create(
			account=teacher_profile,
			employee_code="TCH-DASH-001",
			specialization="Math",
			status=Teacher.Status.ACTIVE,
		)

		self.course = Course.objects.create(
			code="CRS-DASH-001",
			title="Dash Course",
			teacher=self.teacher,
			grade_level=Course.GradeLevel.FIRST_PRIMARY,
			branch=Course.Branch.GENERAL,
			status=Course.Status.PUBLISHED,
		)

		Payment.objects.create(
			student=self.student,
			requested_by=self.admin_user,
			amount="15000.00",
			currency="SYP",
			method=Payment.Method.CASH,
			status=Payment.Status.SUCCESSFUL,
			transaction_reference="DASH-PAY-001",
		)

		self.exam = Exam.objects.create(
			title="Dashboard Exam",
			description="Exam for dashboard report",
			teacher=self.teacher,
			course=self.course,
			status=Exam.Status.PUBLISHED,
			total_marks=10,
			passing_marks=5,
		)
		question = Question.objects.create(
			exam=self.exam,
			text="2 + 2 = ?",
			question_type=Question.QuestionType.MCQ,
			marks=2,
			display_order=1,
		)
		correct_choice = Choice.objects.create(
			question=question,
			text="4",
			is_correct=True,
			display_order=1,
		)
		student_exam = StudentExam.objects.create(
			exam=self.exam,
			student=self.student,
			status=StudentExam.Status.GRADED,
			score="8.00",
			percentage="80.00",
			result_status=StudentExam.ResultStatus.PASSED,
		)
		student_exam.answers.create(
			question=question,
			selected_choice=correct_choice,
			is_correct=True,
			score="2.00",
		)

	def test_homepage_loads(self):
		response = self.client.get(reverse("home"))
		self.assertEqual(response.status_code, 200)
		self.assertIn("total_students", response.context)

	def test_global_search_requires_authentication(self):
		response = self.client.get(reverse("dashboard:global_search"), {"q": "STU-DASH"})
		self.assertEqual(response.status_code, 302)

	def test_global_search_returns_matching_results(self):
		self.client.force_login(self.admin_user)
		response = self.client.get(reverse("dashboard:global_search"), {"q": "STU-DASH"})
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context["students_count"], 1)
		self.assertEqual(response.context["courses_count"], 0)

	def test_reports_dashboard_requires_admin_permissions(self):
		plain_user = User.objects.create_user(username="plain-user", password=self.password)
		self.client.force_login(plain_user)
		response = self.client.get(reverse("dashboard:reports_dashboard"))
		self.assertEqual(response.status_code, 302)

	def test_reports_dashboard_loads_for_authorized_admin(self):
		self.client.force_login(self.admin_user)
		response = self.client.get(reverse("dashboard:reports_dashboard"))
		self.assertEqual(response.status_code, 200)
		self.assertIn("statistics", response.context)
		self.assertIn("monthly_labels", response.context)

	def test_reports_dashboard_includes_exam_statistics_and_exam_rows(self):
		self.client.force_login(self.admin_user)
		response = self.client.get(reverse("dashboard:reports_dashboard"))
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context["statistics"]["total_exams"], 1)
		self.assertEqual(response.context["statistics"]["published_exams"], 1)
		self.assertEqual(response.context["statistics"]["graded_exam_attempts"], 1)
		self.assertEqual(response.context["statistics"]["pending_exam_grading"], 0)
		self.assertEqual(len(response.context["exam_reports"]), 1)
		self.assertContains(response, "Dashboard Exam")
