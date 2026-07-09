from django.contrib.auth.models import Permission, User
from datetime import timedelta
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccountProfile
from payments.forms import PaymentForm, PaymentRequestForm
from payments.models import Invoice, Payment, Receipt
from students.models import Student
from subscriptions.models import StudentSubscription, SubscriptionPlan


class PaymentDatabaseTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(username="payment-user", password="StrongPass123")
		profile = AccountProfile.objects.create(
			user=self.user,
			role=AccountProfile.Role.STUDENT,
			status=AccountProfile.Status.ACTIVE,
		)
		self.student = Student.objects.create(
			account=profile,
			student_code="STU-PAY-001",
			grade_level=Student.GradeLevel.FIRST_PRIMARY,
			branch=Student.Branch.GENERAL,
			status=Student.Status.ACTIVE,
		)

	def test_pending_payment_creates_invoice_without_receipt(self):
		payment = Payment.objects.create(
			student=self.student,
			requested_by=self.user,
			amount="10000.00",
			currency="SYP",
			method=Payment.Method.CASH,
			status=Payment.Status.PENDING,
			transaction_reference="PAY-DB-001",
		)

		self.assertTrue(Invoice.objects.filter(payment=payment).exists())
		self.assertFalse(Receipt.objects.filter(payment=payment).exists())

	def test_successful_payment_creates_invoice_and_receipt(self):
		payment = Payment.objects.create(
			student=self.student,
			requested_by=self.user,
			amount="12000.00",
			currency="SYP",
			method=Payment.Method.BANK_TRANSFER,
			status=Payment.Status.SUCCESSFUL,
			transaction_reference="PAY-DB-002",
		)

		self.assertTrue(Invoice.objects.filter(payment=payment, status=Invoice.Status.PAID).exists())
		self.assertTrue(Receipt.objects.filter(payment=payment).exists())
		payment.refresh_from_db()
		self.assertIsNotNone(payment.paid_at)

	def test_approve_sets_success_and_approval_metadata(self):
		payment = Payment.objects.create(
			student=self.student,
			requested_by=self.user,
			amount="13000.00",
			currency="SYP",
			method=Payment.Method.CARD,
			status=Payment.Status.PENDING,
			transaction_reference="PAY-DB-003",
		)

		payment.approve(approved_by=self.user, note="Approved for test")
		payment.refresh_from_db()

		self.assertEqual(payment.status, Payment.Status.SUCCESSFUL)
		self.assertEqual(payment.approved_by, self.user)
		self.assertIsNotNone(payment.approved_at)
		self.assertIsNotNone(payment.paid_at)
		self.assertIn("Approved for test", payment.notes)


