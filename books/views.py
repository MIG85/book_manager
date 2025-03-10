from django.shortcuts import render, get_object_or_404
from django.views import View
from django.http import FileResponse, Http404
from django.core.exceptions import PermissionDenied
from django.conf import settings
from django.db.models import Q
from django.core.paginator import Paginator
import zipfile
import rarfile
import os
import logging
from patoolib import extract_archive
import tempfile
from .models import Book, Author, Series, Keyword

logger = logging.getLogger(__name__)

class BookListView(View):
    def get(self, request):
        books = Book.objects.all()
        return render(request, 'books/book_list.html', {'books': books})

class BookDetailView(View):
    def get(self, request, pk):
        book = get_object_or_404(
            Book.objects.prefetch_related('authors', 'keywords'),
            pk=pk
        )
        return render(request, 'books/book_detail.html', {'book': book})

class DownloadBookView(View):
    def get(self, request, pk):
        book = get_object_or_404(Book, pk=pk)
        
        if not book.file_archive:
            return self.serve_single_file(book)
            
        archive_path = os.path.join(settings.LIBRARY_ROOT, book.file_archive)
        ext = os.path.splitext(archive_path)[1].lower()

        try:
            if ext == '.zip':
                return self.handle_zip(archive_path, book.file_in_archive)
            elif ext == '.rar':
                return self.handle_rar(archive_path, book.file_in_archive)
            else:
                raise Http404("Unsupported archive format")
                
        except Exception as e:
            logger.error(f"Extraction error: {str(e)}")
            raise Http404("File not found in archive")

    def handle_zip(self, archive_path, target_file):
        with zipfile.ZipFile(archive_path, 'r') as zf:
            if target_file not in zf.namelist():
                raise Http404("File not in archive")
            
            file_info = zf.getinfo(target_file)
            response = FileResponse(
                zf.open(file_info),
                content_type='application/octet-stream'
            )
            response['Content-Disposition'] = f'attachment; filename="{os.path.basename(target_file)}"'
            return response

    def handle_rar(self, archive_path, target_file):
        if not rarfile.is_rarfile(archive_path):
            raise Http404("Invalid RAR archive")
            
        with rarfile.RarFile(archive_path, 'r') as rf:
            if target_file not in rf.namelist():
                raise Http404("File not in archive")
                
            file_info = rf.getinfo(target_file)
            response = FileResponse(
                rf.open(file_info),
                content_type='application/octet-stream'
            )
            response['Content-Disposition'] = f'attachment; filename="{os.path.basename(target_file)}"'
            return response
        
class HomeView(View):
    def get(self, request):
        return render(request, 'main.html')  # Отдельный шаблон для главной
        
def book_search(request):
    query = request.GET.get('q', '')
    books = Book.objects.all()
    
    if query:
        books = books.filter(
            Q(title__icontains=query) |
            Q(authors__last_name__icontains=query) |
            Q(authors__first_name__icontains=query) |
            Q(series__title__icontains=query) |
            Q(keywords__name__icontains=query)
        ).distinct()

    paginator = Paginator(books, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'books/search_results.html', {
        'page_obj': page_obj,
        'query': query
    })

def alpha_filter(request, model_type, letter):
    models_map = {
        'author': (Author, 'last_name'),
        'title': (Book, 'title'),
        'series': (Series, 'title'),  # Исправлено с 'name' на 'title'
        'genre': (Keyword, 'name')
    }
    
    if model_type not in models_map:
        raise Http404("Invalid filter type")

    Model, field = models_map[model_type]
    
    items = Model.objects.filter(
        **{f"{field}__istartswith": letter}
    ).order_by(field)
    
    return render(request, 'books/alpha_filter.html', {
        'items': items,
        'model_type': model_type,
        'letter': letter,
        'field_name': field
    })
