"""Adapters for any LLM - OpenAI, Claude, DeepSeek, MCP, generic."""

from memolite.adapters.anthropic import AnthropicAdapter
from memolite.adapters.base import BaseAdapter
from memolite.adapters.generic import GenericAdapter
from memolite.adapters.openai import OpenAIAdapter

__all__ = ["AnthropicAdapter", "BaseAdapter", "GenericAdapter", "OpenAIAdapter"]

# DeepSeek is OpenAI compatible
DeepSeekAdapter = OpenAIAdapter
