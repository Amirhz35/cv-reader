"""
ASGI config for cv_screening project.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cv_screening.settings')

application = get_asgi_application()
