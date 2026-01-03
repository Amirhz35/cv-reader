"""
Email service for sending OTP verification emails.
"""
import logging
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending email notifications."""

    def send_otp_email(self, email: str, otp_code: str) -> bool:
        """
        Send OTP verification code via email.

        Args:
            email: Recipient's email address
            otp_code: 6-digit OTP code to send

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            subject = "Your OTP Verification Code"
            message = f"""
Hello,

Your OTP verification code is: {otp_code}

This code will expire in 2 minutes. Please enter it to complete your registration.

If you did not request this code, please ignore this email.

Best regards,
CV Screening Platform
"""
            from_email = getattr(settings, 'EMAIL_HOST_USER', 'noreply@cvplatform.com')

            send_mail(
                subject=subject,
                message=message,
                from_email=from_email,
                recipient_list=[email],
                fail_silently=False
            )

            logger.info(f"OTP email sent successfully to {email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send OTP email to {email}: {str(e)}")
            return False

    def send_password_reset_otp_email(self, email: str, otp_code: str) -> bool:
        """
        Send password reset OTP code via email.

        Args:
            email: Recipient's email address
            otp_code: 6-digit OTP code to send

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            subject = "Password Reset Verification Code"
            message = f"""
Hello,

You have requested to reset your password. Your OTP verification code is: {otp_code}

This code will expire in 2 minutes. Please enter it to reset your password.

If you did not request a password reset, please ignore this email and your password will remain unchanged.

Best regards,
CV Screening Platform
"""
            from_email = getattr(settings, 'EMAIL_HOST_USER', 'noreply@cvplatform.com')

            send_mail(
                subject=subject,
                message=message,
                from_email=from_email,
                recipient_list=[email],
                fail_silently=False
            )

            logger.info(f"Password reset OTP email sent successfully to {email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send password reset OTP email to {email}: {str(e)}")
            return False


# Global service instance
email_service = EmailService()
