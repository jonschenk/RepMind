import httpx
import asyncio

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "deepseek-llm"

async def run_deepseek(prompt: str) -> str:
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False
    }

    timeout = httpx.Timeout(60.0)

    async def stream_deepseek(prompt: str):
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                "http://localhost:11434/api/generate",
                json={"model": "deepseek-llm", "prompt": prompt, "stream": True}
            ) as response:
                async for line in response.aiter_lines():
                    if line.strip().startswith("data: "):
                        yield line.removeprefix("data: ").strip()