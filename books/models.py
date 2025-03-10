from django.db import models
from django.core.validators import MinValueValidator
from django.urls import reverse

class Author(models.Model):
    first_name = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        verbose_name="Имя"
    )
    last_name = models.CharField(
        max_length=100,
        db_index=True,
        verbose_name="Фамилия"
    )
    middle_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Отчество"
    )

    class Meta:
        verbose_name = "Автор"
        verbose_name_plural = "Авторы"
        ordering = ['last_name', 'first_name']
        constraints = [
            models.UniqueConstraint(
                fields=['last_name', 'first_name', 'middle_name'],
                name='unique_author'
            )
        ]

    def __str__(self):
        parts = filter(None, [self.last_name, self.first_name, self.middle_name])
        return ' '.join(parts) or "Неизвестный автор"

class Series(models.Model):
    title = models.CharField(
        max_length=500,
        db_index=True,
        verbose_name="Название серии"
    )
    description = models.TextField(
        blank=True,
        verbose_name="Описание серии"
    )

    class Meta:
        verbose_name = "Серия"
        verbose_name_plural = "Серии"
        ordering = ['title']

    def __str__(self):
        return self.title

class Keyword(models.Model):
    name = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        verbose_name="Ключевое слово"
    )

    class Meta:
        verbose_name = "Ключевое слово"
        verbose_name_plural = "Ключевые слова"
        ordering = ['name']

    def __str__(self):
        return self.name

class Book(models.Model):
    title = models.CharField(
        max_length=500,
        db_index=True,
        verbose_name="Название"
    )
    authors = models.ManyToManyField(
        Author,
        related_name='books',
        verbose_name="Авторы"
    )
    series = models.ForeignKey(
        Series,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='books',
        verbose_name="Серия"
    )
    series_number = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name="Номер в серии"
    )
    description = models.TextField(
        blank=True,
        verbose_name="Описание"
    )
    keywords = models.ManyToManyField(
        Keyword,
        blank=True,
        related_name='books',
        verbose_name="Ключевые слова"
    )
    lang = models.CharField(
        max_length=10,
        verbose_name="Язык",
        default='ru'
    )
    cover = models.ImageField(
        upload_to='covers/',
        null=True,
        blank=True,
        verbose_name="Обложка"
    )
    file_path = models.CharField(
        max_length=1000,
        verbose_name="Путь к файлу"
    )
    file_hash = models.CharField(
        max_length=64,
        unique=True,
        verbose_name="Хеш файла"
    )
    created = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )
    modified = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата изменения"
    )
    file_archive = models.CharField(
        max_length=1000, 
        verbose_name="Путь к архиву",
        blank=True,
        null=True
    )
    file_in_archive = models.CharField(
        max_length=1000, 
        verbose_name="Путь внутри архива",
        blank=True,
        null=True
    )

    class Meta:
        verbose_name = "Книга"
        verbose_name_plural = "Книги"
        ordering = ['-created']
        indexes = [
            models.Index(fields=['title'], name='title_idx'),
            models.Index(fields=['lang'], name='lang_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['file_hash'],
                name='unique_file_hash'
            )
        ]

    def __str__(self):
        return f"{self.title} ({self.lang})"

    def get_absolute_url(self):
        return reverse('book-detail', kwargs={'pk': self.pk})
