from __future__ import annotations

from epub2audio.onnx_provider import render_onnx_provider_resolution, resolve_onnx_provider_chain


def test_resolve_provider_chain_linux_prefers_cpu() -> None:
    resolved = resolve_onnx_provider_chain(
        "auto",
        available=["CUDAExecutionProvider", "CPUExecutionProvider"],
        platform_name="linux",
    )
    assert resolved == ["CPUExecutionProvider"]


def test_resolve_provider_chain_non_linux_prefers_coreml() -> None:
    resolved = resolve_onnx_provider_chain(
        "auto",
        available=["CPUExecutionProvider", "CoreMLExecutionProvider"],
        platform_name="darwin",
    )
    assert resolved == ["CoreMLExecutionProvider", "CPUExecutionProvider"]


def test_resolve_provider_chain_explicit_request() -> None:
    resolved = resolve_onnx_provider_chain(
        "CUDAExecutionProvider,CPUExecutionProvider",
        available=["CPUExecutionProvider"],
        platform_name="linux",
    )
    assert resolved == ["CUDAExecutionProvider", "CPUExecutionProvider"]


def test_render_provider_resolution_linux_message() -> None:
    message = render_onnx_provider_resolution(
        "auto",
        available=["CPUExecutionProvider", "CUDAExecutionProvider"],
        platform_name="linux",
    )
    assert "Auto resolved to CPUExecutionProvider on Linux." == message
