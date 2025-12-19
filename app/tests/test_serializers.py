"""
Unit tests for serializers.
"""

import pytest
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from app.serializers import UserSerializer, CVUploadSerializer, CVEvaluationRequestSerializer


class UserSerializerTest(TestCase):
    """Test User serializer."""

    def test_user_serializer_valid_data(self):
        """Test user serializer with valid data."""
        data = {
            'email': 'test@example.com',
            'first_name': 'John',
            'last_name': 'Doe',
            'password': 'password123',
            'password_confirm': 'password123'
        }

        serializer = UserSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data['email'], 'test@example.com')

    def test_user_serializer_password_mismatch(self):
        """Test user serializer with mismatched passwords."""
        data = {
            'email': 'test@example.com',
            'password': 'password123',
            'password_confirm': 'different'
        }

        serializer = UserSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('password', serializer.errors)


class CVUploadSerializerTest(TestCase):
    """Test CV upload serializer."""

    def test_cv_upload_serializer_valid_pdf(self):
        """Test CV upload serializer with valid PDF file."""
        pdf_file = SimpleUploadedFile(
            "test.pdf",
            b"fake pdf content",
            content_type="application/pdf"
        )

        data = {
            'file': pdf_file,
            'prompt': 'Looking for Python developer with Django experience'
        }

        serializer = CVUploadSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_cv_upload_serializer_invalid_file_type(self):
        """Test CV upload serializer with invalid file type."""
        txt_file = SimpleUploadedFile(
            "test.txt",
            b"fake text content",
            content_type="text/plain"
        )

        data = {
            'file': txt_file,
            'prompt': 'Looking for Python developer'
        }

        serializer = CVUploadSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('file', serializer.errors)

    def test_cv_upload_serializer_short_prompt(self):
        """Test CV upload serializer with too short prompt."""
        pdf_file = SimpleUploadedFile(
            "test.pdf",
            b"fake pdf content",
            content_type="application/pdf"
        )

        data = {
            'file': pdf_file,
            'prompt': 'Hi'  # Too short
        }

        serializer = CVUploadSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('prompt', serializer.errors)


class CVEvaluationRequestSerializerTest(TestCase):
    """Test CV evaluation request serializer."""

    def test_evaluation_serializer_with_data(self):
        """Test evaluation serializer with MongoDB data."""
        # Mock MongoDB document data
        data = {
            '_id': '507f1f77bcf86cd799439011',
            'user_id': '123',
            'cv_id': '456',
            'prompt': 'Looking for Python developer',
            'status': 'completed',
            'ai_response': {'score': 85.0},
            'score': 85.0,
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-01T00:00:00Z'
        }

        serializer = CVEvaluationRequestSerializer(data)
        self.assertTrue(serializer.is_valid())

        # Check that _id is converted to id
        result = serializer.to_representation(data)
        self.assertIn('id', result)
        self.assertEqual(result['id'], '507f1f77bcf86cd799439011')
