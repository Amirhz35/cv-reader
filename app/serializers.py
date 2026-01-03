from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from cv_screening.exceptions import ValidationException, AuthenticationException, NotFoundException
from bson import ObjectId
from django.contrib.auth import authenticate
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.db import connection
import mongoengine
from cv_screening.celery import app
from .models import CustomUser, CVUpload, CVEvaluationRequest
from .tasks import evaluate_cv_task
from .services.otp_service import otp_service
from .services.email_service import email_service


class UserSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    email = serializers.CharField(required=True)
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    job_position = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    password = serializers.CharField(required=True, write_only=True)
    password_confirm = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise ValidationException("password_mismatch", "Passwords don't match")

        # Check uniqueness only against existing users (not pending registrations)
        if CustomUser.objects.filter(username=attrs['username']).exists():
            raise ValidationException("username_exists", "Username already exists")

        if CustomUser.objects.filter(email=attrs['email']).exists():
            raise ValidationException("email_exists", "Email already exists")

        return attrs

    def create(self, validated_data):
        from .services.otp_service import otp_service
        from .services.email_service import email_service

        # Extract data
        username = validated_data['username']
        email = validated_data['email']
        password = validated_data['password']
        first_name = validated_data['first_name']
        last_name = validated_data['last_name']
        job_position = validated_data.get('job_position', '')

        # Store pending registration in Redis
        if not otp_service.store_pending_registration(username, email, password, first_name, last_name, job_position):
            raise ValidationException("registration_failed", "Failed to initiate registration")

        # Generate and store OTP
        otp_code = otp_service.create_otp(email)
        if not otp_code:
            raise ValidationException("otp_generation_failed", "Failed to generate OTP")

        # Send OTP email
        if not email_service.send_otp_email(email, otp_code):
            # Clean up on email failure
            otp_service.cleanup_expired_data(email)
            raise ValidationException("email_send_failed", "Failed to send verification email")

        self._data = {
            'email': email,
            'message': 'Registration initiated. Please check your email for the OTP verification code.'
        }
        return True


class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(required=True)
    password = serializers.CharField(required=True)

    def validate(self, attrs):
        identifier = attrs['identifier']
        password = attrs['password']

        user = authenticate(username=identifier, password=password)

        if user is None and '@' in identifier:
            try:
                user_obj = CustomUser.objects.get(email=identifier)
                user = authenticate(username=user_obj.username, password=password)
            except CustomUser.DoesNotExist:
                user = None

        if user is None:
            raise AuthenticationException("invalid_credentials", "Invalid username or password")

        attrs['user'] = user
        return attrs

    def create(self, validated_data):
        user = validated_data['user']
        refresh = RefreshToken.for_user(user)

        self._data = {
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'job_position': user.job_position,
            },
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        }
        return True


class CVUploadSerializer(serializers.Serializer):
    prompt = serializers.CharField(required=True, max_length=8000)
    file = serializers.FileField(required=True)

    def validate_prompt(self, value):
        if len(value.strip()) < 10:
            raise serializers.ValidationError("Prompt must be at least 10 characters long")
        return value.strip()

    def validate_file(self, file):
        if file.size > 10 * 1024 * 1024:
            raise serializers.ValidationError({"file": "File size must be less than 10MB"})

        allowed_types = ['application/pdf']
        if file.content_type not in allowed_types:
            raise serializers.ValidationError({"file": "Only PDF files are allowed"})

        return file

    def create(self, validated_data):
        request = self.context['request']
        user = request.user
        uploaded_file = validated_data['file']
        prompt = validated_data['prompt']

        user_id = user.id
        filename = f"{user_id}_{uploaded_file.name}"

        file_path = f"cvs/{filename}"
        file_content = b''
        for chunk in uploaded_file.chunks():
            file_content += chunk

        saved_file = default_storage.save(file_path, ContentFile(file_content))

        cv_upload = CVUpload(
            user_id=str(user_id),
            original_filename=uploaded_file.name,
            file_size=uploaded_file.size,
            mime_type=uploaded_file.content_type,
            storage_uri=saved_file  # Store relative path, not full URL
        )
        cv_upload.save()

        evaluation = CVEvaluationRequest(
            user_id=str(user_id),
            cv_id=str(cv_upload.id),
            prompt=prompt
        )
        evaluation.save()

        evaluate_cv_task.delay(str(evaluation.id))

        self._data = {
            'id': str(evaluation.id),
            'status': evaluation.status,
            'message': 'CV evaluation request created successfully'
        }
        return True


