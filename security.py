from passlib.context import CryptContext
from itsdangerous import URLSafeSerializer
from .config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
serializer = URLSafeSerializer(settings.secret_key, salt="session")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)

def sign_session(data: dict) -> str:
    return serializer.dumps(data)

def unsign_session(token: str) -> dict | None:
    try:
        return serializer.loads(token)
    except Exception:
        return None
