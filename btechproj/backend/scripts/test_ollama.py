"""Quick smoke test for Ollama gemma4:31b-cloud via OpenAI-compatible API."""

from openai import OpenAI

client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

print("Calling gemma4:31b-cloud via Ollama...")
resp = client.chat.completions.create(
    model="gemma4:31b-cloud",
    messages=[
        {"role": "system", "content": "Respond with a JSON object only."},
        {
            "role": "user",
            "content": 'Return a JSON object: {"status": "ok", "model": "gemma4"}',
        },
    ],
    temperature=0.1,
    max_tokens=100,
    response_format={"type": "json_object"},
)

print(f"Model:    {resp.model}")
print(f"Response: {resp.choices[0].message.content}")
print("Ollama smoke test PASSED")
