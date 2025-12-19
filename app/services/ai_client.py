from abc import ABC, abstractmethod
import logging
import structlog
import time
import json
import os
import requests
from typing import Dict, Any, Optional
from .circuit_breaker import ai_circuit_breaker, CircuitBreakerOpenException

logger = structlog.get_logger()


class AIClient(ABC):
    @abstractmethod
    def evaluate_cv(self, cv_text: str, prompt: str) -> dict:
        pass




class OpenRouterClient(AIClient):
    def __init__(self, api_key: Optional[str] = None, model: str = "z-ai/glm-4.5-air:free", base_url: str = "https://openrouter.ai/api/v1"):
        self.api_key = api_key or os.getenv('OPENROUTER_API_KEY')
        if not self.api_key:
            raise ValueError("OpenRouter API key not provided. Set OPENROUTER_API_KEY environment variable or pass api_key parameter.")
        self.model = model
        self.base_url = base_url
        self.timeout = 60  # 60 seconds timeout

    def evaluate_cv(self, cv_text: str, prompt: str) -> dict:
        def _openrouter_evaluation():
            logger.info("OpenRouter AI evaluation started",
                       cv_text_length=len(cv_text),
                       prompt_length=len(prompt),
                       model=self.model)

            try:
                # Prepare the evaluation prompt
                system_prompt = """You are an expert HR professional evaluating CVs for job positions.
Analyze the provided CV text against the job requirements and provide a detailed evaluation.

Return your response as a JSON object with the following structure:
{
  "score": <number between 0-100>,
  "rationale": "<detailed explanation of the evaluation>",
  "matches": ["<skill1>", "<skill2>", ...],
  "gaps": ["<missing requirement1>", "<missing requirement2>", ...]
}

Be specific and provide actionable feedback."""

                user_message = f"""Job Requirements: {prompt}

CV Content:
{cv_text[:8000]}  # Limit CV text to avoid token limits

Please evaluate this CV against the job requirements."""

                # Prepare the request payload
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 2000,
                    "stream": False
                }

                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://cv-screening-app.com",  # Optional
                    "X-Title": "CV Screening API"  # Optional
                }

                # Make the API call
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=self.timeout
                )

                response.raise_for_status()

                result = response.json()

                # Extract the AI response
                ai_response = result['choices'][0]['message']['content'].strip()

                logger.info("OpenRouter AI response received",
                           response_length=len(ai_response),
                           usage=result.get('usage', {}))

                # Try to parse the JSON response
                try:
                    parsed_response = json.loads(ai_response)
                    # Validate required fields
                    if 'score' not in parsed_response:
                        parsed_response['score'] = 50.0
                    if 'rationale' not in parsed_response:
                        parsed_response['rationale'] = ai_response[:500]
                    if 'matches' not in parsed_response:
                        parsed_response['matches'] = []
                    if 'gaps' not in parsed_response:
                        parsed_response['gaps'] = []

                    logger.info("OpenRouter AI evaluation completed",
                               score=parsed_response['score'])
                    return parsed_response

                except json.JSONDecodeError:
                    # If AI doesn't return valid JSON, create a structured response
                    logger.warning("OpenRouter AI returned non-JSON response, creating fallback")
                    return {
                        'score': 60.0,
                        'rationale': ai_response[:1000],
                        'matches': self._extract_keywords(ai_response, ['experience', 'skills', 'knowledge']),
                        'gaps': ['Unable to parse structured evaluation']
                    }

            except requests.exceptions.Timeout:
                logger.error("OpenRouter API request timed out")
                raise Exception("AI service timeout")

            except requests.exceptions.RequestException as e:
                logger.error("OpenRouter API request failed", error=str(e))
                raise Exception(f"AI service error: {str(e)}")

            except Exception as e:
                logger.error("Unexpected error in OpenRouter evaluation", error=str(e))
                raise Exception(f"AI evaluation failed: {str(e)}")

        try:
            return ai_circuit_breaker.call(_openrouter_evaluation)
        except CircuitBreakerOpenException:
            logger.warning("OpenRouter service circuit breaker is open, returning fallback result")
            return {
                'score': 50.0,
                'rationale': 'Service temporarily unavailable - circuit breaker activated',
                'matches': [],
                'gaps': ['Unable to evaluate due to service issues'],
                'error': 'Circuit breaker open'
            }

    def _extract_keywords(self, text: str, keywords: list) -> list:
        """Simple keyword extraction for fallback responses"""
        text_lower = text.lower()
        found_keywords = []
        for keyword in keywords:
            if keyword.lower() in text_lower:
                found_keywords.append(keyword.capitalize())
        return found_keywords[:5]  # Limit to 5 keywords

