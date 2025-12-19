"""
Models for CV screening platform.
"""

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
import mongoengine


class CustomUser(AbstractUser):
    email = models.EmailField(max_length=150, blank=True, null=True)
    first_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    date_joined = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(auto_now=True)

    groups = models.ManyToManyField(
        'auth.Group',
        related_name='customuser_set',
        blank=True
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='customuser_set',
        blank=True
    )

    def set_password(self, raw_password):
        super().set_password(raw_password)

    def check_password(self, raw_password):
        return super().check_password(raw_password)

    @classmethod
    def create_user(cls, username, password, email=None, first_name=None, last_name=None):
        user = cls(username=username)
        if email:
            user.email = email
        if first_name:
            user.first_name = first_name
        if last_name:
            user.last_name = last_name
        user.set_password(password)
        user.save()
        return user


class CVUpload(mongoengine.Document):
    user_id = mongoengine.StringField(required=True)
    original_filename = mongoengine.StringField(required=True, max_length=255)
    file_size = mongoengine.IntField(required=True)
    mime_type = mongoengine.StringField(required=True, max_length=100)
    storage_uri = mongoengine.StringField(required=True, max_length=500)
    checksum = mongoengine.StringField(max_length=128)
    uploaded_at = mongoengine.DateTimeField(default=timezone.now)

    meta = {
        'collection': 'cv_uploads',
        'indexes': [
            'user_id',
            '-uploaded_at'
        ]
    }

    def __str__(self):
        return f"CV: {self.original_filename}"


class CVEvaluationRequest(mongoengine.Document):
    STATUS_PENDING = 0
    STATUS_PROCESSING = 1
    STATUS_COMPLETED = 2
    STATUS_FAILED = 3

    STATUS_CHOICES = [
        (STATUS_PENDING, 'pending'),
        (STATUS_PROCESSING, 'processing'),
        (STATUS_COMPLETED, 'completed'),
        (STATUS_FAILED, 'failed')
    ]

    user_id = mongoengine.StringField(required=True)
    cv_id = mongoengine.StringField(required=True)
    prompt = mongoengine.StringField(required=True)
    status = mongoengine.IntField(
        required=True,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING
    )
    ai_response = mongoengine.DictField()
    score = mongoengine.FloatField(min_value=0.0, max_value=100.0)
    error_message = mongoengine.StringField()
    created_at = mongoengine.DateTimeField(default=timezone.now)
    updated_at = mongoengine.DateTimeField(default=timezone.now)

    meta = {
        'collection': 'cv_evaluation_requests',
        'indexes': [
            'user_id',
            'cv_id',
            '-created_at'
        ]
    }

    def __str__(self):
        return f"Evaluation {self.id} - {self.status}"
