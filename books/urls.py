from django.urls import path
from . import views  # Добавляем импорт views

app_name = 'books'

urlpatterns = [
    path('', views.BookListView.as_view(), name='book-list'),
    path('<int:pk>/', views.BookDetailView.as_view(), name='book-detail'),
    path('search/', views.book_search, name='book-search'),
    path('filter/<str:model_type>/<str:letter>/', views.alpha_filter, name='alpha-filter'),
    path('download/<int:pk>/', views.DownloadBookView.as_view(), name='download-book'),
]
