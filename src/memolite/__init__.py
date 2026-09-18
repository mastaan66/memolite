"""memolite - SQLite-native agentic memory. Plug and play for any LLM."""

from memolite.adapters.anthropic import AnthropicAdapter
from memolite.adapters.generic import GenericAdapter
from memolite.adapters.openai import DeepSeekAdapter, OpenAIAdapter
from memolite.async_store import AsyncMemoryStore
from memolite.auto import auto_chat
from memolite.config import Config
from memolite.embedders import local_embedder, ollama_embedder, openai_embedder
from memolite.models import Memory, RecallResult, Session, ToolCall, Turn
from memolite.patch import patch_anthropic, patch_openai, unpatch_anthropic, unpatch_openai
from memolite.security import decrypt_str, encrypt_str, redact_pii
from memolite.store import MemoryStore
from memolite.sync import export_bundle, import_bundle, sync_files
from memolite.vec import cosine, hash_embed


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
    "cosine",
    "decrypt_str",
    "encrypt_str",
    "export_bundle",
    "hash_embed",
    "import_bundle",
    "local_embedder",
    "ollama_embedder",
    "openai_embedder",
    "patch_anthropic",
    "patch_openai",
    "plug",
    "redact_pii",
    "sync_files",
    "unpatch_anthropic",
    "unpatch_openai",
]
__version__ = "0.1.0"
