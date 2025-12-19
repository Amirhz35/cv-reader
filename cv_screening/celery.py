"""
Celery configuration for CV screening platform.
"""

import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cv_screening.settings')

app = Celery('cv_screening')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')


# Optional: Add periodic tasks
app.conf.beat_schedule = {
    # Add any periodic tasks here if needed
    # 'cleanup-old-files': {
    #     'task': 'app.tasks.cleanup_old_files',
    #     'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
    # },
}
