import os
import zipfile
import rarfile
import magic
import tempfile
import hashlib
import logging
import chardet
import redis
import base64
import binascii
from lxml import etree
from django.core.files import File
from django.conf import settings
from books.models import Book, Author, Series, Keyword

logger = logging.getLogger(__name__)
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB
)

SUPPORTED_ARCHIVE_FORMATS = {
    'application/zip': 'zip',
    'application/x-rar-compressed': 'rar'
}

SUPPORTED_BOOK_FORMATS = {
    'application/x-fictionbook': 'fb2',
    'application/epub+zip': 'epub',
    'text/xml': 'fb2'
}

def acquire_lock(file_path, timeout=3600):
    lock_key = f"file_lock:{file_path}"
    return redis_client.set(lock_key, 1, nx=True, ex=timeout)

def release_lock(file_path):
    lock_key = f"file_lock:{file_path}"
    redis_client.delete(lock_key)

def calculate_file_hash(file_path):
    sha = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while chunk := f.read(4096):
            sha.update(chunk)
    return sha.hexdigest()

def get_file_mime_type(file_path):
    try:
        return magic.from_file(file_path, mime=True)
    except Exception as e:
        logger.warning(f"MIME detection error: {str(e)}")
        return None

def detect_encoding(content):
    try:
        return chardet.detect(content)['encoding'] or 'utf-8'
    except Exception as e:
        logger.warning(f"Encoding detection failed: {str(e)}")
        return 'utf-8'

def process_archive(file_path, root_path, parent_archive=None):
    try:
        if not acquire_lock(file_path):
            logger.warning(f"File locked: {file_path}")
            return

        mime = get_file_mime_type(file_path)
        archive_type = SUPPORTED_ARCHIVE_FORMATS.get(mime)

        if not archive_type:
            return

        handler = {
            'zip': handle_zip,
            'rar': handle_rar
        }[archive_type]

        handler(file_path, root_path, parent_archive)

    except Exception as e:
        logger.error(f"Archive processing failed: {str(e)}")
    finally:
        release_lock(file_path)

def handle_zip(zip_path, root_path, parent_archive):
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for file_info in zf.infolist():
                if file_info.is_dir():
                    continue

                with zf.open(file_info) as file:
                    content = file.read()
                    process_archive_content(
                        content=content,
                        file_name=file_info.filename,
                        root_path=root_path,
                        parent_archive=zip_path,
                        is_archive_check=lambda c: check_compressed_type(c, zipfile.is_zipfile)
                    )
    except Exception as e:
        logger.error(f"ZIP processing error: {str(e)}")

def handle_rar(rar_path, root_path, parent_archive):
    try:
        with rarfile.RarFile(rar_path) as rf:
            for file_info in rf.infolist():
                if file_info.isdir():
                    continue

                with rf.open(file_info) as file:
                    content = file.read()
                    process_archive_content(
                        content=content,
                        file_name=file_info.filename,
                        root_path=root_path,
                        parent_archive=rar_path,
                        is_archive_check=lambda c: check_compressed_type(c, rarfile.is_rarfile)
                    )
    except Exception as e:
        logger.error(f"RAR processing error: {str(e)}")

def check_compressed_type(content, checker):
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(content)
        tmp.close()
        try:
            return checker(tmp.name)
        finally:
            os.unlink(tmp.name)

def process_archive_content(content, file_name, root_path, parent_archive, is_archive_check):
    try:
        if is_archive_check(content):
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(content)
                tmp.close()
                process_archive(tmp.name, root_path, parent_archive)
                return
        else:
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(content)
                tmp.close()
                process_single_file(
                    tmp.name,
                    root_path,
                    parent_archive=parent_archive,
                    rel_in_archive=file_name
                )
    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)

