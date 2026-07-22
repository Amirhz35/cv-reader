import pytest
import time
import json
import os
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase
from app.services.ai_client import NvidiaClient, DEFAULT_NVIDIA_MODEL
from app.services.cv_parser import CVParserService
from app.services.evaluation_service import CVEvaluationService
from app.services.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenException,
    CircuitBreakerState,
    ai_circuit_breaker,
)


def _mock_completion(content, total_tokens=150):
    completion = Mock()
    completion.choices = [Mock(message=Mock(content=content))]
    completion.usage.model_dump.return_value = {'total_tokens': total_tokens}
    return completion


class NvidiaClientTest(TestCase):
    def setUp(self):
        self.api_key = "test-api-key"
        # Set environment variable for testing
        os.environ['NVIDIA_API_KEY'] = self.api_key
        os.environ.pop('NVIDIA_MODEL', None)
        # Reset shared circuit breaker state so failure tests don't leak
        ai_circuit_breaker._state = CircuitBreakerState.CLOSED
        ai_circuit_breaker._failure_count = 0
        ai_circuit_breaker._success_count = 0
        with patch('app.services.ai_client.OpenAI'):
            self.client = NvidiaClient()

    def tearDown(self):
        # Clean up environment variable
        if 'NVIDIA_API_KEY' in os.environ:
            del os.environ['NVIDIA_API_KEY']

    def test_evaluate_cv_success_json_response(self):
        # Mock successful API response with JSON
        content = json.dumps({
            'score': 85.0,
            'rationale': 'Excellent match for the position',
            'matches': ['Python', 'Django'],
            'gaps': ['No cloud experience']
        })
        mock_create = self.client.client.chat.completions.create
        mock_create.return_value = _mock_completion(content)

        result = self.client.evaluate_cv("Sample CV content", "Python developer position")

        self.assertEqual(result['score'], 85.0)
        self.assertEqual(result['rationale'], 'Excellent match for the position')
        self.assertEqual(result['matches'], ['Python', 'Django'])
        self.assertEqual(result['gaps'], ['No cloud experience'])

        # Verify API call was made correctly
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs

        self.assertEqual(call_kwargs['model'], DEFAULT_NVIDIA_MODEL)
        self.assertEqual(len(call_kwargs['messages']), 2)
        self.assertEqual(call_kwargs['messages'][0]['role'], 'system')
        self.assertEqual(call_kwargs['messages'][1]['role'], 'user')

    def test_evaluate_cv_non_json_response(self):
        # API response with plain text (not JSON) should raise
        content = 'This is a plain text response without JSON structure. The candidate has good skills.'
        self.client.client.chat.completions.create.return_value = _mock_completion(content)

        with self.assertRaises(Exception) as ctx:
            self.client.evaluate_cv("Sample CV", "Developer position")

        self.assertIn('AI evaluation failed', str(ctx.exception))

    def test_evaluate_cv_api_error(self):
        # API errors should surface as exceptions
        self.client.client.chat.completions.create.side_effect = Exception("Request timed out")

        with self.assertRaises(Exception) as ctx:
            self.client.evaluate_cv("Sample CV", "Developer position")

        self.assertIn('AI evaluation failed', str(ctx.exception))

    def test_missing_api_key_raises(self):
        del os.environ['NVIDIA_API_KEY']
        with self.assertRaises(ValueError):
            NvidiaClient()

    def test_extract_keywords(self):
        # Test the keyword extraction helper method
        with patch('app.services.ai_client.OpenAI'):
            client = NvidiaClient(api_key="test")

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
