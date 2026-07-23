from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """使用 bcrypt 对密码进行哈希。（bcrypt 最大支持 72 字节）"""
    password = password[:72]
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码与 bcrypt 哈希是否匹配。（bcrypt 最大支持 72 字节）"""
    plain_password = plain_password[:72]
    return pwd_context.verify(plain_password, hashed_password)
