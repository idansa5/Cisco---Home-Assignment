from __future__ import annotations

import ollama


class OllamaClient:
    """Thin wrapper around the ollama Python package.

    base_url and model are injected at construction time so the caller
    (config.py → settings) controls which provider and model are used.
    """

    def __init__(self, base_url: str, model: str, timeout: float = 120.0) -> None:
        self._model = model
        self._client = ollama.Client(host=base_url, timeout=timeout)

    def generate(self, prompt: str) -> str:
        """Send prompt, return raw response string from the model."""
        response = self._client.generate(
            model=self._model,
            prompt=prompt,
            format="json",   # instructs Ollama to constrain output to valid JSON
            stream=False,
            options={"temperature": 0},  # keep it deterministic
        )
        return response.response
