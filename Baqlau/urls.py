from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from finance.views import dashboard, upload_file

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', dashboard, name='dashboard'),      # Главная
    path('upload/', upload_file, name='upload'), # Страница загрузки
]

# Важно для отображения загруженных картинок в режиме отладки
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)