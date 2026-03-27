from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from typing import Any

import requests

try:
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatPromptTemplate = None
    ChatOpenAI = None


class AgentLLMRunner:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.framework = str(self.config.get("framework", "langchain"))
        self.base_url = (self.config.get("base_url") or "").rstrip("/")
        self.model = self.config.get("model", "")
        self.timeout_seconds = int(self.config.get("timeout_seconds", 60))
        self.temperature = float(self.config.get("temperature", 0))
        self.api_key = self._resolve_api_key()
        self.strict_mode = bool(self.config.get("strict_mode", False))
        self.enabled = bool(self.config.get("enabled", False) and self.base_url and self.model and self.api_key)
        self._chat_model = self._build_chat_model()

    def complete_json(self, *, agent_name: str, prompt: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        self.ensure_available(agent_name)
        if not self.enabled:
            return None
        if self._chat_model and ChatPromptTemplate is not None:
            return self._complete_json_langchain(agent_name=agent_name, prompt=prompt, payload=payload)
        body = {
            "model": self.model,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "agent_name": agent_name,
                            "input": payload,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        return self._parse_json(content)

    def complete_structured(self, *, agent_name: str, prompt: str, payload: dict[str, Any], schema: type[Any]) -> dict[str, Any] | None:
        self.ensure_available(agent_name)
        if not self.enabled or not self._chat_model or ChatPromptTemplate is None:
            return None
        chain = self._build_prompt() | self._chat_model.with_structured_output(schema)
        result = chain.invoke(self._chain_input(agent_name=agent_name, prompt=prompt, payload=payload))
        if hasattr(result, "model_dump"):
            return result.model_dump()
        if isinstance(result, dict):
            return result
        return None

    def _resolve_api_key(self) -> str:
        if self.config.get("api_key"):
            return str(self.config["api_key"])
        env_name = self.config.get("api_key_env", "AGENT_LLM_API_KEY")
        return os.getenv(env_name, "")

    def ensure_available(self, agent_name: str) -> None:
        if self.strict_mode and not self.enabled:
            raise RuntimeError(
                f"LLM strict mode is enabled, but '{agent_name}' cannot run because the LLM model configuration is incomplete."
            )

    def _build_chat_model(self) -> Any | None:
        if not self.enabled or self.framework != "langchain" or ChatOpenAI is None:
            return None
        return ChatOpenAI(
            model=self.model,
            temperature=self.temperature,
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout_seconds,
        )

    def _complete_json_langchain(self, *, agent_name: str, prompt: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        chain = self._build_prompt() | self._chat_model.bind(response_format={"type": "json_object"})
        response = chain.invoke(self._chain_input(agent_name=agent_name, prompt=prompt, payload=payload))
        content = response.content if hasattr(response, "content") else str(response)
        return self._parse_json(content)

    def _build_prompt(self) -> Any:
        return ChatPromptTemplate.from_messages(
            [
                ("system", "{system_prompt}"),
                ("user", "{user_payload}"),
            ]
        )

    def _chain_input(self, *, agent_name: str, prompt: str, payload: dict[str, Any]) -> dict[str, str]:
        return {
            "system_prompt": f"{prompt}\n\nReturn JSON only.",
            "user_payload": "Respond with a JSON object only.\n"
            + json.dumps({"agent_name": agent_name, "input": payload}, ensure_ascii=False),
        }

    def _parse_json(self, content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3:
                text = "\n".join(lines[1:-1]).strip()
        return json.loads(text)


def decision_payload(data: Any) -> Any:
    if is_dataclass(data):
        return asdict(data)
    return data


def runner_is_strict(runner: Any | None) -> bool:
    return bool(getattr(runner, "strict_mode", False))


def ensure_runner_available(runner: Any | None, agent_name: str) -> None:
    if runner is None:
        return
    ensure = getattr(runner, "ensure_available", None)
    if callable(ensure):
        ensure(agent_name)
