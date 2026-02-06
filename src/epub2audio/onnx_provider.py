"""Shared ONNX execution provider resolution helpers."""

from __future__ import annotations

import platform


def get_available_onnx_providers() -> list[str]:
    try:
        import onnxruntime as ort  # type: ignore

        return list(ort.get_available_providers())
    except Exception:
        return []


def resolve_onnx_provider_chain(
    requested: str,
    *,
    available: list[str] | None = None,
    platform_name: str | None = None,
) -> list[str]:
    value = (requested or "auto").strip()
    providers = list(available) if available is not None else get_available_onnx_providers()
    system = (platform_name or platform.system()).lower()

    if value and value.lower() != "auto":
        parts = [part.strip() for part in value.split(",") if part.strip()]
        return parts if parts else _default_chain(providers, system)
    return _default_chain(providers, system)


def render_onnx_provider_resolution(
    requested: str,
    *,
    available: list[str] | None = None,
    platform_name: str | None = None,
) -> str:
    value = (requested or "auto").strip() or "auto"
    providers = list(available) if available is not None else get_available_onnx_providers()
    system = (platform_name or platform.system()).lower()

    if value.lower() != "auto":
        return f"Requested provider(s): {value}."
    if not providers:
        return "No providers reported by onnxruntime."

    resolved = resolve_onnx_provider_chain("auto", available=providers, platform_name=system)
    if system == "linux":
        return f"Auto resolved to {resolved[0]} on Linux."
    return f"Auto resolved to {resolved[0]}."


def _default_chain(available: list[str], platform_name: str) -> list[str]:
    if not available:
        return ["CPUExecutionProvider"]

    if platform_name == "linux":
        return ["CPUExecutionProvider"] if "CPUExecutionProvider" in available else [available[0]]

    preferred = [
        "CoreMLExecutionProvider",
        "CUDAExecutionProvider",
        "DmlExecutionProvider",
        "ROCMExecutionProvider",
        "CPUExecutionProvider",
    ]
    selected = [provider for provider in preferred if provider in available]
    return selected or ["CPUExecutionProvider"]