class CVEvaluationSerializer(serializers.Serializer):
    evaluation_id = serializers.CharField(required=False)

    def to_representation(self, instance):
        user = self.context['user']
        query_params = self.context.get('query_params', {})
        evaluation_id = query_params.get('evaluation_id')
        data = {
            "code":"success",
            "result": []
        }

        if evaluation_id:
            try:
                evaluations = CVEvaluationRequest.objects.filter(id=ObjectId(evaluation_id), user_id=str(user.id))
                if not evaluations:
                    raise NotFoundException("Evaluation request not found")
            except ObjectId.InvalidId:
                raise NotFoundException("Evaluation request not found")
        else:
            evaluations = CVEvaluationRequest.objects.filter(user_id=str(user.id)).order_by('-created_at')

        for evaluation in evaluations:
            cv_filename = None
            cv_uploaded_at = None
            try:
                cv_upload = CVUpload.objects.get(id=ObjectId(evaluation.cv_id))
                cv_filename = cv_upload.original_filename
                cv_uploaded_at = cv_upload.uploaded_at
            except CVUpload.DoesNotExist:
                pass
            data["result"].append({
                'id': str(evaluation.id),
                'cv_id': evaluation.cv_id,
                'prompt': evaluation.prompt,
                'status': evaluation.status,
                'ai_response': evaluation.ai_response,
                'score': evaluation.score,
                'error_message': evaluation.error_message,
                'created_at': evaluation.created_at,
                'updated_at': evaluation.updated_at,
                'cv_filename': cv_filename,
                'cv_uploaded_at': cv_uploaded_at,
            })
        return data


class HealthCheckSerializer(serializers.Serializer):
    def create(self, validated_data):
        health_status = {
            'status': 'healthy',
            'services': {}
        }

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                health_status['services']['mysql'] = 'healthy'
        except Exception as e:
            health_status['services']['mysql'] = f'unhealthy: {str(e)}'
            health_status['status'] = 'unhealthy'

        try:
            mongoengine.connection.get_db().command('ping')
            health_status['services']['mongodb'] = 'healthy'
        except Exception as e:
            health_status['services']['mongodb'] = f'unhealthy: {str(e)}'
            health_status['status'] = 'unhealthy'

        try:
            inspect = app.control.inspect()
            active_tasks = inspect.active()
            if active_tasks:
                health_status['services']['celery'] = 'healthy'
            else:
                health_status['services']['celery'] = 'healthy (no active tasks)'
        except Exception as e:
            health_status['services']['celery'] = f'unhealthy: {str(e)}'

        self._data = health_status
        return True


class OTPVerifySerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    code = serializers.CharField(
        required=True,
        min_length=6,
        max_length=6,
        help_text="6-digit OTP code"
    )

    def validate_code(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("OTP code must contain only digits")
        return value

    def create(self, validated_data):
        email = validated_data['email']
        code = validated_data['code']

        # Verify OTP code
        success, message = otp_service.verify_otp(email, code)

        if not success:
            raise ValidationException("otp_verification_failed", message)

        # Get pending registration data and complete registration
        registration_data = otp_service.complete_registration(email)
        if not registration_data:
            raise ValidationException("registration_not_found", "Registration data not found")

        # Create the user account
        user = CustomUser.create_user(
            username=registration_data['username'],
            password=registration_data['password'],  # Raw password - will be hashed by create_user
            email=registration_data['email'],
            first_name=registration_data['first_name'],
            last_name=registration_data['last_name'],
            job_position=registration_data.get('job_position', '')
        )

        # Issue JWT tokens
        refresh = RefreshToken.for_user(user)

        response_data = {
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'job_position': user.job_position,
            },
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        }

        self._data = response_data
        return True


class OTPResendSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

    def create(self, validated_data):
        email = validated_data['email']

        # Check if there's a pending registration
        pending_data = otp_service.get_pending_registration(email)
        if not pending_data:
            raise ValidationException("no_pending_registration", "No pending registration found for this email")

        # Check OTP data for rate limiting
        otp_data = otp_service.get_otp_data(email)
        if otp_data and not otp_service.can_resend_otp(otp_data):
            raise ValidationException("rate_limited", "Please wait at least 1 minute before requesting a new OTP")

        # Generate new OTP
        new_otp = otp_service.create_otp(email)
        if not new_otp:
            raise ValidationException("otp_generation_failed", "Failed to generate new OTP")

        # Send new OTP email
        if not email_service.send_otp_email(email, new_otp):
            # Clean up on email failure
            otp_service.cleanup_expired_data(email)
            raise ValidationException("email_send_failed", "Failed to send verification email")

        self._data = {'message': 'New OTP sent to your email'}
        return True


class ProfileGetSerializer(serializers.Serializer):
    """Serializer for getting user profile data."""
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)
    job_position = serializers.CharField(read_only=True)
    date_joined = serializers.DateTimeField(read_only=True)
    last_login = serializers.DateTimeField(read_only=True)

    def to_representation(self, instance):
        """Return user profile data."""
        return {
            'id': instance.id,
            'username': instance.username,
            'email': instance.email,
            'first_name': instance.first_name,
            'last_name': instance.last_name,
            'job_position': instance.job_position,
            'date_joined': instance.date_joined,
            'last_login': instance.last_login,
        }


class ProfileUpdateSerializer(serializers.Serializer):
    """Serializer for updating user profile data."""
    username = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    job_position = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_username(self, value):
        """Check if username is unique (excluding current user)."""
        user = self.context.get('user')
        if user and CustomUser.objects.filter(username=value).exclude(id=user.id).exists():
            raise ValidationException("username_exists", "Username already exists")
        return value

    def validate_email(self, value):
        """Check if email is unique (excluding current user)."""
        user = self.context.get('user')
        if user and CustomUser.objects.filter(email=value).exclude(id=user.id).exists():
            raise ValidationException("email_exists", "Email already exists")
        return value

    def to_representation(self, instance):
        """Return updated user profile data."""
        return {
            'id': instance.id,
            'username': instance.username,
            'email': instance.email,
            'first_name': instance.first_name,
            'last_name': instance.last_name,
            'job_position': instance.job_position,
            'date_joined': instance.date_joined,
            'last_login': instance.last_login,
        }

    def update(self, instance, validated_data):
        """Update user profile."""
        instance.username = validated_data.get('username', instance.username)
        instance.email = validated_data.get('email', instance.email)
        instance.first_name = validated_data.get('first_name', instance.first_name)
        instance.last_name = validated_data.get('last_name', instance.last_name)
        instance.job_position = validated_data.get('job_position', instance.job_position)
        instance.save()
        return instance


class ProfileDeleteSerializer(serializers.Serializer):
    """Serializer for account deletion confirmation."""
    password = serializers.CharField(required=True, write_only=True, help_text="User password for confirmation")

    def validate(self, attrs):
        """Verify password before allowing deletion."""
        user = self.context.get('user')
        password = attrs['password']

        if not user.check_password(password):
            raise ValidationException("invalid_password", "Invalid password")

        return attrs

    def create(self, validated_data):
        """Delete user account."""
        user = self.context.get('user')
        user_id = user.id
        user.delete()

        self._data = {'message': 'User account deleted successfully'}
        return True


class PasswordChangeSerializer(serializers.Serializer):
    """Serializer for changing user password."""
    old_password = serializers.CharField(required=True, write_only=True, help_text="Current password")
    new_password = serializers.CharField(required=True, write_only=True, help_text="New password")
    new_password_confirm = serializers.CharField(required=True, write_only=True, help_text="New password confirmation")

    def validate(self, attrs):
        """Validate password change."""
        old_password = attrs['old_password']
        new_password = attrs['new_password']
        new_password_confirm = attrs['new_password_confirm']
        user = self.context.get('user')

        # Verify old password
        if not user.check_password(old_password):
            raise ValidationException("invalid_old_password", "Current password is incorrect")

        # Check if new passwords match
        if new_password != new_password_confirm:
            raise ValidationException("password_mismatch", "New passwords don't match")

        # Check if new password is different from old password
        if user.check_password(new_password):
            raise ValidationException("same_password", "New password must be different from current password")

        return attrs

    def create(self, validated_data):
        """Change user password."""
        user = self.context.get('user')
        new_password = validated_data['new_password']
        
        user.set_password(new_password)
        user.save()

        self._data = {'message': 'Password changed successfully'}
        return True

