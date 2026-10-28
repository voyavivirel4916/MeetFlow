import logging
import secrets
import smtplib
import ssl
from email.message import EmailMessage

from sqlalchemy import delete, insert, select, update

from app.auth.passwords import hash_password
from app.auth.service import token_digest
from app.common import clock
from app.common.responses import ApiError
from app.db.connection import write_transaction
from app.db.models import password_resets, sessions, users

logger = logging.getLogger('meetflow.mail')


def configured(settings):
    return bool(settings.public_origin and settings.smtp_host and settings.smtp_username
                and settings.smtp_password.get_secret_value() and settings.smtp_sender)


def issue(engine, email):
    token = secrets.token_urlsafe(32)
    with write_transaction(engine) as db:
        now = clock.now_ms()
        db.execute(delete(password_resets).where(password_resets.c.expires_at <= now))
        user = db.execute(select(users.c.id).where(users.c.email == email)).scalar_one_or_none()
        if user is None:
            return None
        recent = db.execute(select(password_resets.c.token_hash).where(
            password_resets.c.user_id == user, password_resets.c.created_at > now - 60000)).first()
        if recent:
            return None
        db.execute(update(password_resets).where(password_resets.c.user_id == user,
            password_resets.c.used_at.is_(None)).values(used_at=now))
        db.execute(insert(password_resets).values(token_hash=token_digest(token), user_id=user,
            created_at=now, expires_at=now + 15 * 60 * 1000))
    return token


def deliver(settings, address, token):
    try:
        message = EmailMessage()
        message['Subject'] = 'MeetFlow 密码重置'
        message['From'] = settings.smtp_sender
        message['To'] = address
        message.set_content('请在15分钟内打开以下链接重置密码；若不是你发起的操作，请忽略。\n'
                            + settings.public_origin + '/reset-password#token=' + token)
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10,
                              context=ssl.create_default_context()) as server:
            server.login(settings.smtp_username, settings.smtp_password.get_secret_value())
            server.send_message(message)
    except Exception:
        # Never log exception text, recipient, token or SMTP credentials.
        logger.error('code=PASSWORD_RESET_DELIVERY_FAILED')


def consume(engine, token, password):
    digest = token_digest(token)
    if digest is None:
        raise ApiError(400, 'RESET_INVALID', '重置链接无效或已过期，请重新申请。')
    encoded = hash_password(password)
    with write_transaction(engine) as db:
        now = clock.now_ms()
        reset = db.execute(select(password_resets).where(password_resets.c.token_hash == digest,
            password_resets.c.used_at.is_(None), password_resets.c.expires_at > now)).mappings().first()
        if reset is None:
            raise ApiError(400, 'RESET_INVALID', '重置链接无效或已过期，请重新申请。')
        db.execute(update(users).where(users.c.id == reset['user_id']).values(password_hash=encoded))
        db.execute(update(password_resets).where(password_resets.c.user_id == reset['user_id'],
            password_resets.c.used_at.is_(None)).values(used_at=now))
        db.execute(update(sessions).where(sessions.c.user_id == reset['user_id'],
            sessions.c.revoked_at.is_(None)).values(revoked_at=now))
