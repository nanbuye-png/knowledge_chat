from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger


# 统一"内部错误"对外文案（审计 §5.5 / 错误契约）：
#   1) 绝不把 str(e) 拼进响应 —— SQL、DSN、堆栈片段都会顺着它漏出去；
#   2) 同一类故障在 chat / query / upload / conversation 各处文案必须一致，
#      前端才能按 code 而不是按字符串做处理；
#   3) code 固定为 INTERNAL_ERROR，便于监控按错误码聚合告警。
INTERNAL_ERROR_CODE = "INTERNAL_ERROR"
INTERNAL_ERROR_MESSAGE = "服务器内部错误"


class AppError(Exception):
    """应用基础异常类，包含错误码和消息。"""
    def __init__(self, code: str, message: str, status_code: int = 500):
        self.code = code
        self.message = message
        self.status_code = status_code


def internal_error(context: str) -> AppError:
    """记录原始异常（含 traceback）并返回**统一的**内部错误异常。

    在 ``except`` 块里调用，例如::

        try:
            ...
        except Exception:
            raise internal_error("chat 调用失败")

    对外只有一句固定文案；原始异常通过 ``logger.exception`` 落到日志里
    （带堆栈），排障不会因为"不泄漏细节"而变难。
    """
    logger.exception(f"Internal error: {context}")
    return AppError(
        code=INTERNAL_ERROR_CODE,
        message=INTERNAL_ERROR_MESSAGE,
        status_code=500,
    )


class ResourceNotFoundError(AppError):
    def __init__(self, resource: str, identifier: str | int = ""):
        super().__init__(
            code="RESOURCE_NOT_FOUND",
            message=f"{resource} not found" + (f": {identifier}" if identifier else ""),
            status_code=404,
        )


class PermissionDeniedError(AppError):
    def __init__(self, message: str = "Permission denied"):
        super().__init__(
            code="PERMISSION_DENIED",
            message=message,
            status_code=403,
        )


class ValidationError(AppError):
    def __init__(self, message: str = "Validation error"):
        super().__init__(
            code="VALIDATION_ERROR",
            message=message,
            status_code=400,
        )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """统一处理自定义 AppError 异常。"""
    logger.warning(f"AppError [{exc.code}]: {exc.message}")
    content = {"code": exc.code, "message": exc.message}
    if exc.status_code >= 500:
        # 内部错误带上 request_id：与 global_exception_handler 保持一致，
        # 前端报障时可以直接对齐后端日志（响应里仍然没有实现细节）。
        from .context import get_request_id

        content["request_id"] = (
            getattr(getattr(request, "state", None), "request_id", None)
            or get_request_id()
        )
    return JSONResponse(status_code=exc.status_code, content=content)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """将 HTTPException 转换为统一错误格式。"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": "HTTP_ERROR", "message": exc.detail},
    )