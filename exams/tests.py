from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from accounts.models import AccountProfile
from courses.models import Course
from exams.models import Choice, Exam, Question, StudentAnswer, StudentExam
from notifications.models import Notification
from courses.models import Enrollment
from students.models import Student
from teachers.models import Teacher


class ExamsModelTests(TestCase):
	def setUp(self):
		self.teacher_user = User.objects.create_user(username="exam-teacher", password="StrongPass123")
		teacher_profile = AccountProfile.objects.create(
			user=self.teacher_user,
			role=AccountProfile.Role.TEACHER,
			status=AccountProfile.Status.ACTIVE,
		)
		self.teacher = Teacher.objects.create(
			account=teacher_profile,
			employee_code="TCH-EX-001",
			specialization="Math",
			status=Teacher.Status.ACTIVE,
		)

		self.student_user = User.objects.create_user(username="exam-student", password="StrongPass123")
		student_profile = AccountProfile.objects.create(
			user=self.student_user,
			role=AccountProfile.Role.STUDENT,
			status=AccountProfile.Status.ACTIVE,
		)
		self.student = Student.objects.create(
			account=student_profile,
			student_code="STU-EX-001",
			grade_level=Student.GradeLevel.FIRST_PRIMARY,
			branch=Student.Branch.GENERAL,
			status=Student.Status.ACTIVE,
		)

		self.course = Course.objects.create(
			code="CRS-EX-001",
			title="Exam Course",
			teacher=self.teacher,
			grade_level=Course.GradeLevel.FIRST_PRIMARY,
			branch=Course.Branch.GENERAL,
			status=Course.Status.PUBLISHED,
		)

		self.exam = Exam.objects.create(
			title="Midterm",
			description="Midterm exam",
			teacher=self.teacher,
			course=self.course,
			status=Exam.Status.PUBLISHED,
			total_marks=100,
			passing_marks=50,
		)

	def test_create_exam_question_and_student_records(self):
		mcq_question = Question.objects.create(
			exam=self.exam,
			text="2 + 2 = ?",
			question_type=Question.QuestionType.MCQ,
			display_order=1,
		)
		true_false_question = Question.objects.create(
			exam=self.exam,
			text="The earth is flat.",
			question_type=Question.QuestionType.TRUE_FALSE,
			display_order=2,
		)
		essay_question = Question.objects.create(
			exam=self.exam,
			text="Explain gravity.",
			question_type=Question.QuestionType.ESSAY,
			display_order=3,
		)

		mcq_correct = Choice.objects.create(
			question=mcq_question,
			text="4",
			is_correct=True,
			display_order=1,
		)
		Choice.objects.create(
			question=mcq_question,
			text="5",
			is_correct=False,
			display_order=2,
		)
		Choice.objects.create(
			question=true_false_question,
			text="True",
			is_correct=False,
			display_order=1,
		)
		Choice.objects.create(
			question=true_false_question,
			text="False",
			is_correct=True,
			display_order=2,
		)

		student_exam = StudentExam.objects.create(
			exam=self.exam,
			student=self.student,
			attempt_no=1,
			status=StudentExam.Status.STARTED,
		)

		mcq_answer = StudentAnswer(
			student_exam=student_exam,
			question=mcq_question,
			selected_choice=mcq_correct,
		)
		mcq_answer.full_clean()
		mcq_answer.save()

		essay_answer = StudentAnswer(
			student_exam=student_exam,
			question=essay_question,
			answer_text="Gravity attracts masses toward each other.",
		)
		essay_answer.full_clean()
		essay_answer.save()

		self.assertEqual(self.exam.questions.count(), 3)
		self.assertEqual(student_exam.answers.count(), 2)

	def test_choice_not_allowed_for_essay_question(self):
		essay_question = Question.objects.create(
			exam=self.exam,
			text="Write an essay",
			question_type=Question.QuestionType.ESSAY,
			display_order=1,
		)
		choice = Choice(question=essay_question, text="Option A", display_order=1)
		with self.assertRaises(ValidationError):
			choice.full_clean()

	def test_student_answer_rejects_choice_from_other_question(self):
		question_one = Question.objects.create(
			exam=self.exam,
			text="Question one",
			question_type=Question.QuestionType.MCQ,
			display_order=1,
		)
		question_two = Question.objects.create(
			exam=self.exam,
			text="Question two",
			question_type=Question.QuestionType.MCQ,
			display_order=2,
		)
		choice_for_two = Choice.objects.create(
			question=question_two,
			text="Answer",
			is_correct=True,
			display_order=1,
		)
		student_exam = StudentExam.objects.create(exam=self.exam, student=self.student)

		answer = StudentAnswer(
			student_exam=student_exam,
			question=question_one,
			selected_choice=choice_for_two,
		)
		with self.assertRaises(ValidationError):
			answer.full_clean()

	def test_student_answer_unique_per_question(self):
		question = Question.objects.create(
			exam=self.exam,
			text="Unique question",
			question_type=Question.QuestionType.MCQ,
			display_order=1,
		)
		choice = Choice.objects.create(question=question, text="Correct", is_correct=True, display_order=1)
		student_exam = StudentExam.objects.create(exam=self.exam, student=self.student)

		StudentAnswer.objects.create(student_exam=student_exam, question=question, selected_choice=choice)
		with self.assertRaises(IntegrityError):
			StudentAnswer.objects.create(student_exam=student_exam, question=question, selected_choice=choice)


