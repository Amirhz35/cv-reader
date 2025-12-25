"""
Celery tasks for CV screening platform.
"""

import logging
import os
import tempfile
from bson import ObjectId
from celery import shared_task
import requests
from django.core.files.storage import default_storage
from .models import CVEvaluationRequest, CVUpload
from .services.evaluation_service import CVEvaluationService
from .services.ai_client import OpenRouterClient  # AI client for CV evaluation

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def evaluate_cv_task(self, evaluation_id):
    """
    Asynchronous task to evaluate a CV against a job prompt.

    Args:
        evaluation_id (str): ObjectId of the CVEvaluationRequest document
    """
    try:
        logger.info(f"Starting CV evaluation task for ID: {evaluation_id}")

        CVEvaluationRequest.objects(id=ObjectId(evaluation_id)).update_one(
            set__status=CVEvaluationRequest.STATUS_PROCESSING
        )

        evaluation = CVEvaluationRequest.objects.get(id=ObjectId(evaluation_id))

        cv_upload = CVUpload.objects.get(id=ObjectId(evaluation.cv_id))
        try:
            if cv_upload.storage_uri.startswith('http'):
                # Direct HTTP URL (legacy support)
                response = requests.get(cv_upload.storage_uri)
                response.raise_for_status()

                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                    temp_file.write(response.content)
                    temp_file_path = temp_file.name
            else:
                # S3/MinIO storage - download via storage API
                from django.core.files.storage import default_storage
                with default_storage.open(cv_upload.storage_uri, 'rb') as storage_file:
                    file_content = storage_file.read()

                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                    temp_file.write(file_content)
                    temp_file_path = temp_file.name
            # Initialize OpenRouter AI client
            ai_client = OpenRouterClient(model="google/gemini-2.5-flash-lite")
            evaluation_service = CVEvaluationService(ai_client)

            result = evaluation_service.evaluate_cv(
                cv_file_path=temp_file_path,
                prompt=evaluation.prompt
            )

        finally:
            if 'temp_file_path' in locals() and cv_upload.storage_uri.startswith('http'):
                try:
                    os.unlink(temp_file_path)
                except:
                    pass

        # Update evaluation with results
        if 'error' in result and result['error']:
            # If the result contains an error, mark as failed
            score = result['score'] if 'score' in result else None
            CVEvaluationRequest.objects(id=ObjectId(evaluation_id)).update_one(
                set__status=CVEvaluationRequest.STATUS_FAILED,
                set__ai_response=result,
                set__score=score,
                set__error_message=result['error']
            )
        else:
            # Successful evaluation - validate required fields
            if 'score' not in result:
                raise Exception("AI evaluation result missing 'score' field")
            
            CVEvaluationRequest.objects(id=ObjectId(evaluation_id)).update_one(
                set__status=CVEvaluationRequest.STATUS_COMPLETED,
                set__ai_response=result,
                set__score=result['score'],
                set__error_message=None  # Clear any previous error messages
            )

        logger.info(f"CV evaluation completed for ID: {evaluation_id}")
        return result

    except Exception as exc:
        logger.error(f"Error evaluating CV {evaluation_id}: {exc}")

        CVEvaluationRequest.objects(id=ObjectId(evaluation_id)).update_one(
            set__status=CVEvaluationRequest.STATUS_FAILED,
            set__error_message=str(exc)
        )

        if self.request.retries < self.max_retries:
            logger.info(f"Retrying CV evaluation task for ID: {evaluation_id}")
            raise self.retry(countdown=60 * (2 ** self.request.retries), exc=exc)

        return {'error': str(exc)}
