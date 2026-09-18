"""Patch tests: fake OpenAI/Anthropic clients, no network, no libs."""

from __future__ import annotations

from types import SimpleNamespace

from memolite import MemoryStore
from memolite.patch import (
    patch_anthropic,
    patch_openai,
    unpatch_anthropic,
    unpatch_openai,
)


class FakeCompletions:
    def __init__(self):
        self.calls = []

    def create(self, messages, **kw):
        self.calls.append(list(messages))
        user = messages[-1]["content"]
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=f"echo: {user}"))]
        )


class FakeOpenAI:
    def __init__(self):
        self.chat = SimpleNamespace(completions=FakeCompletions())


class FakeMessages:
    def __init__(self):
        self.calls = []

    def create(self, messages, system="", **kw):
        self.calls.append((system, list(messages)))
        user = messages[-1]["content"]
        return {"content": [{"type": "text", "text": f"echo: {user}"}]}


class FakeAnthropic:
    def __init__(self):
        self.messages = FakeMessages()


def test_patch_openai_auto_every_time():
    store = MemoryStore(":memory:")
    client = FakeOpenAI()
    patch_openai(client, store, session="s1")
    # user writes normal code, zero memory calls
    r1 = client.chat.completions.create(
        messages=[{"role": "user", "content": "I prefer concise Python"}]
    )
    assert "echo" in r1.choices[0].message.content
    r2 = client.chat.completions.create(
        messages=[{"role": "user", "content": "how should I write?"}]
    )
    assert "echo" in r2.choices[0].message.content
    # memory happened implicitly: turns stored, facts extracted
    assert store.stats()["turns"] == 4
    assert store.stats()["memories"] >= 1
    # second call got memory injected (system prepended)
    assert client.chat.completions.calls[1][0]["role"] == "system"
    unpatch_openai(client)
    store.close()


def test_patch_openai_idempotent():
    store = MemoryStore(":memory:")
    client = FakeOpenAI()
    patch_openai(client, store)
    patch_openai(client, store)
    client.chat.completions.create(messages=[{"role": "user", "content": "hi"}])
    assert store.stats()["turns"] == 2
    store.close()


def test_patch_anthropic_auto():
    store = MemoryStore(":memory:")
    client = FakeAnthropic()
    patch_anthropic(client, store, session="s1")
    r = client.messages.create(messages=[{"role": "user", "content": "My name is Ada"}])
    assert "echo" in r["content"][0]["text"]
    assert store.stats()["turns"] == 2
    unpatch_anthropic(client)
    store.close()


def test_patch_stream_passthrough_still_injects():
    store = MemoryStore(":memory:")
    store.remember("User prefers Python", importance=0.9)
    client = FakeOpenAI()
    orig = client.chat.completions.create

    def stream_create(messages, **kw):
        assert kw.get("stream") is True
        return {"stream": True}

    client.chat.completions.create = stream_create
    patch_openai(client, store, session="s1")
    out = client.chat.completions.create(
        messages=[{"role": "user", "content": "python?"}], stream=True
    )
    assert out == {"stream": True}
    # stream path injects but does not store
    assert store.stats()["turns"] == 0
    unpatch_openai(client)
    client.chat.completions.create = orig


def test_patch_session_actor_callables():
    store = MemoryStore(":memory:")
    client = FakeOpenAI()
    patch_openai(
        client,
        store,
        session=lambda msgs, kw: "sess-" + msgs[-1]["content"][:2],
        actor=lambda msgs, kw: "bob",
    )
    client.chat.completions.create(messages=[{"role": "user", "content": "I use Neovim"}])
    assert store.stats()["turns"] == 2
    assert store.stats()["sessions"] >= 1
    unpatch_openai(client)
    store.close()


def test_patch_list_block_content():
    from memolite.patch import _assistant_text_anthropic, _assistant_text_openai, _last_user_text

    assert _last_user_text([{"role": "user", "content": [{"type": "text", "text": "hi"}]}]) == "hi"
    assert _last_user_text([{"role": "assistant", "content": "x"}]) == ""
    assert _assistant_text_openai(object()) == ""
    assert _assistant_text_anthropic(object()) == ""
    assert _assistant_text_anthropic({"content": [{"type": "text", "text": "ok"}]}) == "ok"