class ExamsIntegrationTests(TestCase):
	def setUp(self):
		self.password = "StrongPass123"

		self.owner_user = User.objects.create_user(username="exam-owner", password=self.password)
		owner_profile = AccountProfile.objects.create(
			user=self.owner_user,
			role=AccountProfile.Role.TEACHER,
			status=AccountProfile.Status.ACTIVE,
		)
		self.owner_teacher = Teacher.objects.create(
			account=owner_profile,
			employee_code="TCH-EX-OWN",
			specialization="Physics",
			status=Teacher.Status.ACTIVE,
		)

		self.other_user = User.objects.create_user(username="exam-other", password=self.password)
		other_profile = AccountProfile.objects.create(
			user=self.other_user,
			role=AccountProfile.Role.TEACHER,
			status=AccountProfile.Status.ACTIVE,
		)
		self.other_teacher = Teacher.objects.create(
			account=other_profile,
			employee_code="TCH-EX-OTH",
			specialization="Chemistry",
			status=Teacher.Status.ACTIVE,
		)

		self.owner_course = Course.objects.create(
			code="CRS-EX-OWN",
			title="Owner Course",
			teacher=self.owner_teacher,
			grade_level=Course.GradeLevel.FIRST_PRIMARY,
			branch=Course.Branch.GENERAL,
			status=Course.Status.PUBLISHED,
		)

		self.other_course = Course.objects.create(
			code="CRS-EX-OTH",
			title="Other Course",
			teacher=self.other_teacher,
			grade_level=Course.GradeLevel.FIRST_PRIMARY,
			branch=Course.Branch.GENERAL,
			status=Course.Status.PUBLISHED,
		)

		self.exam = Exam.objects.create(
			title="Owner Exam",
			description="Owner exam",
			teacher=self.owner_teacher,
			course=self.owner_course,
			status=Exam.Status.DRAFT,
			total_marks=100,
			passing_marks=50,
		)

		self.owner_permissions = Permission.objects.filter(
			codename__in=[
				"view_exam",
				"add_exam",
				"change_exam",
				"delete_exam",
				"publish_exam",
				"unpublish_exam",
				"add_question",
				"change_question",
				"delete_question",
				"add_choice",
				"change_choice",
				"delete_choice",
			]
		)
		self.owner_user.user_permissions.add(*self.owner_permissions)
		self.other_user.user_permissions.add(*self.owner_permissions)

	def test_owner_can_create_exam(self):
		self.client.force_login(self.owner_user)
		response = self.client.post(
			reverse("exams:exam_create"),
			data={
				"title": "New Owner Exam",
				"description": "Created by owner",
				"course": self.owner_course.pk,
				"status": Exam.Status.DRAFT,
				"duration_minutes": 60,
				"total_marks": 40,
				"passing_marks": 20,
				"allow_late_submission": False,
			},
		)
		self.assertEqual(response.status_code, 302)
		self.assertTrue(Exam.objects.filter(title="New Owner Exam", teacher=self.owner_teacher).exists())

	def test_non_owner_cannot_edit_or_delete_owner_exam(self):
		self.client.force_login(self.other_user)

		edit_response = self.client.post(
			reverse("exams:exam_update", args=[self.exam.pk]),
			data={
				"title": "Hacked",
				"description": self.exam.description,
				"course": self.other_course.pk,
				"status": Exam.Status.DRAFT,
				"duration_minutes": 60,
				"total_marks": 100,
				"passing_marks": 50,
				"allow_late_submission": False,
			},
		)
		self.assertEqual(edit_response.status_code, 404)

		delete_response = self.client.post(reverse("exams:exam_delete", args=[self.exam.pk]))
		self.assertEqual(delete_response.status_code, 404)

	def test_owner_can_add_question_and_choice(self):
		self.client.force_login(self.owner_user)

		question_response = self.client.post(
			reverse("exams:question_create", args=[self.exam.pk]),
			data={
				"text": "What is 3 + 4?",
				"question_type": Question.QuestionType.MCQ,
				"marks": 5,
				"display_order": 1,
			},
		)
		self.assertEqual(question_response.status_code, 302)
		question = Question.objects.get(exam=self.exam, display_order=1)

		choice_response = self.client.post(
			reverse("exams:choice_create", args=[self.exam.pk, question.pk]),
			data={
				"text": "7",
				"is_correct": True,
				"display_order": 1,
			},
		)
		self.assertEqual(choice_response.status_code, 302)
		self.assertTrue(Choice.objects.filter(question=question, text="7", is_correct=True).exists())

	def test_non_owner_cannot_add_question_or_publish_owner_exam(self):
		self.client.force_login(self.other_user)

		question_response = self.client.post(
			reverse("exams:question_create", args=[self.exam.pk]),
			data={
				"text": "Unauthorized question",
				"question_type": Question.QuestionType.MCQ,
				"marks": 2,
				"display_order": 1,
			},
		)
		self.assertEqual(question_response.status_code, 404)

		publish_response = self.client.post(reverse("exams:exam_publish_toggle", args=[self.exam.pk]))
		self.assertEqual(publish_response.status_code, 404)
		self.exam.refresh_from_db()
		self.assertEqual(self.exam.status, Exam.Status.DRAFT)

	def test_exam_list_is_scoped_to_owner(self):
		other_exam = Exam.objects.create(
			title="Other Teacher Exam",
			description="",
			teacher=self.other_teacher,
			course=self.other_course,
			status=Exam.Status.DRAFT,
			total_marks=50,
			passing_marks=25,
		)

		self.client.force_login(self.owner_user)
		response = self.client.get(reverse("exams:exam_list"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, self.exam.title)
		self.assertNotContains(response, other_exam.title)


class StudentExamsTests(TestCase):
	def setUp(self):
		self.password = "StrongPass123"

		self.student_user = User.objects.create_user(username="student-exam-user", password=self.password)
		student_profile = AccountProfile.objects.create(
			user=self.student_user,
			role=AccountProfile.Role.STUDENT,
			status=AccountProfile.Status.ACTIVE,
		)
		self.student = Student.objects.create(
			account=student_profile,
			student_code="STU-EX-STUDENT",
			grade_level=Student.GradeLevel.FIRST_PRIMARY,
			branch=Student.Branch.GENERAL,
			status=Student.Status.ACTIVE,
		)

		self.teacher_user = User.objects.create_user(username="student-exam-teacher", password=self.password)
		teacher_profile = AccountProfile.objects.create(
			user=self.teacher_user,
			role=AccountProfile.Role.TEACHER,
			status=AccountProfile.Status.ACTIVE,
		)
		self.teacher = Teacher.objects.create(
			account=teacher_profile,
			employee_code="TCH-STUDENT-EX",
			specialization="Physics",
			status=Teacher.Status.ACTIVE,
		)

		self.course = Course.objects.create(
			code="CRS-STUDENT-EX",
			title="Student Exam Course",
			teacher=self.teacher,
			grade_level=Course.GradeLevel.FIRST_PRIMARY,
			branch=Course.Branch.GENERAL,
			status=Course.Status.PUBLISHED,
		)

		self.published_exam = Exam.objects.create(
			title="Published Exam",
			description="Visible to students",
			teacher=self.teacher,
			course=self.course,
			status=Exam.Status.PUBLISHED,
			start_at=timezone.now() - timedelta(hours=1),
			end_at=timezone.now() + timedelta(hours=1),
			total_marks=20,
			passing_marks=2,
		)
		self.draft_exam = Exam.objects.create(
			title="Draft Exam",
			description="Hidden from students",
			teacher=self.teacher,
			course=self.course,
			status=Exam.Status.DRAFT,
			total_marks=20,
			passing_marks=10,
		)

		self.mcq_question = Question.objects.create(
			exam=self.published_exam,
			text="2 + 2 = ?",
			question_type=Question.QuestionType.MCQ,
			display_order=1,
		)
		self.essay_question = Question.objects.create(
			exam=self.published_exam,
			text="Explain gravity.",
			question_type=Question.QuestionType.ESSAY,
			marks=3,
			display_order=2,
		)
		self.true_false_question = Question.objects.create(
			exam=self.published_exam,
			text="The moon is made of cheese.",
			question_type=Question.QuestionType.TRUE_FALSE,
			display_order=3,
		)
		self.correct_choice = Choice.objects.create(
			question=self.mcq_question,
			text="4",
			is_correct=True,
			display_order=1,
		)
		Choice.objects.create(
			question=self.mcq_question,
			text="5",
			is_correct=False,
			display_order=2,
		)
		Choice.objects.create(
			question=self.true_false_question,
			text="True",
			is_correct=False,
			display_order=1,
		)
		self.tf_correct_choice = Choice.objects.create(
			question=self.true_false_question,
			text="False",
			is_correct=True,
			display_order=2,
		)

		self.student_permissions = Permission.objects.filter(
			codename__in=["view_exam", "add_studentexam", "view_studentexam"]
		)
		Enrollment.objects.create(student=self.student, course=self.course, status=Enrollment.Status.ACTIVE)

	def test_student_sees_only_published_exams(self):
		self.student_user.user_permissions.add(*self.student_permissions)
		self.client.force_login(self.student_user)

		response = self.client.get(reverse("exams:student_exam_list"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, self.published_exam.title)
		self.assertNotContains(response, self.draft_exam.title)

	def test_non_student_cannot_access_student_exam_views(self):
		self.teacher_user.user_permissions.add(*self.student_permissions)
		self.client.force_login(self.teacher_user)

		response = self.client.get(reverse("exams:student_exam_list"))
		self.assertEqual(response.status_code, 403)

	def test_student_can_open_exam_and_submit_once(self):
		self.student_user.user_permissions.add(*self.student_permissions)
		self.client.force_login(self.student_user)

		response = self.client.get(reverse("exams:student_exam_detail", args=[self.published_exam.pk]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, self.mcq_question.text)
		self.assertContains(response, self.essay_question.text)
		self.assertContains(response, self.true_false_question.text)

		submit_response = self.client.post(
			reverse("exams:student_exam_detail", args=[self.published_exam.pk]),
			data={
				f"question_{self.mcq_question.pk}": str(self.correct_choice.pk),
				f"question_{self.essay_question.pk}": "Gravity pulls objects together.",
				f"question_{self.true_false_question.pk}": str(self.tf_correct_choice.pk),
			},
		)
		self.assertEqual(submit_response.status_code, 302)
		student_exam = StudentExam.objects.get(exam=self.published_exam, student=self.student)
		self.assertEqual(student_exam.status, StudentExam.Status.SUBMITTED)
		self.assertEqual(student_exam.answers.count(), 3)
		self.assertEqual(student_exam.result_status, StudentExam.ResultStatus.PENDING)
		self.assertEqual(student_exam.score, Decimal("2.00"))
		self.assertEqual(student_exam.percentage, Decimal("10.00"))

		objective_answers = student_exam.answers.exclude(question__question_type=Question.QuestionType.ESSAY)
		self.assertTrue(all(answer.is_correct for answer in objective_answers))
		self.assertTrue(all(answer.score == Decimal("1.00") for answer in objective_answers))
		essay_answer = student_exam.answers.get(question=self.essay_question)
		self.assertIsNone(essay_answer.score)

		repeat_response = self.client.post(
			reverse("exams:student_exam_detail", args=[self.published_exam.pk]),
			data={
				f"question_{self.mcq_question.pk}": str(self.correct_choice.pk),
				f"question_{self.essay_question.pk}": "Gravity pulls objects together.",
				f"question_{self.true_false_question.pk}": str(self.tf_correct_choice.pk),
			},
		)
		self.assertEqual(repeat_response.status_code, 403)

	def test_student_can_view_result_after_submission(self):
		self.student_user.user_permissions.add(*self.student_permissions)
		self.client.force_login(self.student_user)

		self.client.post(
			reverse("exams:student_exam_detail", args=[self.published_exam.pk]),
			data={
				f"question_{self.mcq_question.pk}": str(self.correct_choice.pk),
				f"question_{self.essay_question.pk}": "Gravity pulls objects together.",
				f"question_{self.true_false_question.pk}": str(self.tf_correct_choice.pk),
			},
		)

		response = self.client.get(reverse("exams:student_exam_result", args=[self.published_exam.pk]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Pending")

	def test_exam_submission_respects_time_window(self):
		self.student_user.user_permissions.add(*self.student_permissions)
		future_exam = Exam.objects.create(
			title="Future Exam",
			description="Not started yet",
			teacher=self.teacher,
			course=self.course,
			status=Exam.Status.PUBLISHED,
			start_at=timezone.now() + timedelta(hours=1),
			end_at=timezone.now() + timedelta(hours=2),
			total_marks=20,
			passing_marks=10,
		)
		future_question = Question.objects.create(
			exam=future_exam,
			text="Will it open?",
			question_type=Question.QuestionType.ESSAY,
			display_order=1,
		)
		self.client.force_login(self.student_user)

		response = self.client.post(
			reverse("exams:student_exam_detail", args=[future_exam.pk]),
			data={f"question_{future_question.pk}": "No."},
		)
		self.assertEqual(response.status_code, 403)

	def test_student_cannot_access_published_exam_for_unenrolled_course(self):
		other_course = Course.objects.create(
			code="CRS-STUDENT-OTHER",
			title="Other Student Exam Course",
			teacher=self.teacher,
			grade_level=Course.GradeLevel.FIRST_PRIMARY,
			branch=Course.Branch.GENERAL,
			status=Course.Status.PUBLISHED,
		)
		other_exam = Exam.objects.create(
			title="Other Published Exam",
			description="Not enrolled",
			teacher=self.teacher,
			course=other_course,
			status=Exam.Status.PUBLISHED,
			start_at=timezone.now() - timedelta(hours=1),
			end_at=timezone.now() + timedelta(hours=1),
			total_marks=10,
			passing_marks=5,
		)
		Question.objects.create(
			exam=other_exam,
			text="Blocked question",
			question_type=Question.QuestionType.ESSAY,
			display_order=1,
		)

		self.student_user.user_permissions.add(*self.student_permissions)
		self.client.force_login(self.student_user)

		list_response = self.client.get(reverse("exams:student_exam_list"))
		self.assertEqual(list_response.status_code, 200)
		self.assertNotContains(list_response, other_exam.title)

		detail_response = self.client.get(reverse("exams:student_exam_detail", args=[other_exam.pk]))
		self.assertEqual(detail_response.status_code, 404)


class ExamResultsIntegrationTests(TestCase):
	def setUp(self):
		self.password = "StrongPass123"

		self.teacher_user = User.objects.create_user(username="result-teacher", password=self.password)
		teacher_profile = AccountProfile.objects.create(
			user=self.teacher_user,
			role=AccountProfile.Role.TEACHER,
			status=AccountProfile.Status.ACTIVE,
		)
		self.teacher = Teacher.objects.create(
			account=teacher_profile,
			employee_code="TCH-RESULT-01",
			specialization="Biology",
			status=Teacher.Status.ACTIVE,
		)

		self.student_user = User.objects.create_user(username="result-student", password=self.password)
		student_profile = AccountProfile.objects.create(
			user=self.student_user,
			role=AccountProfile.Role.STUDENT,
			status=AccountProfile.Status.ACTIVE,
		)
		self.student = Student.objects.create(
			account=student_profile,
			student_code="STU-RESULT-01",
			grade_level=Student.GradeLevel.FIRST_PRIMARY,
			branch=Student.Branch.GENERAL,
			status=Student.Status.ACTIVE,
		)

		self.course = Course.objects.create(
			code="CRS-RESULT-01",
			title="Results Course",
			teacher=self.teacher,
			grade_level=Course.GradeLevel.FIRST_PRIMARY,
			branch=Course.Branch.GENERAL,
			status=Course.Status.PUBLISHED,
		)
		Enrollment.objects.create(student=self.student, course=self.course, status=Enrollment.Status.ACTIVE)

		self.exam = Exam.objects.create(
			title="Result Exam",
			description="Exam for grading integration",
			teacher=self.teacher,
			course=self.course,
			status=Exam.Status.PUBLISHED,
			start_at=timezone.now() - timedelta(hours=1),
			end_at=timezone.now() + timedelta(hours=1),
			total_marks=10,
			passing_marks=4,
		)

		self.mcq_question = Question.objects.create(
			exam=self.exam,
			text="2+2?",
			question_type=Question.QuestionType.MCQ,
			marks=2,
			display_order=1,
		)
		self.essay_question = Question.objects.create(
			exam=self.exam,
			text="Describe photosynthesis",
			question_type=Question.QuestionType.ESSAY,
			marks=5,
			display_order=2,
		)
		self.mcq_correct_choice = Choice.objects.create(
			question=self.mcq_question,
			text="4",
			is_correct=True,
			display_order=1,
		)
		Choice.objects.create(
			question=self.mcq_question,
			text="3",
			is_correct=False,
			display_order=2,
		)

		self.student_permissions = Permission.objects.filter(
			codename__in=["view_exam", "add_studentexam", "view_studentexam"]
		)
		self.teacher_permissions = Permission.objects.filter(
			codename__in=["view_studentexam", "change_studentanswer", "view_exam"]
		)

	def _submit_student_exam(self):
		self.student_user.user_permissions.add(*self.student_permissions)
		self.client.force_login(self.student_user)
		response = self.client.post(
			reverse("exams:student_exam_detail", args=[self.exam.pk]),
			data={
				f"question_{self.mcq_question.pk}": str(self.mcq_correct_choice.pk),
				f"question_{self.essay_question.pk}": "Photosynthesis is how plants make food.",
			},
		)
		self.assertEqual(response.status_code, 302)
		return StudentExam.objects.get(exam=self.exam, student=self.student)

	def test_teacher_can_view_all_results(self):
		student_exam = self._submit_student_exam()
		self.teacher_user.user_permissions.add(*self.teacher_permissions)
		self.client.force_login(self.teacher_user)

		response = self.client.get(reverse("exams:result_list"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, self.exam.title)
		self.assertContains(response, self.student_user.username)
		self.assertContains(response, student_exam.get_result_status_display())

	def test_teacher_can_manually_grade_essay_and_finalize_result(self):
		student_exam = self._submit_student_exam()
		self.teacher_user.user_permissions.add(*self.teacher_permissions)
		self.client.force_login(self.teacher_user)

		response = self.client.post(
			reverse("exams:result_grade", args=[student_exam.pk]),
			data={
				f"essay_answer_{student_exam.answers.get(question=self.essay_question).pk}": "5.00",
				"grader_notes": "Excellent answer.",
			},
		)
		self.assertEqual(response.status_code, 302)

		student_exam.refresh_from_db()
		self.assertEqual(student_exam.status, StudentExam.Status.GRADED)
		self.assertEqual(student_exam.result_status, StudentExam.ResultStatus.PASSED)
		self.assertEqual(student_exam.score, Decimal("7.00"))
		self.assertEqual(student_exam.percentage, Decimal("70.00"))

	def test_student_cannot_access_teacher_results_list(self):
		self.student_user.user_permissions.add(*self.student_permissions)
		self.client.force_login(self.student_user)
		response = self.client.get(reverse("exams:result_list"))
		self.assertEqual(response.status_code, 403)


class ExamsPartFiveIntegrationTests(TestCase):
	def setUp(self):
		self.password = "StrongPass123"

		self.admin_user = User.objects.create_user(username="part5-admin", password=self.password)
		AccountProfile.objects.create(
			user=self.admin_user,
			role=AccountProfile.Role.ADMIN,
			status=AccountProfile.Status.ACTIVE,
		)

		self.teacher_user = User.objects.create_user(username="part5-teacher", password=self.password)
		teacher_profile = AccountProfile.objects.create(
			user=self.teacher_user,
			role=AccountProfile.Role.TEACHER,
			status=AccountProfile.Status.ACTIVE,
		)
		self.teacher = Teacher.objects.create(
			account=teacher_profile,
			employee_code="TCH-P5-001",
			specialization="Math",
			status=Teacher.Status.ACTIVE,
		)

		self.student_user = User.objects.create_user(username="part5-student", password=self.password)
		student_profile = AccountProfile.objects.create(
			user=self.student_user,
			role=AccountProfile.Role.STUDENT,
			status=AccountProfile.Status.ACTIVE,
		)
		self.student = Student.objects.create(
			account=student_profile,
			student_code="STU-P5-001",
			grade_level=Student.GradeLevel.FIRST_PRIMARY,
			branch=Student.Branch.GENERAL,
			status=Student.Status.ACTIVE,
		)

		self.course = Course.objects.create(
			code="CRS-P5-001",
			title="Part 5 Course",
			teacher=self.teacher,
			grade_level=Course.GradeLevel.FIRST_PRIMARY,
			branch=Course.Branch.GENERAL,
			status=Course.Status.PUBLISHED,
		)

		Enrollment.objects.create(student=self.student, course=self.course, status=Enrollment.Status.ACTIVE)

		self.teacher_permissions = Permission.objects.filter(
			codename__in=[
				"view_exam",
				"add_exam",
				"change_exam",
				"publish_exam",
				"view_studentexam",
				"change_studentanswer",
			]
		)
		self.student_permissions = Permission.objects.filter(
			codename__in=["view_exam", "add_studentexam", "view_studentexam"]
		)

	def test_exam_create_generates_new_exam_notifications(self):
		self.teacher_user.user_permissions.add(*self.teacher_permissions)
		self.client.force_login(self.teacher_user)

		response = self.client.post(
			reverse("exams:exam_create"),
			data={
				"title": "Part 5 New Exam",
				"description": "Created for notifications",
				"course": self.course.pk,
				"status": Exam.Status.DRAFT,
				"duration_minutes": 60,
				"total_marks": 20,
				"passing_marks": 10,
				"allow_late_submission": False,
			},
		)
		self.assertEqual(response.status_code, 302)
		self.assertTrue(
			Notification.objects.filter(
				recipient_type=Notification.RecipientType.TEACHER,
				teacher=self.teacher,
				title="New exam created",
			).exists()
		)

	def test_publish_exam_notifies_enrolled_students(self):
		exam = Exam.objects.create(
			title="Publish Me",
			description="",
			teacher=self.teacher,
			course=self.course,
			status=Exam.Status.DRAFT,
			total_marks=10,
			passing_marks=5,
		)
		self.teacher_user.user_permissions.add(*self.teacher_permissions)
		self.client.force_login(self.teacher_user)

		response = self.client.post(reverse("exams:exam_publish_toggle", args=[exam.pk]))
		self.assertEqual(response.status_code, 302)
		self.assertTrue(
			Notification.objects.filter(
				recipient_type=Notification.RecipientType.STUDENT,
				student=self.student,
				title="Exam published",
			).exists()
		)

	def test_exam_graded_notification_and_teacher_report_view(self):
		exam = Exam.objects.create(
			title="Auto Grade Exam",
			description="",
			teacher=self.teacher,
			course=self.course,
			status=Exam.Status.PUBLISHED,
			start_at=timezone.now() - timedelta(hours=1),
			end_at=timezone.now() + timedelta(hours=1),
			total_marks=5,
			passing_marks=2,
		)
		question = Question.objects.create(
			exam=exam,
			text="2 + 2 = ?",
			question_type=Question.QuestionType.MCQ,
			marks=5,
			display_order=1,
		)
		correct_choice = Choice.objects.create(
			question=question,
			text="4",
			is_correct=True,
			display_order=1,
		)

		self.student_user.user_permissions.add(*self.student_permissions)
		self.client.force_login(self.student_user)
		submit_response = self.client.post(
			reverse("exams:student_exam_detail", args=[exam.pk]),
			data={f"question_{question.pk}": str(correct_choice.pk)},
		)
		self.assertEqual(submit_response.status_code, 302)
		self.assertTrue(
			Notification.objects.filter(
				recipient_type=Notification.RecipientType.STUDENT,
				student=self.student,
				title="Exam graded",
			).exists()
		)

		self.teacher_user.user_permissions.add(*self.teacher_permissions)
		self.client.force_login(self.teacher_user)
		reports_response = self.client.get(reverse("exams:report_list"))
		self.assertEqual(reports_response.status_code, 200)
		self.assertContains(reports_response, "Auto Grade Exam")
