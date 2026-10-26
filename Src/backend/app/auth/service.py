import hashlib
import re
import secrets
import sqlite3

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from app.auth.models import LoginIn, RegisterIn, UserOut
from app.auth.passwords import DUMMY_HASH, hash_password, verify_password
from app.common import clock
from app.common.responses import ApiError
from app.db.connection import write_transaction
from app.db.models import sessions, users

COOKIE_NAME = 'meetflow_session'
SESSION_SECONDS = 8 * 60 * 60


def token_digest(token: str | None) -> str | None:
    if token is None or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        return None
    return hashlib.sha256(token.encode('ascii')).hexdigest()


def unauthenticated():
    return ApiError(401, 'UNAUTHENTICATED', '登录状态无效或已过期，请重新登录。')


def register(engine, data: RegisterIn) -> UserOut:
    password_hash = hash_password(data.password)
    try:
        with write_transaction(engine) as connection:
            result = connection.execute(insert(users).values(username=data.username, email=str(data.email),
                password_hash=password_hash, created_at=clock.now_ms()))
            identifier = result.inserted_primary_key[0]
    except IntegrityError as error:
        if getattr(error.orig, 'sqlite_errorcode', None) == sqlite3.SQLITE_CONSTRAINT_UNIQUE:
            raise ApiError(409, 'DUPLICATE_ACCOUNT', '用户名或邮箱已被使用。') from None
        raise
    return UserOut(id=identifier, username=data.username, email=str(data.email))


def login(engine, data: LoginIn, current_token: str | None) -> tuple[UserOut, str]:
    with engine.connect() as connection:
        account = connection.execute(select(users).where(users.c.username == data.username)).mappings().first()
    valid = verify_password(data.password, account['password_hash'] if account else DUMMY_HASH)
    if not valid or account is None:
        raise ApiError(401, 'UNAUTHENTICATED', '用户名或密码错误。')
    token = secrets.token_urlsafe(32)
    old_digest = token_digest(current_token)
    with write_transaction(engine) as connection:
        now = clock.now_ms()
        connection.execute(insert(sessions).values(user_id=account['id'], token_hash=token_digest(token),
            created_at=now, expires_at=now + SESSION_SECONDS * 1000))
        if old_digest:
            connection.execute(update(sessions).where(sessions.c.token_hash == old_digest,
                sessions.c.revoked_at.is_(None)).values(revoked_at=now))
    return UserOut(id=account['id'], username=account['username'], email=account['email']), token


def authenticate(engine, token: str | None) -> UserOut:
    digest = token_digest(token)
    if digest is None:
        raise unauthenticated()
    with engine.connect() as connection:
        account = connection.execute(select(users.c.id, users.c.username, users.c.email, sessions.c.expires_at)
            .select_from(sessions.join(users, sessions.c.user_id == users.c.id))
            .where(sessions.c.token_hash == digest, sessions.c.revoked_at.is_(None))).mappings().first()
    # A blocked read must not authenticate against a clock sampled before its wait.
    if account is None or account['expires_at'] <= clock.now_ms():
        raise unauthenticated()
    return UserOut(id=account['id'], username=account['username'], email=account['email'])


def logout(engine, token: str | None) -> int:
    digest = token_digest(token)
    if digest is None:
        raise unauthenticated()
    with write_transaction(engine) as connection:
        row = connection.execute(select(sessions).where(sessions.c.token_hash == digest)).mappings().first()
        now = clock.now_ms()
        if row is None or (row['revoked_at'] is None and row['expires_at'] <= now):
            raise unauthenticated()
        if row['revoked_at'] is None:
            connection.execute(update(sessions).where(sessions.c.id == row['id']).values(revoked_at=now))
    return row['user_id']
