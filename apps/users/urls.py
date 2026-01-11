from django.urls import path
from .views import (
    CheckEmailView, RegisterView, LoginView,
    RequestOTPView, OTPLonView, ChangePasswordView, DeleteAccountView,
    ChangeEmailView, MeView, LogoutView, OCRProcessView  # add LogoutView
)

# Note: these paths are included under the project's `config.urls` as `path('auth/', include('apps.users.urls'))`
# so we DO NOT prefix them again with 'auth/' here. Calling /auth/check-email/ will resolve correctly.
urlpatterns = [
    path('check-email/', CheckEmailView.as_view(), name='check_email'),
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('request-otp/', RequestOTPView.as_view(), name='request_otp'),
    path('verify-otp/', OTPLonView.as_view(), name='verify_otp'),
    path('change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('change-email/', ChangeEmailView.as_view(), name='change_email'),
    path('delete-account/', DeleteAccountView.as_view(), name='delete_account'),
    path('me/', MeView.as_view(), name='me'),  # new: GET /auth/me/
    path('logout/', LogoutView.as_view(), name='logout'),
    path('api/process-ocr/', OCRProcessView.as_view(), name='process-ocr'),  # OCR Process API
]