import threading


_request_local = threading.local()


def set_current_user(user):
    _request_local.user = user


def get_current_user():
    return getattr(_request_local, "user", None)


def set_client_ip(ip_address):
    _request_local.client_ip = ip_address


def get_client_ip():
    return getattr(_request_local, "client_ip", None)


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        set_current_user(getattr(request, "user", None))
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
        ip_address = (forwarded_for.split(",")[0].strip() if forwarded_for else request.META.get("REMOTE_ADDR"))
        set_client_ip(ip_address)
        response = self.get_response(request)
        set_current_user(None)
        set_client_ip(None)
        return response
