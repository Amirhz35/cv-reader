#!/bin/bash

# Wait for databases and services to be ready
echo "Waiting for databases and services to be ready..."
python manage.py wait_for_db

# Only run migrations and create superuser from the main Django app service
if [ "$CONTAINER_NAME" = "cv-screening-api" ]; then
    echo "Running database migrations..."
    # Tables already exist, skip migrations
    # python manage.py migrate --run-syncdb

    # Create MinIO bucket
    echo "Creating MinIO bucket..."
    python manage.py create_minio_bucket

    # Collect static files (if needed)
    # python manage.py collectstatic --noinput

    # Create superuser if it doesn't exist
    echo "Checking for superuser..."
    python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(is_superuser=True).exists():
    User.objects.create_superuser(
        username='admin',
        email='admin@example.com',
        password='admin123',
        first_name='Admin',
        last_name='User'
    )
    print('Superuser created: admin@example.com / admin123')
else:
    print('Superuser already exists')
"
else
    echo "Skipping migrations and superuser creation (running in $CONTAINER_NAME)"
fi

echo "Starting application..."
exec "$@"
