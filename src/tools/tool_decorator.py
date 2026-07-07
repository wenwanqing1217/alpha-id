"""
Tool decorator for Alpha-ID.

Provides a simple @tool decorator compatible with LangChain's tool pattern,
but without requiring the langchain package.
"""

from typing import Any, Callable


def tool(func: Callable[..., Any]) -> Callable[..., Any]:
    """Mark a function as a tool.

    This is a no-op decorator that provides compatibility with LangChain's
    @tool pattern without requiring the langchain package.
    """
    func._is_tool = True  # type: ignore[attr-defined]
    return func


class ToolRuntime:
    """Runtime context for tool execution.

    This is a minimal implementation for compatibility.
    """

    def __init__(self, **kwargs: Any) -> None:
        self.state = kwargs
