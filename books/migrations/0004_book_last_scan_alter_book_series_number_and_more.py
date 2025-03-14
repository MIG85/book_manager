# Generated by Django 4.2.7 on 2025-03-05 09:23

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('books', '0003_alter_book_series_number'),
    ]

    operations = [
        migrations.AddField(
            model_name='book',
            name='last_scan',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='book',
            name='series_number',
            field=models.FloatField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(0)]),
        ),
        migrations.AddIndex(
            model_name='author',
            index=models.Index(fields=['last_name', 'first_name'], name='books_autho_last_na_7ca250_idx'),
        ),
        migrations.AddIndex(
            model_name='book',
            index=models.Index(fields=['title'], name='books_book_title_d3218d_idx'),
        ),
        migrations.AddIndex(
            model_name='book',
            index=models.Index(fields=['lang'], name='books_book_lang_99ab96_idx'),
        ),
        migrations.AddConstraint(
            model_name='author',
            constraint=models.UniqueConstraint(fields=('last_name', 'first_name', 'middle_name'), name='unique_author'),
        ),
        migrations.AddConstraint(
            model_name='book',
            constraint=models.UniqueConstraint(fields=('title', 'file_path'), name='unique_book'),
        ),
    ]
