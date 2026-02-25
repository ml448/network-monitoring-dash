import os
from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from jose import jwt, JWTError


class RateLimit:
    LOGIN_LIMIT: str = os.getenv("RATE_LIMIT_LOGIN", "5/minute")
    REGISTER_LIMIT: str = os.getenv("RATE_LIMIT_REGISTER", "3/minute")
    DEVICES_LIMIT: str = os.getenv("RATE_LIMIT_DEVICE", "60/minute")
    DEVICE_HISTORY_LIMIT: str = os.getenv("RATE_LIMIT_HISTORY", "30/minute")
    DEVICE_DETAIL_LIMIT: str = os.getenv("RATE_LIMIT_DETAIL", "120/minute")
    USER_LIMIT: str = os.getenv("RATE_LIMIT_USER", "30/minute")
    HEALTH_LIMIT: str = os.getenv("RATE_LIMIT_HEALTH", "60/minute")
    ROOT_LIMIT: str = os.getenv("RATE_LIMIT_ROOT", "60/minute")

    ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"

    SECRET_KEY: str = os.getenv("JWT_SECRET_KEY")
    ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")

    @staticmethod
    def get_client_ip(request: Request) -> str:
        return f"ip:{get_remote_address(request)}"

    @staticmethod
    def get_user_or_ip(request: Request) -> str:
        auth_header: str | None = request.headers.get("Authorization")

        # If no header or not Bearer then fallback to IP
        if not auth_header or not auth_header.startswith("Bearer "):
            return f"ip:{get_remote_address(request)}"

        # Extract token
        token = auth_header.removeprefix("Bearer ").strip()

        try:
            # Decode JWT
            payload = jwt.decode(
                token,
                RateLimit.SECRET_KEY,
                algorithms=[RateLimit.ALGORITHM],
            )

            username = payload.get("sub")

            # Return user key if valid
            if username:
                return f"user:{username}"

        except JWTError:
            pass

        # Fallback to IP
        return f"ip:{get_remote_address(request)}"


#Create limiter 
limiter = Limiter(
    key_func=RateLimit.get_user_or_ip,
    storage_uri="memory://",
    headers_enabled=True,
    enabled=RateLimit.ENABLED,
)

async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Limit exceeded. Try again later."},
        headers={"Retry-After": "100"}
    )