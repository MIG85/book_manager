# Generated by Django 4.2.7 on 2025-03-05 11:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('books', '0005_remove_book_unique_book_book_file_hash_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='book',
            name='file_hash',
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
    ]
