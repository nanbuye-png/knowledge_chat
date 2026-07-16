"""
密码强度验证策略。

强制执行用户密码的最低安全要求：
- 至少 12 位
- 至少一个数字
- 至少一个大写字母
- 至少一个小写字母
- 至少一个特殊字符（非字母数字、非空白字符）
"""

import re
from dataclasses import dataclass, field


MIN_LENGTH = 12

# 各要求的正则模式
_HAS_DIGIT = re.compile(r"\d")
_HAS_UPPER = re.compile(r"[A-Z]")
_HAS_LOWER = re.compile(r"[a-z]")
_HAS_SPECIAL = re.compile(r"[^\w\s]")


@dataclass
class PasswordValidationResult:
    """密码强度验证结果。"""

    is_valid: bool = True
    errors: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        self.is_valid = False
        self.errors.append(message)


def validate_password_strength(password: str) -> tuple[bool, list[str]]:
    """验证密码是否符合强度策略。

    Args:
        password: 待检查的明文密码。

    Returns:
        (is_valid, errors) 元组，``is_valid`` 为 ``True`` 表示满足所有要求，
        ``errors`` 为失败原因列表（验证通过时为空）。
    """
    result = PasswordValidationResult()

    if len(password) < MIN_LENGTH:
        result.add_error(f"密码长度至少需要 {MIN_LENGTH} 位，当前为 {len(password)} 位")

    if not _HAS_DIGIT.search(password):
        result.add_error("密码必须包含至少一个数字")

    if not _HAS_UPPER.search(password):
        result.add_error("密码必须包含至少一个大写字母")

    if not _HAS_LOWER.search(password):
        result.add_error("密码必须包含至少一个小写字母")

    if not _HAS_SPECIAL.search(password):
        result.add_error("密码必须包含至少一个特殊字符（如 @#$%^&* 等）")

    return result.is_valid, result.errors