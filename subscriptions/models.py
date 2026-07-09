from django.db import models
from django.utils import timezone


class SubscriptionPlan(models.Model):
	class Status(models.TextChoices):
		ACTIVE = "active", "Active"
		INACTIVE = "inactive", "Inactive"

	name = models.CharField(max_length=100, unique=True)
	description = models.TextField(blank=True)
	duration_days = models.PositiveIntegerField()
	price = models.DecimalField(max_digits=10, decimal_places=2)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["name"]
		indexes = [
			models.Index(fields=["status"]),
		]

	def __str__(self):
		return self.name


class PlanCourse(models.Model):
	plan = models.ForeignKey("subscriptions.SubscriptionPlan", on_delete=models.CASCADE, related_name="plan_courses")
	course = models.ForeignKey("courses.Course", on_delete=models.CASCADE, related_name="course_plans")
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		unique_together = ("plan", "course")
		indexes = [
			models.Index(fields=["plan", "course"]),
		]

	def __str__(self):
		return f"{self.plan.name} - {self.course.code}"


class StudentSubscriptionQuerySet(models.QuerySet):
	def auto_expire(self):
		now = timezone.now()
		return self.filter(
			ends_at__lte=now,
			status__in=[
				StudentSubscription.Status.PENDING,
				StudentSubscription.Status.TRIAL,
				StudentSubscription.Status.ACTIVE,
				StudentSubscription.Status.PAST_DUE,
			],
		).update(status=StudentSubscription.Status.EXPIRED)


class StudentSubscriptionManager(models.Manager):
	def get_queryset(self):
		return StudentSubscriptionQuerySet(self.model, using=self._db)

	def auto_expire(self):
		return self.get_queryset().auto_expire()


class StudentSubscription(models.Model):
	class Status(models.TextChoices):
		PENDING = "pending", "Pending"
		TRIAL = "trial", "Trial"
		ACTIVE = "active", "Active"
		PAST_DUE = "past_due", "Past Due"
		CANCELLED = "cancelled", "Cancelled"
		EXPIRED = "expired", "Expired"

	student = models.ForeignKey("students.Student", on_delete=models.CASCADE, related_name="subscriptions")
	plan = models.ForeignKey(
		"subscriptions.SubscriptionPlan",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="student_subscriptions",
	)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
	started_at = models.DateTimeField()
	ends_at = models.DateTimeField()
	auto_renew = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	objects = StudentSubscriptionManager()

	class Meta:
		ordering = ["-started_at"]
		indexes = [
			models.Index(fields=["status"]),
			models.Index(fields=["ends_at"]),
			models.Index(fields=["student", "status"]),
		]

	def __str__(self):
		return f"{self.student.student_code} - {self.status}"

	def apply_automatic_expiration(self):
		if not self.ends_at:
			return

		if self.ends_at <= timezone.now() and self.status in {
			self.Status.PENDING,
			self.Status.TRIAL,
			self.Status.ACTIVE,
			self.Status.PAST_DUE,
		}:
			self.status = self.Status.EXPIRED

	def save(self, *args, **kwargs):
		self.apply_automatic_expiration()
		super().save(*args, **kwargs)
