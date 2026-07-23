from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _truncate_password(password: str) -> str:
    """按 UTF-8 字节截断密码到 bcrypt 支持的 72 字节上限。"""
    return password.encode("utf-8")[:72].decode("utf-8", errors="ignore")


def hash_password(password: str) -> str:
    """使用 bcrypt 对密码进行哈希。（bcrypt 最大支持 72 字节）"""
    password = _truncate_password(password)
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码与 bcrypt 哈希是否匹配。（bcrypt 最大支持 72 字节）"""
    plain_password = _truncate_password(plain_password)
    return pwd_context.verify(plain_password, hashed_password)
