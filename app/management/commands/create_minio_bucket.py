"""
Django management command to create MinIO bucket.
"""

import os
import time
from django.core.management.base import BaseCommand
from django.conf import settings
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError


class Command(BaseCommand):
    help = 'Create MinIO bucket if it does not exist'

    def handle(self, *args, **options):
        bucket_name = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', 'cv-files')
        endpoint_url = getattr(settings, 'AWS_S3_ENDPOINT_URL', 'http://minio:9000')
        access_key = getattr(settings, 'AWS_ACCESS_KEY_ID', 'admin')
        secret_key = getattr(settings, 'AWS_SECRET_ACCESS_KEY', 'admin123')
        use_ssl = getattr(settings, 'AWS_S3_USE_SSL', False)

        # Wait for MinIO to be ready
        max_retries = 30
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                self.stdout.write(f'Attempting to connect to MinIO (attempt {attempt + 1}/{max_retries})...')

                # Create S3 client for MinIO
                s3_client = boto3.client(
                    's3',
                    endpoint_url=endpoint_url,
                    aws_access_key_id=access_key,
                    aws_secret_access_key=secret_key,
                    config=Config(signature_version='s3v4'),
                    verify=use_ssl
                )

                # Test connection by listing buckets
                s3_client.list_buckets()
                self.stdout.write(self.style.SUCCESS('Successfully connected to MinIO'))
                break

            except Exception as e:
                if attempt == max_retries - 1:
                    self.stderr.write(
                        self.style.ERROR(f'Failed to connect to MinIO after {max_retries} attempts: {e}')
                    )
                    return
                self.stdout.write(f'MinIO not ready yet: {e}. Retrying in {retry_delay} seconds...')
                time.sleep(retry_delay)
                continue

        try:
            # Check if bucket exists
            try:
                s3_client.head_bucket(Bucket=bucket_name)
                self.stdout.write(
                    self.style.SUCCESS(f'Bucket "{bucket_name}" already exists')
                )
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code == '404' or error_code == 'NoSuchBucket':
                    # Create bucket if it doesn't exist
                    s3_client.create_bucket(Bucket=bucket_name)
                    self.stdout.write(
                        self.style.SUCCESS(f'Successfully created bucket "{bucket_name}"')
                    )
                else:
                    raise e

            # Set bucket policy for public read access (optional)
            # This allows direct access to files via URLs
            bucket_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"AWS": "*"},
                        "Action": ["s3:GetObject"],
                        "Resource": [f"arn:aws:s3:::{bucket_name}/*"]
                    }
                ]
            }

            try:
                s3_client.put_bucket_policy(
                    Bucket=bucket_name,
                    Policy=str(bucket_policy).replace("'", '"')
                )
                self.stdout.write(
                    self.style.SUCCESS(f'Set public read policy for bucket "{bucket_name}"')
                )
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f'Could not set bucket policy (this is usually OK): {e}')
                )

        except Exception as e:
            self.stderr.write(
                self.style.ERROR(f'Failed to create/configure MinIO bucket: {e}')
            )
            return
