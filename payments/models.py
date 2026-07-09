from django.db import models
from django.utils import timezone


class Payment(models.Model):
	class Method(models.TextChoices):
		CASH = "cash", "Cash"
		CARD = "card", "Card"
		BANK_TRANSFER = "bank_transfer", "Bank Transfer"
		MOBILE_WALLET = "mobile_wallet", "Mobile Wallet"
		CRYPTO = "crypto", "Crypto"

	class Status(models.TextChoices):
		PENDING = "pending", "Pending"
		SUCCESSFUL = "successful", "Successful"
		FAILED = "failed", "Failed"
		REFUNDED = "refunded", "Refunded"

	student = models.ForeignKey("students.Student", on_delete=models.CASCADE, related_name="payments")
	requested_by = models.ForeignKey(
		"auth.User",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="requested_payments",
	)
	approved_by = models.ForeignKey(
		"auth.User",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="approved_payments",
	)
	subscription = models.ForeignKey(
		"subscriptions.StudentSubscription",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="payments",
	)
	amount = models.DecimalField(max_digits=10, decimal_places=2)
	currency = models.CharField(max_length=3, default="SYP")
	method = models.CharField(max_length=20, choices=Method.choices)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
	transaction_reference = models.CharField(max_length=120, unique=True, null=True, blank=True)
	paid_at = models.DateTimeField(null=True, blank=True)
	approved_at = models.DateTimeField(null=True, blank=True)
	notes = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-created_at"]
		indexes = [
			models.Index(fields=["status"]),
			models.Index(fields=["method"]),
			models.Index(fields=["transaction_reference"]),
		]

	def __str__(self):
		return f"Payment {self.id} - {self.student.student_code} - {self.status}"

	def approve(self, approved_by=None, note=""):
		self.status = self.Status.SUCCESSFUL
		self.approved_by = approved_by
		self.approved_at = timezone.now()
		if not self.paid_at:
			self.paid_at = timezone.now()
		if note:
			self.notes = f"{self.notes}\n{note}".strip()
		self.save()

	def reject(self, approved_by=None, note=""):
		self.status = self.Status.FAILED
		self.approved_by = approved_by
		self.approved_at = timezone.now()
		if note:
			self.notes = f"{self.notes}\n{note}".strip()
		self.save()

	def save(self, *args, **kwargs):
		creating = self.pk is None
		if self.status == self.Status.SUCCESSFUL and not self.paid_at:
			self.paid_at = timezone.now()
		super().save(*args, **kwargs)

		# Every payment request gets an invoice; successful ones also get a receipt.
		Invoice.objects.get_or_create(
			payment=self,
			defaults={
				"invoice_number": f"INV-{timezone.now():%Y%m%d}-{self.id:06d}",
				"total_amount": self.amount,
				"currency": self.currency,
				"status": Invoice.Status.PAID if self.status == self.Status.SUCCESSFUL else Invoice.Status.ISSUED,
			},
		)

		if self.status == self.Status.SUCCESSFUL:
			Receipt.objects.get_or_create(
				payment=self,
				defaults={
					"receipt_number": f"RCT-{timezone.now():%Y%m%d}-{self.id:06d}",
					"amount": self.amount,
					"currency": self.currency,
					"method": self.method,
					"transaction_reference": self.transaction_reference,
				},
			)

		if not creating and hasattr(self, "invoice"):
			if self.status == self.Status.SUCCESSFUL:
				if self.invoice.status != Invoice.Status.PAID:
					self.invoice.status = Invoice.Status.PAID
					self.invoice.save(update_fields=["status", "updated_at"])
			elif self.status == self.Status.FAILED:
				if self.invoice.status != Invoice.Status.CANCELLED:
					self.invoice.status = Invoice.Status.CANCELLED
					self.invoice.save(update_fields=["status", "updated_at"])


class Invoice(models.Model):
	class Status(models.TextChoices):
		ISSUED = "issued", "Issued"
		PAID = "paid", "Paid"
		CANCELLED = "cancelled", "Cancelled"

	payment = models.OneToOneField("payments.Payment", on_delete=models.CASCADE, related_name="invoice")
	invoice_number = models.CharField(max_length=40, unique=True)
	total_amount = models.DecimalField(max_digits=10, decimal_places=2)
	currency = models.CharField(max_length=3, default="SYP")
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.ISSUED)
	issued_at = models.DateTimeField(default=timezone.now)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-issued_at"]
		indexes = [
			models.Index(fields=["invoice_number"]),
			models.Index(fields=["status"]),
		]

	def __str__(self):
		return self.invoice_number


class Receipt(models.Model):
	payment = models.OneToOneField("payments.Payment", on_delete=models.CASCADE, related_name="receipt")
	receipt_number = models.CharField(max_length=40, unique=True)
	amount = models.DecimalField(max_digits=10, decimal_places=2)
	currency = models.CharField(max_length=3, default="SYP")
	method = models.CharField(max_length=20, choices=Payment.Method.choices)
	transaction_reference = models.CharField(max_length=120, null=True, blank=True)
	issued_at = models.DateTimeField(default=timezone.now)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-issued_at"]
		indexes = [
			models.Index(fields=["receipt_number"]),
		]

	def __str__(self):
		return self.receipt_number
