from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.views import TokenRefreshView
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes, OpenApiResponse
from bson import ObjectId
from django.core.files.storage import default_storage
from django.http import HttpResponse
from .serializers import (
    UserSerializer, LoginSerializer, CVUploadSerializer,
    CVEvaluationSerializer, HealthCheckSerializer,
    OTPVerifySerializer, OTPResendSerializer,
    ProfileGetSerializer, ProfileUpdateSerializer, ProfileDeleteSerializer,
    PasswordChangeSerializer
)
from .models import CustomUser, CVUpload, CVEvaluationRequest



class RegisterView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Initiate User Registration",
        description="Initiate user registration by storing user data and sending OTP verification code to email. User account is not created until OTP is verified.",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'username': {'type': 'string', 'description': 'Unique username'},
                    'email': {'type': 'string', 'format': 'email', 'description': 'User email address'},
                    'first_name': {'type': 'string', 'description': 'User first name'},
                    'last_name': {'type': 'string', 'description': 'User last name'},
                    'job_position': {'type': 'string', 'description': 'User job position', 'nullable': True},
                    'password': {'type': 'string', 'format': 'password', 'description': 'User password'},
                    'password_confirm': {'type': 'string', 'format': 'password', 'description': 'Password confirmation'},
                },
                'required': ['username', 'email', 'first_name', 'last_name', 'password', 'password_confirm']
            }
        },
        responses={
            200: OpenApiResponse(
                description="Registration initiated, OTP sent to email",
                response={
                    'type': 'object',
                    'properties': {
                        'email': {'type': 'string', 'format': 'email', 'description': 'User email'},
                        'message': {'type': 'string', 'description': 'Success message'},
                    }
                }
            ),
            400: OpenApiResponse(description="Validation error")
        }
    )
    def post(self, request):
        serializer = UserSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(data=serializer.data, status=status.HTTP_200_OK)


class LoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="User Login",
        description="Authenticate user with username and password to obtain JWT tokens.",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'identifier': {'type': 'string', 'description': 'Username or email'},
                    'password': {'type': 'string', 'format': 'password', 'description': 'User password'},
                },
                'required': ['identifier', 'password']
            }
        },
        responses={
            200: OpenApiResponse(
                description="Login successful",
                response={
                    'type': 'object',
                    'properties': {
                        'user': {
                            'type': 'object',
                            'properties': {
                                'id': {'type': 'integer', 'description': 'User ID'},
                                'username': {'type': 'string', 'description': 'Username'},
                                'email': {'type': 'string', 'format': 'email', 'description': 'User email'},
                                'first_name': {'type': 'string', 'description': 'First name'},
                                'last_name': {'type': 'string', 'description': 'Last name'},
                                'job_position': {'type': 'string', 'description': 'Job position', 'nullable': True},
                            }
                        },
                        'tokens': {
                            'type': 'object',
                            'properties': {
                                'refresh': {'type': 'string', 'description': 'JWT refresh token'},
                                'access': {'type': 'string', 'description': 'JWT access token'},
                            }
                        }
                    }
                }
            ),
            400: OpenApiResponse(description="Validation error - invalid credentials")
        }
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(data=serializer.data, status=status.HTTP_200_OK)