def process_single_file(file_path, root_path, parent_archive=None, rel_in_archive=None):
    try:
        file_hash = calculate_file_hash(file_path)
        
        if Book.objects.filter(file_hash=file_hash).exists():
            logger.info(f"Skipping duplicate: {file_path}")
            return

        mime = get_file_mime_type(file_path)
        if not mime or mime not in SUPPORTED_BOOK_FORMATS:
            return

        meta = None
        book_format = SUPPORTED_BOOK_FORMATS[mime]
        
        if book_format == 'fb2':
            meta = extract_meta_from_fb2(file_path)
        elif book_format == 'epub':
            meta = extract_meta_from_epub(file_path)

        if not meta:
            return

        series = None
        if meta['series']:
            series, _ = Series.objects.get_or_create(
                title=meta['series'],
                defaults={'description': meta.get('series_description', '')}
            )

        book_data = {
            'title': meta['title'][:500],
            'description': meta['description'][:5000],
            'file_path': os.path.relpath(parent_archive, root_path) if parent_archive else os.path.relpath(file_path, root_path),
            'file_archive': os.path.relpath(parent_archive, root_path) if parent_archive else None,
            'file_in_archive': rel_in_archive,
            'lang': (meta['lang'][:2] if meta['lang'] else 'ru').lower(),
            'file_hash': file_hash,
            'series': series,
            'series_number': meta['series_number']
        }

        book, created = Book.objects.update_or_create(
            file_hash=file_hash,
            defaults=book_data
        )

        if meta['cover']:
            from django.core.files.base import ContentFile
            try:
                book.cover.save(
                    f"{file_hash}.jpg",
                    ContentFile(meta['cover']),
                    save=True
                )
            except Exception as e:
                logger.warning(f"Failed to save cover: {str(e)}")

        for author_data in meta['authors']:
            author, _ = Author.objects.get_or_create(
                last_name=author_data['last_name'][:100],
                first_name=author_data['first_name'][:100],
                defaults={'middle_name': author_data['middle_name'][:100]}
            )
            book.authors.add(author)

        for keyword in meta['keywords']:
            kw, _ = Keyword.objects.get_or_create(name=keyword[:100])
            book.keywords.add(kw)

        logger.info(f"{'Created' if created else 'Updated'} book: {book.title}")

    except Exception as e:
        logger.error(f"File processing failed: {str(e)}")

def extract_cover_from_fb2(file_path):
    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read()
        
        encoding = detect_encoding(file_path)
        parser = etree.XMLParser(recover=True, encoding=encoding)
        tree = etree.fromstring(raw_data, parser=parser)
        
        ns = {'fb': 'http://www.gribuser.ru/xml/fictionbook/2.0'}
        cover = tree.find('fb:description/fb:title-info/fb:coverpage/fb:image', namespaces=ns)
        
        if cover is not None:
            href = cover.get('{http://www.w3.org/1999/xlink}href')
            if href and href.startswith('#'):
                binary = tree.find(f"fb:binary[@id='{href[1:]}']", namespaces=ns)
                if binary is not None and binary.text:
                    return binary.text.encode(encoding).decode('utf-8', errors='replace')
        return None
    except Exception as e:
        logger.error(f"Cover extraction failed: {str(e)}")
        return None

def extract_meta_from_fb2(file_path):
    try:
        encoding = detect_encoding(file_path)
        parser = etree.XMLParser(encoding=encoding, recover=True)
        tree = etree.parse(file_path, parser=parser)
        
        ns = {'fb': 'http://www.gribuser.ru/xml/fictionbook/2.0'}
        meta = {
            'title': "Без названия",
            'authors': [],
            'series': None,
            'series_number': None,
            'lang': 'ru',
            'description': '',
            'keywords': [],
            'cover': None
        }

        root = tree.getroot()
        lang = root.get('lang', 'ru')
        meta['lang'] = lang.split('-')[0].lower() if lang else 'ru'
        meta['cover'] = extract_cover_from_fb2(file_path)

        title_info = root.find('fb:description/fb:title-info', namespaces=ns)
        if title_info is not None:
            title = title_info.findtext('fb:book-title', namespaces=ns)
            meta['title'] = title.strip() if title else meta['title']

            for author in title_info.findall('fb:author', namespaces=ns):
                first = author.findtext('fb:first-name', namespaces=ns, default='').strip()
                last = author.findtext('fb:last-name', namespaces=ns, default='').strip()
                middle = author.findtext('fb:middle-name', namespaces=ns, default='').strip()
                meta['authors'].append({
                    'first_name': first,
                    'last_name': last,
                    'middle_name': middle
                })

            sequence = title_info.find('fb:sequence', namespaces=ns)
            if sequence is not None:
                meta['series'] = sequence.get('name', '').strip()
                try:
                    meta['series_number'] = float(sequence.get('number', 0))
                except (ValueError, TypeError):
                    meta['series_number'] = None

            for genre in title_info.findall('fb:genre', namespaces=ns):
                if genre.text:
                    meta['keywords'].append(genre.text.strip().replace('\n', ' '))

            annotation = title_info.find('fb:annotation', namespaces=ns)
            if annotation is not None:
                texts = []
                for elem in annotation.iter():
                    if elem.text and elem.tag != '{http://www.gribuser.ru/xml/fictionbook/2.0}annotation':
                        texts.append(elem.text.strip().replace('\n', ' '))
                meta['description'] = ' '.join(texts)

        return meta
    except etree.XMLSyntaxError as e:
        logger.error(f"Invalid XML in {file_path}: {str(e)}")
        return None
    except UnicodeDecodeError as e:
        logger.error(f"Encoding error in {file_path}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"FB2 processing error: {str(e)}")
        return None
