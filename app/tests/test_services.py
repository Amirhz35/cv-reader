import pytest
import time
import json
import os
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase
from app.services.ai_client import OpenRouterClient
from app.services.cv_parser import CVParserService
from app.services.evaluation_service import CVEvaluationService
from app.services.circuit_breaker import CircuitBreaker, CircuitBreakerOpenException


class OpenRouterClientTest(TestCase):
    def setUp(self):
        self.api_key = "test-api-key"
        # Set environment variable for testing
        os.environ['OPENROUTER_API_KEY'] = self.api_key
        self.client = OpenRouterClient()

    def tearDown(self):
        # Clean up environment variable
        if 'OPENROUTER_API_KEY' in os.environ:
            del os.environ['OPENROUTER_API_KEY']

    @patch('app.services.ai_client.requests.post')
    def test_evaluate_cv_success_json_response(self, mock_post):
        # Mock successful API response with JSON
        mock_response = Mock()
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': json.dumps({
                        'score': 85.0,
                        'rationale': 'Excellent match for the position',
                        'matches': ['Python', 'Django'],
                        'gaps': ['No cloud experience']
                    })
                }
            }],
            'usage': {'total_tokens': 150}
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = self.client.evaluate_cv("Sample CV content", "Python developer position")

        self.assertEqual(result['score'], 85.0)
        self.assertEqual(result['rationale'], 'Excellent match for the position')
        self.assertEqual(result['matches'], ['Python', 'Django'])
        self.assertEqual(result['gaps'], ['No cloud experience'])

        # Verify API call was made correctly
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        self.assertEqual(call_args[0][0], 'https://openrouter.ai/api/v1/chat/completions')
        request_data = call_args[1]['json']

        self.assertEqual(request_data['model'], 'qwen/qwen3-coder:free')
        self.assertEqual(len(request_data['messages']), 2)
        self.assertIn('system', request_data['messages'][0]['role'])
        self.assertIn('user', request_data['messages'][1]['role'])

    @patch('app.services.ai_client.requests.post')
    def test_evaluate_cv_non_json_response(self, mock_post):
        # Mock API response with plain text (not JSON)
        mock_response = Mock()
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': 'This is a plain text response without JSON structure. The candidate has good skills.'
                }
            }]
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = self.client.evaluate_cv("Sample CV", "Developer position")

        # Should create fallback structure
        self.assertEqual(result['score'], 60.0)
        self.assertIn('plain text response', result['rationale'])
        self.assertEqual(result['gaps'], ['Unable to parse structured evaluation'])

    @patch('app.services.ai_client.requests.post')
    def test_evaluate_cv_api_timeout(self, mock_post):
        # Mock timeout error
        mock_post.side_effect = TimeoutError("Request timed out")

        result = self.client.evaluate_cv("Sample CV", "Developer position")

        # Should return circuit breaker fallback
        self.assertEqual(result['score'], 50.0)
        self.assertIn('Service temporarily unavailable', result['rationale'])
        self.assertIn('Circuit breaker open', result.get('error', ''))

    def test_extract_keywords(self):
        # Test the keyword extraction helper method
        client = OpenRouterClient(api_key="test")

        text = "The candidate has experience in Python and JavaScript development."
        keywords = ['experience', 'python', 'javascript']

        result = client._extract_keywords(text, keywords)
        self.assertIn('Experience', result)
        self.assertIn('Python', result)
        self.assertIn('Javascript', result)


class CVParserServiceTest(TestCase):
    """Test CV parser service."""

    @patch('app.services.cv_parser.PDFMinerParser.extract_text')
    def test_extract_text_pdfminer_success(self, mock_pdfminer):
        mock_pdfminer.return_value = "Extracted text from PDF"

        service = CVParserService()
        result = service.extract_text("/path/to/file.pdf")

        self.assertEqual(result, "Extracted text from PDF")
        mock_pdfminer.assert_called_once()

    @patch('app.services.cv_parser.PDFMinerParser.extract_text')
    @patch('app.services.cv_parser.PyMuPDFParser.extract_text')
    def test_extract_text_fallback_to_pymupdf(self, mock_pymupdf, mock_pdfminer):
        mock_pdfminer.return_value = None
        mock_pymupdf.return_value = "Extracted text from PyMuPDF"

        service = CVParserService()
        result = service.extract_text("/path/to/file.pdf")

        self.assertEqual(result, "Extracted text from PyMuPDF")
        mock_pdfminer.assert_called_once()
        mock_pymupdf.assert_called_once()


class CVEvaluationServiceTest(TestCase):
    def setUp(self):
        self.mock_ai_client = Mock()
        self.service = CVEvaluationService(self.mock_ai_client)

    @patch('app.services.evaluation_service.CVParserService.extract_text')
    def test_evaluate_cv_success(self, mock_extract):
        mock_extract.return_value = "Sample CV content"
        self.mock_ai_client.evaluate_cv.return_value = {
            'score': 85.0,
            'rationale': 'Good match',
            'matches': ['Python'],
            'gaps': []
        }

        result = self.service.evaluate_cv("/path/to/cv.pdf", "Python developer")

        self.assertEqual(result['score'], 85.0)
        mock_extract.assert_called_once_with("/path/to/cv.pdf")
        self.mock_ai_client.evaluate_cv.assert_called_once()

    @patch('app.services.evaluation_service.CVParserService.extract_text')
    def test_evaluate_cv_parsing_failed(self, mock_extract):
        mock_extract.return_value = None

        result = self.service.evaluate_cv("/path/to/cv.pdf", "Python developer")

        self.assertIn('error', result)
        self.assertIn('Failed to extract text', result['error'])


class CircuitBreakerTest(TestCase):
    def setUp(self):
        self.cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1)

    def test_circuit_breaker_closed_state(self):
        def success_func():
            return "success"

        result = self.cb.call(success_func)
        self.assertEqual(result, "success")
        self.assertEqual(self.cb.state.name, "CLOSED")

    def test_circuit_breaker_opens_after_failures(self):
        def failure_func():
            raise Exception("Service error")

        with self.assertRaises(Exception):
            self.cb.call(failure_func)

        with self.assertRaises(Exception):
            self.cb.call(failure_func)

        self.assertEqual(self.cb.state.name, "OPEN")
        with self.assertRaises(CircuitBreakerOpenException):
            self.cb.call(lambda: "should not execute")

    def test_circuit_breaker_half_open_recovery(self):
        def failure_func():
            raise Exception("Service error")

        def success_func():
            return "recovered"

        for _ in range(2):
            with self.assertRaises(Exception):
                self.cb.call(failure_func)

        self.assertEqual(self.cb.state.name, "OPEN")

        time.sleep(1.1)

        result = self.cb.call(success_func)
        self.assertEqual(result, "recovered")

        self.assertEqual(self.cb.state.name, "CLOSED")