class CVEvaluationView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get CV Evaluations",
        description="Retrieve CV evaluation history for the authenticated user. Can filter by specific evaluation ID.",
        parameters=[
            OpenApiParameter(
                name='evaluation_id',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Optional evaluation ID to retrieve specific evaluation',
                required=False
            )
        ],
        responses={
            200: OpenApiResponse(
                description="CV evaluations retrieved successfully",
                response={
                    'type': 'object',
                    'properties': {
                        'code': {'type': 'string', 'example': 'success'},
                        'result': {
                            'type': 'array',
                            'items': {
                                'type': 'object',
                                'properties': {
                                    'id': {'type': 'string', 'description': 'Evaluation ID'},
                                    'cv_id': {'type': 'string', 'description': 'CV upload ID'},
                                    'prompt': {'type': 'string', 'description': 'Evaluation prompt'},
                                    'status': {'type': 'integer', 'enum': [0, 1, 2, 3], 'description': 'Evaluation status (0=pending, 1=processing, 2=completed, 3=failed)'},
                                    'ai_response': {'type': 'object', 'nullable': True, 'description': 'AI evaluation response'},
                                    'score': {'type': 'number', 'nullable': True, 'description': 'Evaluation score'},
                                    'error_message': {'type': 'string', 'nullable': True, 'description': 'Error message if evaluation failed'},
                                    'created_at': {'type': 'string', 'format': 'date-time', 'description': 'Creation timestamp'},
                                    'updated_at': {'type': 'string', 'format': 'date-time', 'description': 'Last update timestamp'},
                                    'cv_filename': {'type': 'string', 'nullable': True, 'description': 'Original CV filename'},
                                    'cv_uploaded_at': {'type': 'string', 'format': 'date-time', 'nullable': True, 'description': 'CV upload timestamp'},
                                }
                            }
                        }
                    }
                }
            ),
            401: OpenApiResponse(description="Unauthorized - authentication required"),
            404: OpenApiResponse(description="Evaluation not found")
        }
    )
    def get(self, request):
        query_params = request.query_params
        context = {
            'user': request.user,
            'request': request,
            'query_params': query_params
        }
        serializer = CVEvaluationSerializer(context=context)
        result = serializer.to_representation({})
        return Response(data=result, status=status.HTTP_200_OK)

class CVEvaluationCreateView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        summary="Create CV Evaluation",
        description="Upload a CV file (PDF) and create an evaluation request with a custom prompt.",
        request={
            'multipart/form-data': {
                'type': 'object',
                'properties': {
                    'file': {
                        'type': 'string',
                        'format': 'binary',
                        'description': 'CV file to evaluate (PDF format, max 10MB)'
                    },
                    'prompt': {
                        'type': 'string',
                        'description': 'Evaluation prompt describing the requirements (minimum 10 characters)'
                    }
                },
                'required': ['file', 'prompt']
            }
        },
        responses={
            201: OpenApiResponse(
                description="CV evaluation request created successfully",
                response={
                    'type': 'object',
                    'properties': {
                        'id': {'type': 'string', 'description': 'Evaluation request ID'},
                        'status': {'type': 'integer', 'enum': [0], 'description': 'Initial status (0=pending)'},
                        'message': {'type': 'string', 'description': 'Success message'},
                    }
                }
            ),
            400: OpenApiResponse(description="Validation error - invalid file or prompt"),
            401: OpenApiResponse(description="Unauthorized - authentication required")
        }
    )
    def post(self, request):
        serializer = CVUploadSerializer(data=request.data, context={'request': request, 'user': request.user})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(data=serializer.data, status=status.HTTP_200_OK)


class HealthCheckView(APIView):
    permission_classes = []

    @extend_schema(
        summary="Health Check",
        description="Check the health status of all system services (MySQL, MongoDB, Celery).",
        responses={
            200: OpenApiResponse(
                description="Health check completed",
                response={
                    'type': 'object',
                    'properties': {
                        'status': {'type': 'string', 'enum': ['healthy', 'unhealthy'], 'description': 'Overall system health'},
                        'services': {
                            'type': 'object',
                            'properties': {
                                'mysql': {'type': 'string', 'description': 'MySQL database status'},
                                'mongodb': {'type': 'string', 'description': 'MongoDB database status'},
                                'celery': {'type': 'string', 'description': 'Celery task queue status'}
                            }
                        }
                    }
                }
            )
        }
    )
    def get(self, request):
        serializer = HealthCheckSerializer(context={'request': request})
        result = serializer.create({})
        return Response(data=result, status=status.HTTP_200_OK)


