from abc import ABC, abstractmethod
import logging
import structlog
import time
import json
import os
import re
import requests
from typing import Dict, Any, Optional
from .circuit_breaker import ai_circuit_breaker, CircuitBreakerOpenException

logger = structlog.get_logger()


class AIClient(ABC):
    @abstractmethod
    def evaluate_cv(self, cv_text: str, prompt: str) -> dict:
        pass




class OpenRouterClient(AIClient):
    def __init__(self, api_key: Optional[str] = None, model: str = "google/gemini-2.5-flash-lite", base_url: str = "https://openrouter.ai/api/v1"):
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

                usage = result.get('usage') if 'usage' in result else None
                logger.info("OpenRouter AI response received",
                           response_length=len(ai_response),
                           usage=usage)

                # Try to parse the JSON response
                parsed_response = self._parse_ai_response(ai_response)
                
                if not parsed_response:
                    raise Exception("AI returned invalid JSON response that could not be parsed")
                
                # Validate required fields - raise error if missing
                if 'score' not in parsed_response:
                    raise Exception("AI response missing required 'score' field")
                if 'rationale' not in parsed_response:
                    raise Exception("AI response missing required 'rationale' field")
                if 'matches' not in parsed_response:
                    raise Exception("AI response missing required 'matches' field")
                if 'gaps' not in parsed_response:
                    raise Exception("AI response missing required 'gaps' field")

                # Ensure score is a float
                try:
                    score_value = parsed_response['score']
                    parsed_response['score'] = float(score_value)
                    logger.info("Score extracted successfully", 
                              original_score=score_value, 
                              parsed_score=parsed_response['score'])
                except (ValueError, TypeError) as e:
                    raise Exception(f"AI response 'score' field is not a valid number: {score_value}")

                logger.info("OpenRouter AI evaluation completed",
                           score=parsed_response['score'],
                           matches_count=len(parsed_response['matches']),
                           gaps_count=len(parsed_response['gaps']))
                return parsed_response

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
            logger.error("OpenRouter service circuit breaker is open")
            raise Exception("AI service temporarily unavailable - circuit breaker activated")

    def _parse_ai_response(self, ai_response: str) -> Optional[Dict[str, Any]]:
        """
        Parse AI response, handling markdown code blocks and nested JSON.
        
        Args:
            ai_response: Raw AI response string
            
        Returns:
            Parsed JSON dict or None if parsing fails
        """
        # First, try to extract JSON from markdown code blocks
        # Pattern: ```json\n{...}\n```
        json_block_pattern = r'```(?:json)?\s*\n(.*?)\n```'
        json_match = re.search(json_block_pattern, ai_response, re.DOTALL)
        
        if json_match:
            json_str = json_match.group(1).strip()
        else:
            # Try to find JSON object in the response
            # Look for { ... } pattern
            json_object_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
            json_match = re.search(json_object_pattern, ai_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0).strip()
            else:
                json_str = ai_response.strip()
        
        # Try to parse the JSON
        try:
            parsed = json.loads(json_str)
            
            # Handle nested JSON in rationale field (if present)
            # Sometimes AI returns the actual evaluation JSON nested inside rationale
            if isinstance(parsed, dict) and 'rationale' in parsed:
                rationale = parsed['rationale']
                # Check if rationale contains nested JSON in markdown code block
                if isinstance(rationale, str) and ('```json' in rationale or '```' in rationale):
                    # Try to extract nested JSON from rationale
                    nested_match = re.search(json_block_pattern, rationale, re.DOTALL)
                    if nested_match:
                        try:
                            nested_json_str = nested_match.group(1).strip()
                            nested_json = json.loads(nested_json_str)
                            # If nested JSON has score and matches, use it (it's likely the actual response)
                            if 'score' in nested_json and 'matches' in nested_json:
                                logger.info("Found nested JSON in rationale with score and matches, using nested response",
                                          nested_score=nested_json['score'])
                                parsed = nested_json
                            elif 'score' in nested_json:
                                # Use nested score but keep other fields from outer response
                                parsed['score'] = nested_json['score']
                                if 'matches' in nested_json:
                                    parsed['matches'] = nested_json['matches']
                                if 'gaps' in nested_json:
                                    parsed['gaps'] = nested_json['gaps']
                                logger.info("Merged nested JSON data from rationale",
                                          score=parsed['score'])
                        except json.JSONDecodeError as e:
                            logger.warning(f"Failed to parse nested JSON in rationale: {e}")
                            pass
            
            return parsed
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            # Try one more time with cleaned string (remove markdown artifacts)
            try:
                # Remove common markdown artifacts
                cleaned = json_str.replace('```json', '').replace('```', '').strip()
                # Remove leading/trailing non-JSON text
                start_idx = cleaned.find('{')
                end_idx = cleaned.rfind('}')
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    cleaned = cleaned[start_idx:end_idx + 1]
                    return json.loads(cleaned)
            except (json.JSONDecodeError, ValueError):
                pass
            
            return None

    def _extract_keywords(self, text: str, keywords: list) -> list:
        """Simple keyword extraction from text"""
        text_lower = text.lower()
        found_keywords = []
        for keyword in keywords:
            if keyword.lower() in text_lower:
                found_keywords.append(keyword.capitalize())
        return found_keywords[:5]  # Limit to 5 keywords

