"""
URL configuration for the app.
"""

from django.urls import path
from .views import (
    RegisterView, LoginView, TokenRefreshView,
    CVEvaluationView, CVEvaluationCreateView, CVFileView, HealthCheckView,
    OTPVerifyView, OTPResendView,
    ProfileGetView, ProfileUpdateView, ProfileDeleteView,
    PasswordChangeView, PasswordResetRequestView, PasswordResetVerifyView,
    PasswordResetResendView
)

app_name = 'app'

urlpatterns = [
    # Authentication endpoints
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # OTP verification endpoints
    path('auth/otp/verify/', OTPVerifyView.as_view(), name='otp_verify'),
    path('auth/otp/resend/', OTPResendView.as_view(), name='otp_resend'),

    # Password reset endpoints
    path('auth/password-reset/request/', PasswordResetRequestView.as_view(), name='password-reset-request'),
    path('auth/password-reset/verify/', PasswordResetVerifyView.as_view(), name='password-reset-verify'),
    path('auth/password-reset/resend/', PasswordResetResendView.as_view(), name='password-reset-resend'),

    # CV file download endpoint
    path('cv-files/<str:file_id>/', CVFileView.as_view(), name='cv-file-download'),

    # CV evaluation endpoints
    path('cv-evaluations/', CVEvaluationView.as_view(), name='cv-evaluation-combined'),
    path('cv-evaluations/create/', CVEvaluationCreateView.as_view(), name='cv-evaluation-create'),

    # Health check endpoint
    path('health/', HealthCheckView.as_view(), name='health-check'),

    # Profile endpoints
    path('profile/', ProfileGetView.as_view(), name='profile-get'),
    path('profile/update/', ProfileUpdateView.as_view(), name='profile-update'),
    path('profile/delete/', ProfileDeleteView.as_view(), name='profile-delete'),
    path('profile/change-password/', PasswordChangeView.as_view(), name='password-change'),
]
