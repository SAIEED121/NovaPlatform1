from datetime import timedelta

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from accounts.models import AccountProfile
from courses.forms import CourseForm
from courses.models import Course, Enrollment, HomeworkSubmission, Lesson, Schedule
from students.models import Student
from teachers.models import Teacher


class CourseAcademicRuleTests(TestCase):
	def test_first_secondary_course_must_remain_general(self):
		form = CourseForm(
			data={
				"code": "CRS-SEC-001",
				"title": "First Secondary General Course",
				"grade_level": Course.GradeLevel.FIRST_SECONDARY,
				"branch": Course.Branch.SCIENCE,
				"price": "0",
				"status": Course.Status.DRAFT,
			}
		)
		self.assertFalse(form.is_valid())
		self.assertIn("branch", form.errors)


class CourseAccessScopeTests(TestCase):
	def setUp(self):
		self.password = "StrongPass123"
		self.student_user = User.objects.create_user(username="course-student", password=self.password)
		student_profile = AccountProfile.objects.create(
			user=self.student_user,
			role=AccountProfile.Role.STUDENT,
			status=AccountProfile.Status.ACTIVE,
		)
		self.student = Student.objects.create(
			account=student_profile,
			student_code="STU-COURSE-001",
			grade_level=Student.GradeLevel.FIRST_PRIMARY,
			branch=Student.Branch.GENERAL,
			status=Student.Status.ACTIVE,
		)

		teacher_user = User.objects.create_user(username="course-teacher", password=self.password)
		teacher_profile = AccountProfile.objects.create(
			user=teacher_user,
			role=AccountProfile.Role.TEACHER,
			status=AccountProfile.Status.ACTIVE,
		)
		teacher = Teacher.objects.create(
			account=teacher_profile,
			employee_code="TCH-COURSE-001",
			specialization="Science",
			status=Teacher.Status.ACTIVE,
		)

		other_teacher_user = User.objects.create_user(username="course-teacher-other", password=self.password)
		other_teacher_profile = AccountProfile.objects.create(
			user=other_teacher_user,
			role=AccountProfile.Role.TEACHER,
			status=AccountProfile.Status.ACTIVE,
		)
		other_teacher = Teacher.objects.create(
			account=other_teacher_profile,
			employee_code="TCH-COURSE-002",
			specialization="Math",
			status=Teacher.Status.ACTIVE,
		)

		self.owned_course = Course.objects.create(
			code="CRS-COURSE-001",
			title="Owned Course",
			teacher=teacher,
			grade_level=Course.GradeLevel.FIRST_PRIMARY,
			branch=Course.Branch.GENERAL,
			status=Course.Status.PUBLISHED,
		)
		self.other_course = Course.objects.create(
			code="CRS-COURSE-002",
			title="Other Course",
			teacher=other_teacher,
			grade_level=Course.GradeLevel.FIRST_PRIMARY,
			branch=Course.Branch.GENERAL,
			status=Course.Status.PUBLISHED,
		)
		self.owned_enrollment = Enrollment.objects.create(
			student=self.student,
			course=self.owned_course,
			status=Enrollment.Status.ACTIVE,
		)
		other_student_user = User.objects.create_user(username="course-student-other", password=self.password)
		other_student_profile = AccountProfile.objects.create(
			user=other_student_user,
			role=AccountProfile.Role.STUDENT,
			status=AccountProfile.Status.ACTIVE,
		)
		other_student = Student.objects.create(
			account=other_student_profile,
			student_code="STU-COURSE-002",
			grade_level=Student.GradeLevel.FIRST_PRIMARY,
			branch=Student.Branch.GENERAL,
			status=Student.Status.ACTIVE,
		)
		self.other_enrollment = Enrollment.objects.create(
			student=other_student,
			course=self.other_course,
			status=Enrollment.Status.ACTIVE,
		)

		self.owned_lesson = Lesson.objects.create(
			course=self.owned_course,
			title="Owned Lesson",
			order=1,
			duration_minutes=30,
		)
		self.other_lesson = Lesson.objects.create(
			course=self.other_course,
			title="Other Lesson",
			order=1,
			duration_minutes=30,
		)
		self.owned_schedule = Schedule.objects.create(
			course=self.owned_course,
			lesson=self.owned_lesson,
			title="Owned Schedule",
			starts_at=timezone.now(),
			ends_at=timezone.now() + timedelta(hours=1),
		)
		self.other_schedule = Schedule.objects.create(
			course=self.other_course,
			lesson=self.other_lesson,
			title="Other Schedule",
			starts_at=timezone.now() + timedelta(days=1),
			ends_at=timezone.now() + timedelta(days=1, hours=1),
		)
		self.owned_submission = HomeworkSubmission.objects.create(
			enrollment=self.owned_enrollment,
			lesson=self.owned_lesson,
			title="Owned Submission",
			description="Owned",
			attachment=SimpleUploadedFile(
				"owned.pdf",
				b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n",
				content_type="application/pdf",
			),
		)
		self.other_submission = HomeworkSubmission.objects.create(
			enrollment=self.other_enrollment,
			lesson=self.other_lesson,
			title="Other Submission",
			description="Other",
			attachment=SimpleUploadedFile(
				"other.pdf",
				b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n",
				content_type="application/pdf",
			),
		)

		self.student_user.user_permissions.add(Permission.objects.get(codename="view_course"))
		self.student_user.user_permissions.add(Permission.objects.get(codename="view_enrollment"))
		self.student_user.user_permissions.add(Permission.objects.get(codename="view_lesson"))
		self.student_user.user_permissions.add(Permission.objects.get(codename="view_schedule"))
		self.student_user.user_permissions.add(Permission.objects.get(codename="view_homeworksubmission"))

		self.teacher_user = teacher_user
		self.teacher_user.user_permissions.add(Permission.objects.get(codename="view_lesson"))
		self.teacher_user.user_permissions.add(Permission.objects.get(codename="change_lesson"))
		self.teacher_user.user_permissions.add(Permission.objects.get(codename="delete_lesson"))
		self.teacher_user.user_permissions.add(Permission.objects.get(codename="view_schedule"))
		self.teacher_user.user_permissions.add(Permission.objects.get(codename="change_schedule"))
		self.teacher_user.user_permissions.add(Permission.objects.get(codename="delete_schedule"))
		self.teacher_user.user_permissions.add(Permission.objects.get(codename="view_homeworksubmission"))
		self.teacher_user.user_permissions.add(Permission.objects.get(codename="change_homeworksubmission"))
		self.teacher_user.user_permissions.add(Permission.objects.get(codename="delete_homeworksubmission"))

	def test_student_course_and_enrollment_views_are_scoped(self):
		self.client.force_login(self.student_user)

		course_list_response = self.client.get(reverse("courses:course_list"))
		self.assertEqual(course_list_response.status_code, 200)
		self.assertContains(course_list_response, self.owned_course.code)
		self.assertNotContains(course_list_response, self.other_course.code)

		course_detail_response = self.client.get(reverse("courses:course_detail", args=[self.other_course.pk]))
		self.assertEqual(course_detail_response.status_code, 404)

		enrollment_list_response = self.client.get(reverse("courses:enrollment_list"))
		self.assertEqual(enrollment_list_response.status_code, 200)
		self.assertContains(enrollment_list_response, self.owned_course.code)
		self.assertNotContains(enrollment_list_response, self.other_course.code)

		enrollment_detail_response = self.client.get(reverse("courses:enrollment_detail", args=[self.other_enrollment.pk]))
		self.assertEqual(enrollment_detail_response.status_code, 404)

		lesson_list_response = self.client.get(reverse("courses:lesson_list"))
		self.assertEqual(lesson_list_response.status_code, 200)
		self.assertContains(lesson_list_response, self.owned_lesson.title)
		self.assertNotContains(lesson_list_response, self.other_lesson.title)

		lesson_detail_response = self.client.get(reverse("courses:lesson_detail", args=[self.other_lesson.pk]))
		self.assertEqual(lesson_detail_response.status_code, 404)

		schedule_list_response = self.client.get(reverse("courses:schedule_list"))
		self.assertEqual(schedule_list_response.status_code, 200)
		self.assertContains(schedule_list_response, self.owned_schedule.title)
		self.assertNotContains(schedule_list_response, self.other_schedule.title)

		schedule_detail_response = self.client.get(reverse("courses:schedule_detail", args=[self.other_schedule.pk]))
		self.assertEqual(schedule_detail_response.status_code, 404)

		homework_list_response = self.client.get(reverse("courses:homework_submission_list"))
		self.assertEqual(homework_list_response.status_code, 200)
		self.assertContains(homework_list_response, self.owned_submission.title)
		self.assertNotContains(homework_list_response, self.other_submission.title)

		homework_detail_response = self.client.get(
			reverse("courses:homework_submission_detail", args=[self.other_submission.pk])
		)
		self.assertEqual(homework_detail_response.status_code, 404)

	def test_teacher_cannot_mutate_other_teacher_course_content_or_homework(self):
		self.client.force_login(self.teacher_user)

		lesson_update_response = self.client.post(
			reverse("courses:lesson_update", args=[self.other_lesson.pk]),
			data={
				"course": self.other_course.pk,
				"title": "Hijacked Lesson",
				"description": "Attempt",
				"order": 1,
				"duration_minutes": 30,
				"video_url": "",
				"is_published": False,
				"due_date": "",
			},
		)
		self.assertEqual(lesson_update_response.status_code, 404)

		schedule_update_response = self.client.post(
			reverse("courses:schedule_update", args=[self.other_schedule.pk]),
			data={
				"course": self.other_course.pk,
				"lesson": self.other_lesson.pk,
				"title": "Hijacked Schedule",
				"starts_at": timezone.localtime(self.other_schedule.starts_at).strftime("%Y-%m-%dT%H:%M"),
				"ends_at": timezone.localtime(self.other_schedule.ends_at).strftime("%Y-%m-%dT%H:%M"),
				"meeting_url": "",
				"is_live": False,
				"notes": "",
			},
		)
		self.assertEqual(schedule_update_response.status_code, 404)

		homework_update_response = self.client.post(
			reverse("courses:homework_submission_update", args=[self.other_submission.pk]),
			data={
				"enrollment": self.other_enrollment.pk,
				"lesson": self.other_lesson.pk,
				"title": self.other_submission.title,
				"description": self.other_submission.description,
				"status": HomeworkSubmission.Status.REVIEWED,
				"grade": "10.00",
				"feedback": "Unauthorized",
			},
		)
		self.assertEqual(homework_update_response.status_code, 404)

	def test_second_secondary_course_requires_science_or_literary_branch(self):
		form = CourseForm(
			data={
				"code": "CRS-SEC-002",
				"title": "Second Secondary Course",
				"grade_level": Course.GradeLevel.SECOND_SECONDARY,
				"branch": Course.Branch.GENERAL,
				"price": "0",
				"status": Course.Status.DRAFT,
			}
		)
		self.assertFalse(form.is_valid())
		self.assertIn("branch", form.errors)

