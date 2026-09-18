"""memolite - SQLite-native agentic memory. Plug and play for any LLM."""

from memolite.adapters.anthropic import AnthropicAdapter
from memolite.adapters.generic import GenericAdapter
from memolite.adapters.openai import DeepSeekAdapter, OpenAIAdapter
from memolite.async_store import AsyncMemoryStore
from memolite.auto import auto_chat
from memolite.config import Config
from memolite.models import Memory, RecallResult, Session, ToolCall, Turn
from memolite.security import decrypt_str, encrypt_str, redact_pii
from memolite.store import MemoryStore


def plug(
    store: MemoryStore, llm: str = "generic"
) -> GenericAdapter | OpenAIAdapter | AnthropicAdapter:
    """One line plug for any LLM. llm in generic, openai, chatgpt, deepseek, claude, anthropic, mcp."""
    llm = llm.lower()
    if llm in {"openai", "chatgpt", "deepseek", "deepseekadapter"}:
        return OpenAIAdapter(store)
    if llm in {"claude", "anthropic"}:
        return AnthropicAdapter(store)
    return GenericAdapter(store)


__all__ = [
    "AnthropicAdapter",
    "AsyncMemoryStore",
    "Config",
    "DeepSeekAdapter",
    "GenericAdapter",
    "Memory",
    "MemoryStore",
    "OpenAIAdapter",
    "RecallResult",
    "Session",
    "ToolCall",
    "Turn",
    "auto_chat",
    "decrypt_str",
    "encrypt_str",
    "plug",
    "redact_pii",
]
__version__ = "0.1.0"
