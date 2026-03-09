from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from finance.views import dashboard, upload_file, export_transactions, register, edit_receipt_item, get_ai_advice

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', dashboard, name='dashboard'),
    path('upload/', upload_file, name='upload'),
    path('export/', export_transactions, name='export'),
    path('login/', auth_views.LoginView.as_view(template_name='finance/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('register/', register, name='register'),
    path('edit-item/<int:item_id>/', edit_receipt_item, name='edit_receipt_item'),
    path('ai-advice/', get_ai_advice, name='ai_advice'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

