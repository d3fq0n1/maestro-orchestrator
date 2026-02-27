"""
NCG Generator — Headless model interface for novel content generation.

Headless generators produce content WITHOUT conversational framing:
  - No system prompts shaping personality or helpfulness
  - No RLHF-aligned "assistant" role
  - Raw completion from the model weights

The output serves as a diversity baseline. It represents what the model
produces when free of conversational pressure — the control group against
which conversational agent outputs are measured for drift.
"""

import os
from abc import ABC, abstractmethod


class HeadlessGenerator(ABC):
    """
    Base class for headless content generators.

    Subclasses implement raw generation against a specific model/API.
    The key contract: no system prompt, no assistant framing, no
    conversational scaffolding. Just the prompt and the weights.
    """

    @abstractmethod
    def generate(self, prompt: str) -> dict:
        """
        Generate raw content from a prompt without conversational framing.

        Returns:
            dict with keys:
                - "content": the raw generated text
                - "model": identifier of the model used
                - "metadata": dict of any available signal (token counts,
                  logprobs if supported, latency, etc.)
        """
        pass

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Identifier for the underlying model."""
        pass


class MockHeadlessGenerator(HeadlessGenerator):
    """
    Mock headless generator for testing and development.

    Returns deterministic responses that simulate raw, unframed output —
    blunt, unshaped, no hedging. This is what headless looks like:
    the model says what it computes, not what it thinks you want to hear.
    """

    @property
    def model_id(self) -> str:
        return "mock-headless-v1"

    def generate(self, prompt: str) -> dict:
        raw = (
            f"Raw generation for: '{prompt}' — "
            "Unframed. No alignment shaping. Direct weight output. "
            "This content exists outside the conversational reward surface."
        )
        return {
            "content": raw,
            "model": self.model_id,
            "metadata": {
                "token_count": len(raw.split()),
                "logprobs_available": False,
                "framing": "none",
            },
        }


class OpenAIHeadlessGenerator(HeadlessGenerator):
    """
    Headless generator using OpenAI's API in completion mode.

    Uses logprobs when available — this is the bridge between
    conversational-level metadata and token-level analysis.
    """

    def __init__(self, model: str = "gpt-3.5-turbo", temperature: float = 1.0):
        self._model = model
        self.temperature = temperature

    @property
    def model_id(self) -> str:
        return self._model

    def generate(self, prompt: str) -> dict:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return MockHeadlessGenerator().generate(prompt)

        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        # No system prompt. No role framing. Just the raw prompt as user input.
        # Temperature at 1.0 by default — we want the full distribution,
        # not the compressed high-confidence peak.
        response = client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
            logprobs=True,
            top_logprobs=5,
        )

        choice = response.choices[0]
        content = choice.message.content.strip()

        # Extract token-level signal when available
        token_data = []
        if choice.logprobs and choice.logprobs.content:
            for token_info in choice.logprobs.content:
                token_data.append({
                    "token": token_info.token,
                    "logprob": token_info.logprob,
                    "top_alternatives": [
                        {"token": alt.token, "logprob": alt.logprob}
                        for alt in (token_info.top_logprobs or [])
                    ],
                })

        return {
            "content": content,
            "model": self.model_id,
            "metadata": {
                "token_count": response.usage.completion_tokens if response.usage else len(content.split()),
                "prompt_tokens": response.usage.prompt_tokens if response.usage else None,
                "logprobs_available": len(token_data) > 0,
                "logprobs": token_data if token_data else None,
                "framing": "none",
                "temperature": self.temperature,
            },
        }


class AnthropicHeadlessGenerator(HeadlessGenerator):
    """
    Headless generator using Anthropic's API.

    No logprobs available yet — operates at the conversational metadata
    level. Still valuable as a headless baseline because the absence of
    a system prompt removes the personality/alignment shaping layer.
    """

    def __init__(self, model: str = "claude-sonnet-4-20250514", temperature: float = 1.0):
        self._model = model
        self.temperature = temperature

    @property
    def model_id(self) -> str:
        return self._model

    def generate(self, prompt: str) -> dict:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return MockHeadlessGenerator().generate(prompt)

        import requests
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        data = {
            "model": self._model,
            "max_tokens": 1024,
            "temperature": self.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }

        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=data,
        )
        json_data = response.json()

        content_parts = json_data.get("content", [])
        content = "".join(part.get("text", "") for part in content_parts)
        usage = json_data.get("usage", {})

        return {
            "content": content,
            "model": self.model_id,
            "metadata": {
                "token_count": usage.get("output_tokens"),
                "prompt_tokens": usage.get("input_tokens"),
                "logprobs_available": False,
                "framing": "none",
                "temperature": self.temperature,
            },
        }
