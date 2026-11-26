from celery import shared_task

from .services import sweep_expired_attempts


@shared_task
def auto_submit_expired_attempts():
    return sweep_expired_attempts()
