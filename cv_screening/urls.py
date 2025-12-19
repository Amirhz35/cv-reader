"""
URL configuration for cv_screening project.
"""

from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from cv_screening.metrics import get_metrics

urlpatterns = [
    path('admin/', admin.site.urls),

    # API endpoints from the app
    path('api/', include('app.urls')),

    # Metrics endpoint
    path('metrics/', lambda request: HttpResponse(get_metrics(), content_type='text/plain'), name='prometheus-metrics'),

    # API documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
