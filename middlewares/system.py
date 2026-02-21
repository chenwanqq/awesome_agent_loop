from tools import read_file, write_file, edit_file, list_dir, exec
from .base import Middleware

class SystemMiddleware(Middleware):
    """系统操作中间件"""

    def tools(self) -> list[callable]:
        return [read_file, write_file, edit_file, list_dir, exec]