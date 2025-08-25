import logging
import json
import re
import ast
from langchain.tools import Tool
from app.wb.tools import (
    get_unanswered_feedbacks_tool,
    post_feedback_answer_tool,
    get_chat_events_tool,
    post_chat_message_tool,
)


from app.tools.knowledge_tool import create_knowledge_base_tool

def create_knowledge_base_tool(api_key: str, base_url: str = None):
    """Оставлено для обратной совместимости. Импортируйте из app.tools.knowledge_tool."""
    from app.tools.knowledge_tool import create_knowledge_base_tool as _impl
    return _impl(api_key=api_key, base_url=base_url)
