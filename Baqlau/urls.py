from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from finance.views import dashboard, upload_file
from finance.views import dashboard, upload_file, export_transactions  # <-- Импортируем новую функцию

urlpatterns = [
    path('', dashboard, name='dashboard'),
    path('upload/', upload_file, name='upload'),
    path('export/', export_transactions, name='export'),
]

# Важно для отображения загруженных картинок в режиме отладки
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
