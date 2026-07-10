"""FastAPI application entry point.

启动: ``uvicorn maestro.main:app --reload``。
HTTP 实现位于 ``maestro.api``；此模块保留稳定的导入入口。
"""

from maestro.api.app import create_app
from maestro.api.routes.chat import _contract_route
from maestro.api.routes.knowledge import _MAX_UPLOAD_BYTES

app = create_app()

__all__ = ["app", "create_app", "_contract_route", "_MAX_UPLOAD_BYTES"]
