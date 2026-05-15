#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import types
from typing import Any


CONTRACT_EMIT_ENV = "AGENTIR_CONTRACT_EMIT"
SAFE_PROVIDER_CHAIN_METHODS = {
    "bind",
    "bind_functions",
    "bind_tools",
    "with_config",
    "with_fallbacks",
    "with_retry",
    "with_structured_output",
}
PROVIDER_RUNTIME_METHODS = {
    "__call__",
    "ainvoke",
    "astream",
    "batch",
    "invoke",
    "stream",
}


class ContractEmitProviderRuntimeError(RuntimeError):
    pass


def contract_emit_enabled() -> bool:
    raw = os.environ.get(CONTRACT_EMIT_ENV, "").strip().lower()
    return raw not in {"", "0", "false", "no"}


def contract_to_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "build_contract"):
        value = value.build_contract()
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    if not isinstance(value, dict):
        raise TypeError("LangGraph contract source did not resolve to a contract dictionary.")
    return value


def install_langgraph_compat_if_needed() -> None:
    try:
        import langgraph  # noqa: F401
        import langchain_core  # noqa: F401
        return
    except ModuleNotFoundError:
        pass

    langchain_core = types.ModuleType("langchain_core")
    messages = types.ModuleType("langchain_core.messages")

    class _Message:
        def __init__(self, content: str = "", **kwargs: Any):
            self.content = content
            self.additional_kwargs = kwargs

    class HumanMessage(_Message):
        pass

    class AIMessage(_Message):
        pass

    messages.HumanMessage = HumanMessage
    messages.AIMessage = AIMessage
    langchain_core.messages = messages

    langgraph = types.ModuleType("langgraph")
    graph_module = types.ModuleType("langgraph.graph")
    message_module = types.ModuleType("langgraph.graph.message")
    checkpoint_module = types.ModuleType("langgraph.checkpoint")
    checkpoint_memory_module = types.ModuleType("langgraph.checkpoint.memory")

    START = "START"
    END = "END"

    class StateGraph:
        def __init__(self, state_type: Any):
            self.state_type = state_type
            self.nodes: dict[str, Any] = {}
            self.edges: list[tuple[str, str]] = []
            self.entry_point: str | None = None
            self.finish_points: list[str] = []

        def add_node(self, name: str, fn: Any) -> None:
            self.nodes[name] = fn

        def add_edge(self, src: str, dst: str) -> None:
            self.edges.append((src, dst))

        def add_conditional_edges(self, *args: Any, **kwargs: Any) -> None:
            return None

        def set_entry_point(self, name: str) -> None:
            self.entry_point = name

        def set_finish_point(self, name: str) -> None:
            self.finish_points.append(name)

        def compile(self, *args: Any, **kwargs: Any) -> "StateGraph":
            return self

    class InMemorySaver:
        pass

    def add_messages(left: list[Any] | None, right: list[Any] | None) -> list[Any]:
        return list(left or []) + list(right or [])

    graph_module.StateGraph = StateGraph
    graph_module.START = START
    graph_module.END = END
    graph_module.message = message_module
    message_module.add_messages = add_messages
    checkpoint_memory_module.InMemorySaver = InMemorySaver
    checkpoint_module.memory = checkpoint_memory_module

    sys.modules.setdefault("langchain_core", langchain_core)
    sys.modules.setdefault("langchain_core.messages", messages)
    sys.modules.setdefault("langgraph", langgraph)
    sys.modules.setdefault("langgraph.graph", graph_module)
    sys.modules.setdefault("langgraph.graph.message", message_module)
    sys.modules.setdefault("langgraph.checkpoint", checkpoint_module)
    sys.modules.setdefault("langgraph.checkpoint.memory", checkpoint_memory_module)


def _provider_runtime_error(operation: str) -> ContractEmitProviderRuntimeError:
    return ContractEmitProviderRuntimeError(
        "LangGraph contract emission cannot execute provider calls at import time while "
        f"{CONTRACT_EMIT_ENV}=1; blocked operation: {operation}."
    )


class _ProviderStub:
    _factory_name = "provider"

    def __init__(self, *args: Any, **kwargs: Any):
        self._args = args
        self._kwargs = kwargs

    def __getattr__(self, name: str) -> Any:
        if name in SAFE_PROVIDER_CHAIN_METHODS:
            def _safe_chain(*args: Any, **kwargs: Any) -> "_ProviderStub":
                del args, kwargs
                return self

            return _safe_chain
        raise AttributeError(name)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise _provider_runtime_error(f"{self._factory_name}.__call__")

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise _provider_runtime_error(f"{self._factory_name}.invoke")

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise _provider_runtime_error(f"{self._factory_name}.ainvoke")

    def stream(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise _provider_runtime_error(f"{self._factory_name}.stream")

    async def astream(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise _provider_runtime_error(f"{self._factory_name}.astream")

    def batch(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise _provider_runtime_error(f"{self._factory_name}.batch")


def _provider_class(name: str) -> type[_ProviderStub]:
    class _SpecificProviderStub(_ProviderStub):
        _factory_name = name

    _SpecificProviderStub.__name__ = name
    return _SpecificProviderStub


def install_provider_compat_if_needed() -> None:
    if not contract_emit_enabled():
        return

    langchain_openai = types.ModuleType("langchain_openai")
    langchain_openai.ChatOpenAI = _provider_class("ChatOpenAI")
    sys.modules["langchain_openai"] = langchain_openai

    langchain_anthropic = types.ModuleType("langchain_anthropic")
    langchain_anthropic.ChatAnthropic = _provider_class("ChatAnthropic")
    sys.modules["langchain_anthropic"] = langchain_anthropic

    langchain = sys.modules.get("langchain")
    if langchain is None:
        langchain = types.ModuleType("langchain")
        langchain.__path__ = []  # type: ignore[attr-defined]
        sys.modules["langchain"] = langchain

    chat_models = types.ModuleType("langchain.chat_models")
    init_chat_model_stub = _provider_class("init_chat_model")

    def init_chat_model(*args: Any, **kwargs: Any) -> _ProviderStub:
        return init_chat_model_stub(*args, **kwargs)

    chat_models.init_chat_model = init_chat_model
    langchain.chat_models = chat_models
    sys.modules["langchain.chat_models"] = chat_models


def prepare_contract_emit_environment() -> None:
    os.environ.setdefault(CONTRACT_EMIT_ENV, "1")
    install_langgraph_compat_if_needed()
    install_provider_compat_if_needed()
