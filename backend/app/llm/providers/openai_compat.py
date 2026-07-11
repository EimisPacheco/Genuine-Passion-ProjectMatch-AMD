"""OpenAI-compatible chat provider.

AMD/Ollama and Google both expose OpenAI-compatible
`/v1/chat/completions` endpoints, so a single client covers all of them — only
the base URL, key, and default model differ. Speed metrics are measured by wall clock (optionally streaming for
an accurate time-to-first-token), which is exactly the experienced latency the
race is meant to expose.
"""
from __future__ import annotations

import time
from typing import Callable

from backend.app.llm.providers.base import LLMResult, build_messages


class OpenAICompatProvider:
    def __init__(self, *, name: str, api_key: str, base_url: str, default_model: str) -> None:
        self.name = name
        self._api_key = api_key
        self._base_url = base_url
        self.default_model = default_model
        self._client = None

    def _ensure(self):
        if not self._api_key:
            raise RuntimeError(
                f"{self.name.upper()}_API_KEY not set; cannot call {self.name}."
            )
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=self._api_key, base_url=self._base_url)
        return self._client

    def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        model: str | None = None,
        max_tokens: int = 2048,
        images: list[str] | None = None,
        stream: bool = False,
        on_token: Callable[[str], None] | None = None,
    ) -> LLMResult:
        client = self._ensure()
        model = model or self.default_model
        messages = build_messages(prompt, system, images)
        t0 = time.time()
        if stream or on_token:
            return self._stream(client, model, messages, max_tokens, on_token, t0)

        # Thinking-mode Gemma (gemma4:31b on Ollama) spends tokens on its `reasoning`
        # trace before emitting `content`; give it enough budget so the answer
        # actually lands in content instead of being truncated to reasoning-only.
        if self.name == "amd" and (max_tokens or 0) < 1024:
            max_tokens = 1024

        resp = client.chat.completions.create(
            model=model, messages=messages, max_tokens=max_tokens
        )
        total_ms = (time.time() - t0) * 1000.0
        # Thinking models (e.g. Ollama gemma4:31b) return the answer in `content`,
        # but if the token budget is tight the answer lands in a `reasoning` field
        # with `content` empty — salvage that instead of returning nothing.
        text = ""
        if resp.choices:
            _m = resp.choices[0].message
            text = (
                getattr(_m, "content", None)
                or getattr(_m, "reasoning", None)
                or getattr(_m, "reasoning_content", None)
                or (getattr(_m, "model_extra", None) or {}).get("reasoning")
                or ""
            )
        usage = getattr(resp, "usage", None)
        in_tok = int(getattr(usage, "prompt_tokens", 0) or 0)
        out_tok = int(getattr(usage, "completion_tokens", 0) or 0) or _approx_tokens(text)
        tps = out_tok / (total_ms / 1000.0) if total_ms > 0 else 0.0
        return LLMResult(
            text=text, provider=self.name, model=model,
            input_tokens=in_tok, output_tokens=out_tok,
            ttft_ms=total_ms, total_ms=total_ms, tokens_per_sec=tps,
        )

    def _stream(self, client, model, messages, max_tokens, on_token, t0) -> LLMResult:
        ttft_ms: float | None = None
        parts: list[str] = []
        in_tok = 0
        out_tok = 0
        stream = client.chat.completions.create(
            model=model, messages=messages, max_tokens=max_tokens,
            stream=True, stream_options={"include_usage": True},
        )
        for chunk in stream:
            usage = getattr(chunk, "usage", None)
            if usage is not None:
                in_tok = int(getattr(usage, "prompt_tokens", in_tok) or in_tok)
                out_tok = int(getattr(usage, "completion_tokens", out_tok) or out_tok)
            if not getattr(chunk, "choices", None):
                continue
            delta = chunk.choices[0].delta
            piece = getattr(delta, "content", None)
            if piece:
                if ttft_ms is None:
                    ttft_ms = (time.time() - t0) * 1000.0
                parts.append(piece)
                if on_token:
                    on_token(piece)
        total_ms = (time.time() - t0) * 1000.0
        text = "".join(parts)
        if not out_tok:
            out_tok = _approx_tokens(text)
        # tokens/sec over full wall-clock (end-to-end, fair across providers that
        # stream incrementally vs. return one chunk). Avoids divide-by-near-zero.
        tps = out_tok / (total_ms / 1000.0) if total_ms > 0 else 0.0
        return LLMResult(
            text=text, provider=self.name, model=model,
            input_tokens=in_tok, output_tokens=out_tok,
            ttft_ms=ttft_ms or total_ms, total_ms=total_ms, tokens_per_sec=tps,
        )


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)
