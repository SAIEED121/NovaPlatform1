from django.urls import path
from . import views

app_name = "payments"

urlpatterns = [
	path("", views.PaymentListView.as_view(), name="payment_list"),
	path("history/", views.PaymentHistoryView.as_view(), name="payment_history"),
	path("request/", views.PaymentRequestCreateView.as_view(), name="payment_request"),
	path("create/", views.PaymentCreateView.as_view(), name="payment_create"),
	path("<int:pk>/", views.PaymentDetailView.as_view(), name="payment_detail"),
	path("<int:pk>/approve/", views.PaymentApproveView.as_view(), name="payment_approve"),
	path("<int:pk>/edit/", views.PaymentUpdateView.as_view(), name="payment_update"),
	path("<int:pk>/delete/", views.PaymentDeleteView.as_view(), name="payment_delete"),
	path("invoices/<int:pk>/", views.InvoiceDetailView.as_view(), name="invoice_detail"),
	path("receipts/<int:pk>/", views.ReceiptDetailView.as_view(), name="receipt_detail"),
]
