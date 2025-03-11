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
from io import BytesIO
from django.core.files import File
from django.conf import settings
from books.models import Book, Author, Series, Keyword

logger = logging.getLogger(__name__)
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB
)

SUPPORTED_ARCHIVE_TYPES = {
    'application/zip': 'zip',
    'application/x-rar-compressed': 'rar',
    'application/vnd.rar': 'rar'
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

def get_archive_type(file_path):
    mime = magic.from_file(file_path, mime=True)
    return SUPPORTED_ARCHIVE_TYPES.get(mime)

def detect_encoding(file_path):
    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read(1024)

        detected = chardet.detect(raw_data)
        encoding = detected['encoding'] or 'utf-8'
        
        # Нормализация названия кодировки
        if isinstance(encoding, bytes):
            encoding = encoding.decode('utf-8', 'ignore')
        encoding = (
            str(encoding)
            .lower()
            .replace('b\'', '')
            .replace('\'', '')
            .replace('utf-8-sig', 'utf-8')
            .replace('utf_8', 'utf-8')
            .replace('windows-1251', 'cp1251')
            .strip()
        )

        # Проверка валидности кодировки
        try:
            'test'.encode(encoding)
            return encoding
        except LookupError:
            return 'utf-8'
            
    except Exception as e:
        logger.warning(f"Encoding detection failed: {str(e)}")
        return 'utf-8'

def extract_cover_from_fb2(file_path):
    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read()
        
        # Удаление BOM
        bom = b'\xef\xbb\xbf'
        if raw_data.startswith(bom):
            raw_data = raw_data[len(bom):]
        
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
                    base64_data = binary.text.strip()
                    try:
                        return base64.b64decode(base64_data)
                    except (TypeError, binascii.Error) as e:
                        logger.error(f"Base64 decode error: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Cover extraction failed: {str(e)}", exc_info=True)
        return None

def extract_meta_from_fb2(file_path):
    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read()
        
        # Удаление BOM
        bom = b'\xef\xbb\xbf'
        if raw_data.startswith(bom):
            raw_data = raw_data[len(bom):]
            
        encoding = detect_encoding(file_path)
        
        # Форсируем UTF-8 если невалидная кодировка
        try:
            etree.XMLParser(encoding=encoding)
        except LookupError:
            encoding = 'utf-8'
            
        parser = etree.XMLParser(
            encoding=encoding,
            recover=True,
            resolve_entities=False
        )
        
        tree = etree.fromstring(raw_data, parser=parser)
        
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

        root = tree
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

def process_single_file(file_path, root_path, parent_archive=None, rel_in_archive=None):
    try:
        file_hash = calculate_file_hash(file_path)
        
        if Book.objects.filter(file_hash=file_hash).exists():
            logger.info(f"Skipping duplicate: {file_path}")
            return

        mime = magic.from_file(file_path, mime=True)
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

    except UnicodeDecodeError as e:
        logger.error(f"Unicode error in {file_path}: {str(e)}")
    except Exception as e:
        logger.error(f"File processing failed: {str(e)}")
        raise

def process_archive(file_path, root_path, parent_archive=None, depth=0):
    if depth > 5:
        logger.warning(f"Max archive nesting depth reached: {file_path}")
        return

    if not acquire_lock(file_path):
        logger.warning(f"File locked: {file_path}")
        return

    try:
        archive_type = get_archive_type(file_path)
        if not archive_type:
            return

        if archive_type == 'zip':
            with zipfile.ZipFile(file_path) as zf:
                for name in zf.namelist():
                    if name.endswith('/'):
                        continue
                    
                    with zf.open(name) as entry:
                        content = entry.read()
                        process_content(
                            content=content,
                            file_name=name,
                            root_path=root_path,
                            depth=depth+1,
                            parent_archive=file_path
                        )
        elif archive_type == 'rar':
            with rarfile.RarFile(file_path) as rf:
                for entry in rf.infolist():
                    if entry.isdir():
                        continue
                    
                    with rf.open(entry) as f:
                        content = f.read()
                        process_content(
                            content=content,
                            file_name=entry.filename,
                            root_path=root_path,
                            depth=depth+1,
                            parent_archive=file_path
                        )
    except (zipfile.BadZipFile, rarfile.RarCannotExec, rarfile.BadRarFile) as e:
        logger.error(f"Bad archive: {file_path} - {str(e)}")
    except Exception as e:
        logger.error(f"Error processing archive: {file_path} - {str(e)}")
    finally:
        release_lock(file_path)

def process_content(content, file_name, root_path, depth, parent_archive):
    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        mime = magic.from_file(tmp_path, mime=True)
        
        if mime in SUPPORTED_ARCHIVE_TYPES:
            process_archive(
                tmp_path, 
                root_path,
                parent_archive=parent_archive,
                depth=depth+1
            )
        elif mime in SUPPORTED_BOOK_FORMATS:
            process_single_file(
                file_path=tmp_path,
                root_path=root_path,
                parent_archive=parent_archive,
                rel_in_archive=file_name
            )
        else:
            logger.debug(f"Skipping unsupported file: {file_name}")
    finally:
        os.unlink(tmp_path)
