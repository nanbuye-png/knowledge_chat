from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger


class AppError(Exception):
    """Base application error with code and message."""
    def __init__(self, code: str, message: str, status_code: int = 500):
        self.code = code
        self.message = message
        self.status_code = status_code


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
    """Unified handler for custom AppError exceptions."""
    logger.warning(f"AppError [{exc.code}]: {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message},
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Convert HTTPException to unified error format."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": "HTTP_ERROR", "message": exc.detail},
    )