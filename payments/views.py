from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from .forms import PaymentApprovalForm, PaymentForm, PaymentRequestForm
from .models import Invoice, Payment, Receipt
from students.models import Student


class PaymentBaseQuerySetMixin:
	def _all_payments_queryset(self):
		return Payment.objects.select_related(
			"student",
			"student__account",
			"student__account__user",
			"invoice",
			"receipt",
			"subscription",
			"subscription__student",
			"requested_by",
			"approved_by",
		)

	def _student_profile(self, user):
		return Student.objects.select_related("account", "account__user").filter(account__user=user).first()

	def _can_access_all_payments(self, user):
		return bool(user and user.is_authenticated and (user.is_superuser or user.is_staff))

	def _enforce_payment_management_access(self):
		if self._can_access_all_payments(self.request.user):
			return
		raise PermissionDenied("Only staff can manage payments.")

	def _visible_payments_queryset(self, user):
		queryset = self._all_payments_queryset()
		if self._can_access_all_payments(user):
			return queryset

		student_profile = self._student_profile(user)
		if not student_profile:
			return Payment.objects.none()
		return queryset.filter(student=student_profile)


class PaymentListView(PaymentBaseQuerySetMixin, LoginRequiredMixin, PermissionRequiredMixin, ListView):
	model = Payment
	permission_required = "payments.view_payment"
	template_name = "payments/payment_list.html"
	context_object_name = "payments"
	paginate_by = 25

	def get_queryset(self):
		return self._visible_payments_queryset(self.request.user)


class PaymentDetailView(PaymentBaseQuerySetMixin, LoginRequiredMixin, PermissionRequiredMixin, DetailView):
	model = Payment
	permission_required = "payments.view_payment"
	template_name = "payments/payment_detail.html"
	context_object_name = "payment"

	def get_queryset(self):
		return self._visible_payments_queryset(self.request.user)


class PaymentCreateView(PaymentBaseQuerySetMixin, LoginRequiredMixin, PermissionRequiredMixin, CreateView):
	model = Payment
	form_class = PaymentForm
	permission_required = "payments.add_payment"
	template_name = "payments/payment_form.html"
	success_url = reverse_lazy("payments:payment_list")

	def dispatch(self, request, *args, **kwargs):
		self._enforce_payment_management_access()
		return super().dispatch(request, *args, **kwargs)


class PaymentUpdateView(PaymentBaseQuerySetMixin, LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
	model = Payment
	form_class = PaymentForm
	permission_required = "payments.change_payment"
	template_name = "payments/payment_form.html"
	success_url = reverse_lazy("payments:payment_list")

	def dispatch(self, request, *args, **kwargs):
		self._enforce_payment_management_access()
		return super().dispatch(request, *args, **kwargs)

	def get_queryset(self):
		return self._all_payments_queryset()


class PaymentDeleteView(PaymentBaseQuerySetMixin, LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
	model = Payment
	permission_required = "payments.delete_payment"
	template_name = "payments/payment_confirm_delete.html"
	success_url = reverse_lazy("payments:payment_list")

	def dispatch(self, request, *args, **kwargs):
		self._enforce_payment_management_access()
		return super().dispatch(request, *args, **kwargs)

	def get_queryset(self):
		return self._all_payments_queryset()


class PaymentRequestCreateView(PaymentBaseQuerySetMixin, LoginRequiredMixin, CreateView):
	model = Payment
	form_class = PaymentRequestForm
	template_name = "payments/payment_request_form.html"
	success_url = reverse_lazy("payments:payment_history")

	def get_form_kwargs(self):
		kwargs = super().get_form_kwargs()
		kwargs["user"] = self.request.user
		return kwargs

	def form_valid(self, form):
		student_profile = self._student_profile(self.request.user)
		if not student_profile:
			messages.error(self.request, "Only student accounts can submit payment requests.")
			return redirect("home")

		form.instance.student = student_profile
		form.instance.requested_by = self.request.user
		form.instance.status = Payment.Status.PENDING
		messages.success(self.request, "Payment request submitted successfully and is waiting for approval.")
		return super().form_valid(form)


class PaymentApproveView(PaymentBaseQuerySetMixin, LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
	model = Payment
	form_class = PaymentApprovalForm
	permission_required = "payments.change_payment"
	template_name = "payments/payment_approval_form.html"
	success_url = reverse_lazy("payments:payment_list")

	def dispatch(self, request, *args, **kwargs):
		self._enforce_payment_management_access()
		return super().dispatch(request, *args, **kwargs)

	def get_queryset(self):
		return self._all_payments_queryset().filter(status=Payment.Status.PENDING)

	def form_valid(self, form):
		form.instance.approved_by = self.request.user
		messages.success(self.request, "Payment approval decision recorded successfully.")
		return super().form_valid(form)


class PaymentHistoryView(PaymentBaseQuerySetMixin, LoginRequiredMixin, ListView):
	model = Payment
	template_name = "payments/payment_history.html"
	context_object_name = "payments"
	paginate_by = 25

	def get_queryset(self):
		return self._visible_payments_queryset(self.request.user)


class InvoiceDetailView(PaymentBaseQuerySetMixin, LoginRequiredMixin, DetailView):
	model = Invoice
	template_name = "payments/invoice_detail.html"
	context_object_name = "invoice"

	def get_queryset(self):
		queryset = Invoice.objects.select_related(
			"payment",
			"payment__invoice",
			"payment__receipt",
			"payment__student",
			"payment__student__account",
			"payment__student__account__user",
		)
		if self._can_access_all_payments(self.request.user):
			return queryset

		student_profile = self._student_profile(self.request.user)
		if not student_profile:
			return Invoice.objects.none()
		return queryset.filter(payment__student=student_profile)


class ReceiptDetailView(PaymentBaseQuerySetMixin, LoginRequiredMixin, DetailView):
	model = Receipt
	template_name = "payments/receipt_detail.html"
	context_object_name = "receipt"

	def get_queryset(self):
		queryset = Receipt.objects.select_related(
			"payment",
			"payment__invoice",
			"payment__receipt",
			"payment__student",
			"payment__student__account",
			"payment__student__account__user",
		)
		if self._can_access_all_payments(self.request.user):
			return queryset

		student_profile = self._student_profile(self.request.user)
		if not student_profile:
			return Receipt.objects.none()
		return queryset.filter(payment__student=student_profile)

