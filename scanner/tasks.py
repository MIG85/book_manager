from celery import shared_task
import os
import logging
from django.conf import settings
from .utils import process_archive

logger = logging.getLogger(__name__)

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
    retry_jitter=False
)
def process_archive_task(self, file_path, root_path, parent_archive=None):
    try:
        process_archive(file_path, root_path, parent_archive)
        return {
            'status': 'success',
            'file_path': file_path,
            'parent_archive': parent_archive
        }
    except Exception as e:
        logger.error(f"Task failed: {file_path} - {str(e)}")
        raise self.retry(exc=e, countdown=60)

@shared_task(bind=True)
def scan_library(self, full_scan=False):
    total = 0
    processed = 0
    
    for root, dirs, files in os.walk(settings.LIBRARY_ROOT):
        total += len(files)
    
    for root, dirs, files in os.walk(settings.LIBRARY_ROOT):
        for filename in files:
            file_path = os.path.join(root, filename)
            process_archive_task.delay(file_path, settings.LIBRARY_ROOT)
            processed += 1
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': processed,
                    'total': total,
                    'progress': f"{processed/total:.1%}",
                    'current_file': filename
                }
            )
    
    return {
        'current': total,
        'total': total,
        'status': 'COMPLETED',
        'processed_files': processed
    }