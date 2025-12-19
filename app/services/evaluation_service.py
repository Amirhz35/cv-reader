import logging
from typing import Optional, Dict, Any
from .cv_parser import CVParserService
from .ai_client import AIClient

logger = logging.getLogger(__name__)


class CVEvaluationService:
    def __init__(self, ai_client: AIClient):
        self.parser = CVParserService()
        self.ai_client = ai_client

    def evaluate_cv(self, cv_file_path: str, prompt: str) -> Dict[str, Any]:
        try:
            cv_text = self.parser.extract_text(cv_file_path)
            if not cv_text:
                return {
                    'error': 'Failed to extract text from CV',
                    'score': 0.0
                }

            result = self.ai_client.evaluate_cv(cv_text, prompt)
            return result

        except Exception as e:
            logger.error(f"Error evaluating CV: {e}")
            return {
                'error': str(e),
                'score': 0.0
            }
