import json
from django.test import TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch


class CVScreeningIntegrationTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)

    def test_complete_cv_evaluation_flow(self):
        pdf_file = SimpleUploadedFile(
            "test_cv.pdf",
            b"fake pdf content for testing",
            content_type="application/pdf"
        )

        upload_data = {
            'file': pdf_file,
            'prompt': 'Looking for a Python developer with Django experience'
        }

        # Mock the file operations
        with patch('app.views.os.makedirs'), \
             patch('app.views.open', create=True) as mock_file, \
             patch('app.models.CVUpload.create') as mock_cv_create, \
             patch('app.models.CVEvaluationRequest.create') as mock_eval_create, \
             patch('app.tasks.evaluate_cv_task.delay') as mock_task_delay:
            mock_cv_create.return_value = {
                '_id': 'cv123',
                'user_id': str(self.user.id),
                'original_filename': 'test_cv.pdf',
                'file_size': 1000,
                'mime_type': 'application/pdf',
                'storage_uri': '/media/cvs/test_cv.pdf'
            }

            mock_eval_create.return_value = {
                '_id': 'eval123',
                'user_id': str(self.user.id),
                'cv_id': 'cv123',
                'prompt': 'Looking for a Python developer with Django experience',
                'status': 'pending'
            }

            response = self.client.post('/api/cv-evaluations/', upload_data, format='multipart')

            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assertIn('id', response.data)
            self.assertEqual(response.data['status'], 'pending')
            mock_cv_create.assert_called_once()
            mock_eval_create.assert_called_once()
            mock_task_delay.assert_called_once_with('eval123')

    def test_evaluation_history_retrieval(self):

        with patch('app.views.CVEvaluationRequest.objects.filter') as mock_filter:
            mock_queryset = Mock()
            mock_queryset.order_by.return_value = [
                {
                    '_id': 'eval123',
                    'user_id': str(self.user.id),
                    'cv_id': 'cv123',
                    'prompt': 'Python developer position',
                    'status': 'completed',
                    'score': 85.0,
                    'ai_response': {'score': 85.0, 'rationale': 'Good match'},
                    'created_at': '2024-01-01T00:00:00Z',
                    'updated_at': '2024-01-01T00:00:00Z'
                }
            ]
            mock_filter.return_value.order_by.return_value = mock_queryset

            response = self.client.get('/api/cv-evaluations/')

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(response.data), 1)
            self.assertEqual(response.data[0]['status'], 'completed')
            self.assertEqual(response.data[0]['score'], 85.0)

    def test_evaluation_detail_retrieval(self):

        with patch('app.views.CVEvaluationRequest.objects.get') as mock_get, \
             patch('app.views.CVUpload.objects.get') as mock_cv_get:
            mock_evaluation = Mock()
            mock_evaluation.id = 'eval123'
            mock_evaluation.user_id = str(self.user.id)
            mock_evaluation.cv_id = 'cv123'
            mock_evaluation.prompt = 'Python developer position'
            mock_evaluation.status = CVEvaluationRequest.STATUS_COMPLETED
            mock_evaluation.score = 85.0
            mock_evaluation.ai_response = {'score': 85.0, 'rationale': 'Good match'}

            mock_cv = Mock()
            mock_cv.original_filename = 'test_cv.pdf'
            mock_cv.uploaded_at = '2024-01-01T00:00:00Z'

            mock_get.return_value = mock_evaluation
            mock_cv_get.return_value = mock_cv

            response = self.client.get('/api/cv-evaluations/eval123/')

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data['status'], 'completed')
            self.assertEqual(response.data['score'], 85.0)
            self.assertEqual(response.data['cv_filename'], 'test_cv.pdf')

    def test_health_check_endpoint(self):

        with patch('app.views.connection') as mock_mysql_conn, \
             patch('app.views.mongoengine') as mock_mongo, \
             patch('cv_screening.celery.app.control.inspect') as mock_inspect:
            mock_cursor = Mock()
            mock_mysql_conn.cursor.return_value.__enter__.return_value = mock_cursor
            mock_cursor.execute.return_value = None

            mock_db = Mock()
            mock_mongo.connection.get_db.return_value = mock_db
            mock_db.command.return_value = {'ok': 1}

            mock_active = {'worker1': []}
            mock_inspect.return_value.active.return_value = mock_active

            response = self.client.get('/api/health/')

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data['status'], 'healthy')
            self.assertIn('mysql', response.data['services'])
            self.assertIn('mongodb', response.data['services'])
            self.assertIn('celery', response.data['services'])
