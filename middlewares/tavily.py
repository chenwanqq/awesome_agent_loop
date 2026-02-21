from tools import tavily_search, tavily_extract
from .base import Middleware

class TavilyMiddleware(Middleware):
    """Tavily搜索中间件"""
    
    def tools(self) -> list[callable]:
        return [tavily_search, tavily_extract]