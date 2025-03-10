from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from books.views import HomeView  # Добавляем новый импорт

urlpatterns = [
    path('admin/', admin.site.urls),
    path('books/', include('books.urls')),
    path('users/', include('users.urls')),
    path('', HomeView.as_view(), name='home'),  # Изменяем на HomeView
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)