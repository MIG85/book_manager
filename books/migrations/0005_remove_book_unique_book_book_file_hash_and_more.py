# Generated by Django 4.2.7 on 2025-03-05 10:37

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('books', '0004_book_last_scan_alter_book_series_number_and_more'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='book',
            name='unique_book',
        ),
        migrations.AddField(
            model_name='book',
            name='file_hash',
            field=models.CharField(blank=True, max_length=64, unique=True),
        ),
        migrations.AddIndex(
            model_name='book',
            index=models.Index(fields=['file_hash'], name='books_book_file_ha_17b6f4_idx'),
        ),
        migrations.AddConstraint(
            model_name='book',
            constraint=models.UniqueConstraint(fields=('file_hash',), name='unique_file_hash'),
        ),
    ]
