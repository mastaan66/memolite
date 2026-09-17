"""Any LLM - generic prompt injection. Works with local models, DeepSeek, etc."""

from memolite import MemoryStore
from memolite.adapters.generic import GenericAdapter

store = MemoryStore("agent.db")
store.add_turn(session="s1", role="user", content="I prefer concise Python")

# one line plug for any LLM
adapter = GenericAdapter(store)
prompt = adapter.inject("how should I write code?", session_id="s1")

# use with any API
# openai: client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}])
# claude: client.messages.create(model="claude-3-5-sonnet", messages=[{"role": "user", "content": prompt}])
# deepseek: client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}])
# ollama: requests.post("http://localhost:11434/api/chat", json={"messages": [{"role": "user", "content": prompt}]})

print(prompt)
print(
    adapter.build_messages(
        system="You are helpful", user_query="how should I write code?", session_id="s1"
    )
)
