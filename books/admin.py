from django.contrib import admin
from .models import Book, Author, Series, Keyword

@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('title', 'lang', 'file_path')
    list_filter = ('lang', 'series')
    search_fields = ('title', 'authors__last_name')
    filter_horizontal = ('authors', 'keywords')

@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    search_fields = ('last_name', 'first_name')

@admin.register(Series)
class SeriesAdmin(admin.ModelAdmin):
    search_fields = ('title',)

@admin.register(Keyword)
class KeywordAdmin(admin.ModelAdmin):
    search_fields = ('name',)