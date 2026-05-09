import httpx
import asyncio

MISTRAL_API_KEY = "EQ0XXgQQlRADFmrIO1hMnBAnPwX9N8y9"
MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"

AGENT_IDS = {
    "coder": "ag_019dde1f66bf766ca618b66745cd8cac",
    "debugger": "ag_019dde20b1c472d09b719c805c03cc23",
    "optimizer": "ag_019dde2101f776dfb1c74e44f190fa44",
}

async def call_mistral_agent(agent_id: str, messages: list, temperature: float = 0.4) -> str:
    """Вызов конкретного агента Mistral (через agent_id)"""
    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "mistral-large-latest",   # или оставить как есть
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 4096
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(MISTRAL_API_URL, json=payload, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return data["choices"][0]["message"]["content"]
        else:
            return f"Ошибка API: {response.status_code} - {response.text}"