class PaymentViewAndFormTests(TestCase):
	def setUp(self):
		self.password = "StrongPass123"
		self.admin_user = User.objects.create_user(username="pay-admin", password=self.password)
		self.admin_user.is_staff = True
		self.admin_user.save(update_fields=["is_staff"])
		self.student_user = User.objects.create_user(username="pay-student", password=self.password)

		self.student_profile = AccountProfile.objects.create(
			user=self.student_user,
			role=AccountProfile.Role.STUDENT,
			status=AccountProfile.Status.ACTIVE,
		)
		self.student = Student.objects.create(
			account=self.student_profile,
			student_code="STU-PAY-TEST",
			grade_level=Student.GradeLevel.FIRST_PRIMARY,
			branch=Student.Branch.GENERAL,
			status=Student.Status.ACTIVE,
		)

		self.payment = Payment.objects.create(
			student=self.student,
			requested_by=self.admin_user,
			amount="9999.00",
			currency="SYP",
			method=Payment.Method.CASH,
			status=Payment.Status.PENDING,
			transaction_reference="PAY-VIEW-001",
		)
		self.plan = SubscriptionPlan.objects.create(
			name="Payment Plan",
			duration_days=30,
			price="15000.00",
			status=SubscriptionPlan.Status.ACTIVE,
		)
		self.subscription = StudentSubscription.objects.create(
			student=self.student,
			plan=self.plan,
			status=StudentSubscription.Status.ACTIVE,
			started_at=timezone.now(),
			ends_at=timezone.now() + timedelta(days=30),
		)

	def test_payment_form_requires_transaction_reference_for_non_cash(self):
		form = PaymentForm(
			data={
				"student": self.student.pk,
				"requested_by": self.admin_user.pk,
				"amount": "100.00",
				"currency": "SYP",
				"method": Payment.Method.CARD,
				"status": Payment.Status.PENDING,
				"transaction_reference": "",
			}
		)
		self.assertFalse(form.is_valid())
		self.assertIn("transaction_reference", form.errors)

	def test_payment_form_rejects_subscription_from_other_student(self):
		other_user = User.objects.create_user(username="pay-form-other", password=self.password)
		other_profile = AccountProfile.objects.create(
			user=other_user,
			role=AccountProfile.Role.STUDENT,
			status=AccountProfile.Status.ACTIVE,
		)
		other_student = Student.objects.create(
			account=other_profile,
			student_code="STU-PAY-FORM-OTHER",
			grade_level=Student.GradeLevel.FIRST_PRIMARY,
			branch=Student.Branch.GENERAL,
			status=Student.Status.ACTIVE,
		)
		other_subscription = StudentSubscription.objects.create(
			student=other_student,
			plan=self.plan,
			status=StudentSubscription.Status.ACTIVE,
			started_at=timezone.now(),
			ends_at=timezone.now() + timedelta(days=30),
		)

		form = PaymentForm(
			data={
				"student": self.student.pk,
				"requested_by": self.admin_user.pk,
				"approved_by": "",
				"subscription": other_subscription.pk,
				"amount": "100.00",
				"currency": "SYP",
				"method": Payment.Method.CASH,
				"status": Payment.Status.PENDING,
				"transaction_reference": "",
				"paid_at": "",
				"approved_at": "",
				"notes": "",
			}
		)
		self.assertFalse(form.is_valid())
		self.assertIn("subscription", form.errors)

	def test_payment_request_form_currency_validation(self):
		form = PaymentRequestForm(
			data={
				"amount": "100.00",
				"currency": "sy",
				"method": Payment.Method.CASH,
			}
		)
		self.assertFalse(form.is_valid())
		self.assertIn("currency", form.errors)

	def test_payment_list_requires_permission(self):
		self.client.force_login(self.admin_user)
		response = self.client.get(reverse("payments:payment_list"))
		self.assertIn(response.status_code, (302, 403))

	def test_payment_request_create_assigns_student_and_pending_status(self):
		self.client.force_login(self.student_user)
		response = self.client.post(
			reverse("payments:payment_request"),
			data={
				"subscription": self.subscription.pk,
				"amount": "250.00",
				"currency": "SYP",
				"method": Payment.Method.CASH,
				"transaction_reference": "",
				"notes": "request",
			},
		)
		self.assertEqual(response.status_code, 302)
		created = Payment.objects.filter(requested_by=self.student_user).latest("id")
		self.assertEqual(created.student, self.student)
		self.assertEqual(created.status, Payment.Status.PENDING)
		self.assertEqual(created.subscription, self.subscription)

	def test_payment_request_rejects_other_students_subscription(self):
		other_user = User.objects.create_user(username="pay-sub-other", password=self.password)
		other_profile = AccountProfile.objects.create(
			user=other_user,
			role=AccountProfile.Role.STUDENT,
			status=AccountProfile.Status.ACTIVE,
		)
		other_student = Student.objects.create(
			account=other_profile,
			student_code="STU-PAY-SUB-OTHER",
			grade_level=Student.GradeLevel.FIRST_PRIMARY,
			branch=Student.Branch.GENERAL,
			status=Student.Status.ACTIVE,
		)
		other_subscription = StudentSubscription.objects.create(
			student=other_student,
			plan=self.plan,
			status=StudentSubscription.Status.ACTIVE,
			started_at=timezone.now(),
			ends_at=timezone.now() + timedelta(days=30),
		)

		self.client.force_login(self.student_user)
		response = self.client.post(
			reverse("payments:payment_request"),
			data={
				"subscription": other_subscription.pk,
				"amount": "250.00",
				"currency": "SYP",
				"method": Payment.Method.CASH,
				"transaction_reference": "",
				"notes": "request",
			},
		)
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "subscription")
		self.assertFalse(Payment.objects.filter(requested_by=self.student_user, subscription=other_subscription).exists())

	def test_student_can_view_own_invoice_and_receipt(self):
		successful_payment = Payment.objects.create(
			student=self.student,
			requested_by=self.student_user,
			amount="1200.00",
			currency="SYP",
			method=Payment.Method.CARD,
			status=Payment.Status.SUCCESSFUL,
			transaction_reference="PAY-VIEW-OWN-001",
		)

		self.client.force_login(self.student_user)

		invoice_response = self.client.get(
			reverse("payments:invoice_detail", args=[successful_payment.invoice.pk])
		)
		receipt_response = self.client.get(
			reverse("payments:receipt_detail", args=[successful_payment.receipt.pk])
		)

		self.assertEqual(invoice_response.status_code, 200)
		self.assertEqual(receipt_response.status_code, 200)

	def test_student_cannot_view_other_students_invoice_or_receipt(self):
		other_user = User.objects.create_user(username="pay-other-student", password=self.password)
		other_profile = AccountProfile.objects.create(
			user=other_user,
			role=AccountProfile.Role.STUDENT,
			status=AccountProfile.Status.ACTIVE,
		)
		other_student = Student.objects.create(
			account=other_profile,
			student_code="STU-PAY-OTHER",
			grade_level=Student.GradeLevel.FIRST_PRIMARY,
			branch=Student.Branch.GENERAL,
			status=Student.Status.ACTIVE,
		)
		other_payment = Payment.objects.create(
			student=other_student,
			requested_by=other_user,
			amount="2100.00",
			currency="SYP",
			method=Payment.Method.BANK_TRANSFER,
			status=Payment.Status.SUCCESSFUL,
			transaction_reference="PAY-VIEW-OTHER-001",
		)

		self.client.force_login(self.student_user)

		invoice_response = self.client.get(
			reverse("payments:invoice_detail", args=[other_payment.invoice.pk])
		)
		receipt_response = self.client.get(
			reverse("payments:receipt_detail", args=[other_payment.receipt.pk])
		)

		self.assertEqual(invoice_response.status_code, 404)
		self.assertEqual(receipt_response.status_code, 404)

	def test_student_payment_views_are_scoped_to_own_records(self):
		self.student_user.user_permissions.add(Permission.objects.get(codename="view_payment"))

		other_user = User.objects.create_user(username="pay-list-other", password=self.password)
		other_profile = AccountProfile.objects.create(
			user=other_user,
			role=AccountProfile.Role.STUDENT,
			status=AccountProfile.Status.ACTIVE,
		)
		other_student = Student.objects.create(
			account=other_profile,
			student_code="STU-PAY-LIST-OTHER",
			grade_level=Student.GradeLevel.FIRST_PRIMARY,
			branch=Student.Branch.GENERAL,
			status=Student.Status.ACTIVE,
		)
		other_payment = Payment.objects.create(
			student=other_student,
			requested_by=other_user,
			amount="777.00",
			currency="SYP",
			method=Payment.Method.CASH,
			status=Payment.Status.PENDING,
			transaction_reference="PAY-LIST-OTHER-001",
		)

		self.client.force_login(self.student_user)

		list_response = self.client.get(reverse("payments:payment_list"))
		self.assertEqual(list_response.status_code, 200)
		self.assertContains(list_response, self.student.student_code)
		self.assertNotContains(list_response, other_student.student_code)

		detail_response = self.client.get(reverse("payments:payment_detail", args=[other_payment.pk]))
		self.assertEqual(detail_response.status_code, 404)

	def test_student_cannot_mutate_payments_even_with_change_permission(self):
		self.student_user.user_permissions.add(Permission.objects.get(codename="change_payment"))
		self.client.force_login(self.student_user)

		response = self.client.post(
			reverse("payments:payment_update", args=[self.payment.pk]),
			data={
				"student": self.student.pk,
				"requested_by": self.admin_user.pk,
				"approved_by": "",
				"subscription": self.subscription.pk,
				"amount": "9999.00",
				"currency": "SYP",
				"method": Payment.Method.CASH,
				"status": Payment.Status.SUCCESSFUL,
				"transaction_reference": "PAY-VIEW-001",
				"paid_at": "2026-01-01T10:00",
				"approved_at": "",
				"notes": "tamper",
			},
		)
		self.assertEqual(response.status_code, 403)