class CVFileView(APIView):
    """View to serve CV files to frontend."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Download CV File",
        description="Download a previously uploaded CV file by its ID.",
        parameters=[
            OpenApiParameter(
                name='file_id',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.PATH,
                description='Unique identifier of the CV file to download',
                required=True
            )
        ],
        responses={
            200: OpenApiResponse(
                description="File download successful",
                response={
                    'type': 'string',
                    'format': 'binary',
                    'description': 'The CV file content'
                }
            ),
            400: OpenApiResponse(description="File ID required"),
            401: OpenApiResponse(description="Unauthorized - authentication required"),
            404: OpenApiResponse(description="File not found"),
            500: OpenApiResponse(description="Error reading file")
        }
    )
    def get(self, request, file_id=None):
        if not file_id:
            return Response({'error': 'File ID required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            cv_upload = CVUpload.objects.get(id=ObjectId(file_id), user_id=str(request.user.id))
        except CVUpload.DoesNotExist:
            return Response({'error': 'File not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
            with default_storage.open(cv_upload.storage_uri, 'rb') as file_obj:
                file_content = file_obj.read()

            response = HttpResponse(file_content, content_type=cv_upload.mime_type)
            response['Content-Disposition'] = f'attachment; filename="{cv_upload.original_filename}"'
            response['Content-Length'] = len(file_content)
            return response

        except Exception as e:
            return Response({'error': f'Error reading file: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class OTPVerifyView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Verify OTP Code",
        description="Verify OTP code to complete user registration. OTP codes are 6 digits, expire after 2 minutes, and allow maximum 5 verification attempts.",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'email': {'type': 'string', 'format': 'email', 'description': 'User email address'},
                    'code': {'type': 'string', 'minLength': 6, 'maxLength': 6, 'description': '6-digit OTP code'},
                },
                'required': ['email', 'code']
            }
        },
        responses={
            201: OpenApiResponse(
                description="OTP verified successfully, user account created",
                response={
                    'type': 'object',
                    'properties': {
                        'user': {
                            'type': 'object',
                            'properties': {
                                'id': {'type': 'integer', 'description': 'User ID'},
                                'username': {'type': 'string', 'description': 'Username'},
                                'email': {'type': 'string', 'format': 'email', 'description': 'User email'},
                                'first_name': {'type': 'string', 'description': 'First name'},
                                'last_name': {'type': 'string', 'description': 'Last name'},
                                'job_position': {'type': 'string', 'description': 'Job position', 'nullable': True},
                            }
                        },
                        'tokens': {
                            'type': 'object',
                            'properties': {
                                'refresh': {'type': 'string', 'description': 'JWT refresh token'},
                                'access': {'type': 'string', 'description': 'JWT access token'},
                            }
                        }
                    }
                }
            ),
            400: OpenApiResponse(description="OTP verification failed - invalid code, expired, or too many attempts"),
        }
    )
    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(data=serializer.data, status=status.HTTP_201_CREATED)


class OTPResendView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Resend OTP Code",
        description="Request a new OTP code for email verification. Rate limited to 1 request per minute. Only works if there's a pending registration for the email.",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'email': {'type': 'string', 'format': 'email', 'description': 'User email address'},
                },
                'required': ['email']
            }
        },
        responses={
            200: OpenApiResponse(
                description="New OTP sent successfully",
                response={
                    'type': 'object',
                    'properties': {
                        'message': {'type': 'string', 'description': 'Success message'},
                    }
                }
            ),
            400: OpenApiResponse(description="No pending registration found for this email"),
            429: OpenApiResponse(description="Rate limited - please wait before requesting another OTP"),
        }
    )
    def post(self, request):
        serializer = OTPResendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(data=serializer.data, status=status.HTTP_200_OK)


class ProfileGetView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get User Profile",
        description="Retrieve the authenticated user's profile information.",
        responses={
            200: OpenApiResponse(
                description="Profile retrieved successfully",
                response={
                    'type': 'object',
                    'properties': {
                        'id': {'type': 'integer', 'description': 'User ID'},
                        'username': {'type': 'string', 'description': 'Username'},
                        'email': {'type': 'string', 'format': 'email', 'description': 'User email'},
                        'first_name': {'type': 'string', 'description': 'First name'},
                        'last_name': {'type': 'string', 'description': 'Last name'},
                        'job_position': {'type': 'string', 'description': 'Job position', 'nullable': True},
                        'date_joined': {'type': 'string', 'format': 'date-time', 'description': 'Account creation date'},
                        'last_login': {'type': 'string', 'format': 'date-time', 'description': 'Last login date'},
                    }
                }
            ),
            401: OpenApiResponse(description="Unauthorized - authentication required")
        }
    )
    def get(self, request):
        serializer = ProfileGetSerializer(instance=request.user, context={'user': request.user})
        return Response(data=serializer.data, status=status.HTTP_200_OK)


class ProfileUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Update User Profile",
        description="Update the authenticated user's profile information. All fields are optional.",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'username': {'type': 'string', 'description': 'Username'},
                    'email': {'type': 'string', 'format': 'email', 'description': 'User email address'},
                    'first_name': {'type': 'string', 'description': 'User first name'},
                    'last_name': {'type': 'string', 'description': 'User last name'},
                    'job_position': {'type': 'string', 'description': 'User job position', 'nullable': True},
                }
            }
        },
        responses={
            200: OpenApiResponse(
                description="Profile updated successfully",
                response={
                    'type': 'object',
                    'properties': {
                        'id': {'type': 'integer', 'description': 'User ID'},
                        'username': {'type': 'string', 'description': 'Username'},
                        'email': {'type': 'string', 'format': 'email', 'description': 'User email'},
                        'first_name': {'type': 'string', 'description': 'First name'},
                        'last_name': {'type': 'string', 'description': 'Last name'},
                        'job_position': {'type': 'string', 'description': 'Job position', 'nullable': True},
                        'date_joined': {'type': 'string', 'format': 'date-time', 'description': 'Account creation date'},
                        'last_login': {'type': 'string', 'format': 'date-time', 'description': 'Last login date'},
                    }
                }
            ),
            400: OpenApiResponse(description="Validation error"),
            401: OpenApiResponse(description="Unauthorized - authentication required")
        }
    )
    def post(self, request):
        serializer = ProfileUpdateSerializer(
            instance=request.user,
            data=request.data,
            context={'user': request.user},
            partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(data=serializer.data, status=status.HTTP_200_OK)


class ProfileDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Delete User Account",
        description="Delete the authenticated user's account. Requires password confirmation for security.",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'password': {'type': 'string', 'format': 'password', 'description': 'User password for confirmation'},
                },
                'required': ['password']
            }
        },
        responses={
            200: OpenApiResponse(
                description="Account deleted successfully",
                response={
                    'type': 'object',
                    'properties': {
                        'message': {'type': 'string', 'description': 'Success message'},
                    }
                }
            ),
            400: OpenApiResponse(description="Validation error - invalid password"),
            401: OpenApiResponse(description="Unauthorized - authentication required")
        }
    )
    def post(self, request):
        serializer = ProfileDeleteSerializer(data=request.data, context={'user': request.user})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(data=serializer.data, status=status.HTTP_200_OK)


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Change User Password",
        description="Change the authenticated user's password. Requires current password for verification.",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'old_password': {'type': 'string', 'format': 'password', 'description': 'Current password'},
                    'new_password': {'type': 'string', 'format': 'password', 'description': 'New password'},
                    'new_password_confirm': {'type': 'string', 'format': 'password', 'description': 'New password confirmation'},
                },
                'required': ['old_password', 'new_password', 'new_password_confirm']
            }
        },
        responses={
            200: OpenApiResponse(
                description="Password changed successfully",
                response={
                    'type': 'object',
                    'properties': {
                        'message': {'type': 'string', 'description': 'Success message'},
                    }
                }
            ),
            400: OpenApiResponse(description="Validation error - invalid current password, passwords don't match, or new password same as old"),
            401: OpenApiResponse(description="Unauthorized - authentication required")
        }
    )
    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={'user': request.user})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(data=serializer.data, status=status.HTTP_200_OK)
