"""
Redis-based OTP service for email verification during registration.
"""
import json
import random
import string
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
import redis
import django
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.hashers import make_password

# Setup Django
django.setup()


class OTPService:
    """Redis-based service for handling OTP and pending registrations."""

    def __init__(self):
        """Initialize Redis connection."""
        redis_url = getattr(settings, 'CELERY_BROKER_URL', 'redis://redis:6379/0')
        # Extract host and port from Redis URL
        if redis_url.startswith('redis://'):
            redis_url = redis_url.replace('redis://', '')
        if '/' in redis_url:
            host_port, db = redis_url.rsplit('/', 1)
        else:
            host_port = redis_url
            db = '0'

        if ':' in host_port:
            host, port = host_port.split(':', 1)
        else:
            host = host_port
            port = 6379

        self.redis = redis.Redis(
            host=host,
            port=int(port),
            db=int(db),
            decode_responses=True
        )

    def _get_pending_registration_key(self, email: str) -> str:
        """Get Redis key for pending registration."""
        return f"pending_registration:{email.lower()}"

    def _get_otp_key(self, email: str) -> str:
        """Get Redis key for OTP data."""
        return f"otp:{email.lower()}"

    def generate_otp_code(self) -> str:
        """Generate a 6-digit random OTP code."""
        return ''.join(random.choices(string.digits, k=6))

    def store_pending_registration(self, username: str, email: str, password: str,
                                   first_name: str, last_name: str) -> bool:
        """
        Store pending registration data in Redis.

        Args:
            username: User's username
            email: User's email
            password: Raw password (will be hashed)
            first_name: User's first name
            last_name: User's last name

        Returns:
            bool: True if stored successfully
        """
        try:
            # Hash the password
            hashed_password = make_password(password)

            data = {
                'username': username,
                'email': email.lower(),
                'password_hash': hashed_password,
                'first_name': first_name,
                'last_name': last_name,
                'created_at': timezone.now().isoformat()
            }

            key = self._get_pending_registration_key(email)
            # Store for 5 minutes (2 minutes OTP expiry + 3 minutes buffer)
            self.redis.setex(key, 300, json.dumps(data))
            return True
        except Exception:
            return False

    def get_pending_registration(self, email: str) -> Optional[Dict]:
        """
        Retrieve pending registration data.

        Args:
            email: User's email

        Returns:
            Dict with registration data or None if not found
        """
        try:
            key = self._get_pending_registration_key(email)
            data = self.redis.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception:
            return None

    def create_otp(self, email: str) -> Optional[str]:
        """
        Create and store OTP for email verification.

        Args:
            email: User's email

        Returns:
            str: Generated OTP code or None if failed
        """
        try:
            # Check if there's already an active OTP and if it can be resent
            existing_otp_data = self.get_otp_data(email)
            if existing_otp_data and not self.can_resend_otp(existing_otp_data):
                return None

            code = self.generate_otp_code()
            expires_at = timezone.now() + timedelta(minutes=2)

            otp_data = {
                'code': code,
                'expires_at': expires_at.isoformat(),
                'attempts_left': 5,
                'last_sent_at': timezone.now().isoformat()
            }

            key = self._get_otp_key(email)
            # Store for 2 minutes (OTP expiry time)
            self.redis.setex(key, 120, json.dumps(otp_data))
            return code
        except Exception:
            return None

    def get_otp_data(self, email: str) -> Optional[Dict]:
        """
        Get OTP data for email.

        Args:
            email: User's email

        Returns:
            Dict with OTP data or None if not found
        """
        try:
            key = self._get_otp_key(email)
            data = self.redis.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception:
            return None

    def can_resend_otp(self, otp_data: Dict) -> bool:
        """
        Check if OTP can be resent (rate limit: 1 per minute).

        Args:
            otp_data: OTP data dictionary

        Returns:
            bool: True if can resend
        """
        try:
            last_sent = datetime.fromisoformat(otp_data['last_sent_at'])
            time_diff = timezone.now() - last_sent
            return time_diff.total_seconds() >= 60
        except Exception:
            return True  # If error, allow resend

    def verify_otp(self, email: str, code: str) -> Tuple[bool, str]:
        """
        Verify OTP code.

        Args:
            email: User's email
            code: OTP code to verify

        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            otp_data = self.get_otp_data(email)
            if not otp_data:
                return False, "OTP not found or expired"

            # Check expiry
            expires_at = datetime.fromisoformat(otp_data['expires_at'])
            if timezone.now() > expires_at:
                return False, "OTP has expired"

            # Check attempts
            if otp_data['attempts_left'] <= 0:
                return False, "Too many failed attempts"

            # Check code
            if otp_data['code'] != code:
                # Decrement attempts
                otp_data['attempts_left'] -= 1
                key = self._get_otp_key(email)
                self.redis.setex(key, 120, json.dumps(otp_data))
                return False, f"Invalid OTP. {otp_data['attempts_left']} attempts remaining"

            return True, "OTP verified successfully"

        except Exception as e:
            return False, f"Verification error: {str(e)}"

    def complete_registration(self, email: str) -> Optional[Dict]:
        """
        Complete registration by retrieving and clearing pending data.

        Args:
            email: User's email

        Returns:
            Dict with registration data or None if not found
        """
        try:
            # Get pending registration data
            registration_data = self.get_pending_registration(email)
            if not registration_data:
                return None

            # Clear both pending registration and OTP data
            pending_key = self._get_pending_registration_key(email)
            otp_key = self._get_otp_key(email)

            self.redis.delete(pending_key, otp_key)

            return registration_data
        except Exception:
            return None

    def cleanup_expired_data(self, email: str):
        """
        Clean up expired registration and OTP data.

        Args:
            email: User's email
        """
        try:
            pending_key = self._get_pending_registration_key(email)
            otp_key = self._get_otp_key(email)
            self.redis.delete(pending_key, otp_key)
        except Exception:
            pass


# Global service instance
otp_service = OTPService()
