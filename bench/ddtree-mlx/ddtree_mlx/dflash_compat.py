"""Compatibility boundary between DDTree and dflash-mlx.

DDTree needs target-model internals for tree verification, but dflash-mlx
reorganized those internals behind TargetOps. Keep that dependency in one
module so DDTree's tree logic does not import private dflash_mlx.runtime names.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

import mlx.core as mx

from dflash_mlx.engine.events import SummaryEvent, is_engine_event
from dflash_mlx.engine.acceptance import match_acceptance_length
from dflash_mlx.engine.target_ops import bind_draft_to_target, resolve_target_ops
from dflash_mlx.engine.sampling import build_suppress_token_mask, greedy_tokens_with_mask
from dflash_mlx.runtime import get_stop_token_ids
from dflash_mlx.runtime.context import build_offline_runtime_context

HYBRID_SDPA_EXACT_KV_THRESHOLD = 1024


def split_sdpa_output(*args: Any, **kwargs: Any) -> Any:
    from dflash_mlx.engine.target_qwen_gdn import _split_sdpa_output

    return _split_sdpa_output(*args, **kwargs)


def _verify_len_cap_from_env(block_tokens: int) -> int:
    requested = int(os.environ.get("DFLASH_VERIFY_LEN_CAP", "0") or 0)
    if requested <= 0:
        return int(block_tokens)
    return max(1, min(int(block_tokens), requested))


def eval_logits_and_captured(
    logits: mx.array,
    captured: list[mx.array] | dict[int, mx.array],
) -> None:
    if isinstance(captured, dict):
        mx.eval(logits, *captured.values())
    else:
        mx.eval(logits, *captured)


def target_text_model(target_model: Any) -> Any:
    return resolve_target_ops(target_model).text_model(target_model)


def target_embed_tokens(target_model: Any) -> Any:
    return resolve_target_ops(target_model).embed_tokens(target_model)


def logits_from_hidden(target_model: Any, hidden_states: mx.array) -> mx.array:
    return resolve_target_ops(target_model).logits_from_hidden(
        target_model,
        hidden_states,
    )


def target_forward_with_hidden_states(
    target_model: Any,
    *,
    input_ids: Optional[mx.array] = None,
    cache: Optional[list[Any]] = None,
    input_embeddings: Optional[mx.array] = None,
    capture_layer_ids: Optional[set[int]] = None,
) -> tuple[mx.array, list[mx.array] | dict[int, mx.array]]:
    return resolve_target_ops(target_model).forward_with_hidden_capture(
        target_model,
        input_ids=input_ids,
        cache=cache,
        input_embeddings=input_embeddings,
        capture_layer_ids=capture_layer_ids,
    )


def extract_context_feature_from_dict(
    captured: list[mx.array] | dict[int, mx.array],
    target_layer_ids: list[int],
) -> mx.array:
    selected = [captured[int(layer_id) + 1] for layer_id in target_layer_ids]
    return mx.concatenate(selected, axis=-1)


def make_target_cache(
    target_model: Any,
    *,
    enable_speculative_linear_cache: bool,
    quantize_kv_cache: bool = False,
    target_fa_window: Optional[int] = None,
) -> list[Any]:
    return resolve_target_ops(target_model).make_cache(
        target_model,
        enable_speculative_linear_cache=enable_speculative_linear_cache,
        quantize_kv_cache=quantize_kv_cache,
        target_fa_window=target_fa_window,
    )


def make_draft_cache(
    draft_model: Any,
    *,
    sink_size: int,
    window_size: int,
) -> list[Any]:
    from dflash_mlx.draft_backend import make_draft_backend

    return make_draft_backend().make_cache(
        draft_model=draft_model,
        sink_size=int(sink_size),
        window_size=int(window_size),
    )


def resolve_draft_ref(model_ref: str, draft_ref: str | None = None) -> str | None:
    from dflash_mlx.runtime.registry import resolve_optional_draft_ref

    return resolve_optional_draft_ref(str(model_ref), draft_ref)


def load_runtime_components(
    *,
    model_ref: str,
    draft_ref: str | None = None,
    draft_quant: str | None = None,
    verify_mode: str | None = "auto",
    split_full_attention_sdpa: bool | None = None,
    quantize_kv_cache: bool = False,
) -> tuple[Any, Any, Any, str]:
    """Load target/tokenizer/draft using the current dflash-mlx runtime API."""
    from dflash_mlx.runtime.bundle import load_runtime_bundle

    runtime_context = build_offline_runtime_context(verify_mode=verify_mode)
    bundle = load_runtime_bundle(
        model_ref=model_ref,
        draft_ref=draft_ref,
        draft_quant=draft_quant,
        verify_config=runtime_context.verify,
        split_full_attention_sdpa=split_full_attention_sdpa,
        quantize_kv_cache=quantize_kv_cache,
        lazy=True,
    )
    return (
        bundle.target_model,
        bundle.tokenizer,
        bundle.draft_model,
        bundle.resolved_draft_ref,
    )


def generate_dflash_once(
    *,
    target_model: Any,
    tokenizer: Any,
    draft_model: Any,
    prompt: str,
    max_new_tokens: int,
    use_chat_template: bool = False,
    stop_token_ids: Optional[list[int]] = None,
    suppress_token_ids: Optional[list[int]] = None,
    prompt_tokens_override: Optional[list[int]] = None,
    target_fa_window: int = 0,
    prefill_step_size: Optional[int] = None,
    draft_sink_size: int = 64,
    draft_window_size: int = 1024,
    verify_len_cap: int = 0,
    verify_mode: str = "auto",
) -> dict[str, Any]:
    from dflash_mlx.runtime import stream_dflash_generate

    runtime_context = build_offline_runtime_context(
        target_fa_window=int(target_fa_window),
        prefill_step_size=prefill_step_size,
        draft_sink_size=int(draft_sink_size),
        draft_window_size=int(draft_window_size),
        verify_len_cap=int(verify_len_cap),
        verify_mode=str(verify_mode),
    )
    target_adapter = DFlashTargetAdapter.from_model(
        target_model,
        draft_model=draft_model,
    )
    from dflash_mlx.draft_backend import make_draft_backend

    draft_backend = make_draft_backend()
    summary: dict[str, Any] | None = None
    for event in stream_dflash_generate(
        target_model=target_model,
        target_ops=target_adapter.target_ops,
        tokenizer=tokenizer,
        draft_model=draft_model,
        draft_backend=draft_backend,
        prompt=prompt,
        max_new_tokens=int(max_new_tokens),
        use_chat_template=bool(use_chat_template),
        stop_token_ids=stop_token_ids,
        suppress_token_ids=suppress_token_ids,
        prompt_tokens_override=prompt_tokens_override,
        runtime_context=runtime_context,
    ):
        if isinstance(event, SummaryEvent):
            summary = event.to_payload()
        elif not is_engine_event(event):
            raise TypeError(f"Unsupported DFlash engine event: {type(event).__name__}")
    if summary is None:
        raise RuntimeError("dflash generation ended without a summary event")
    return summary


@dataclass(frozen=True)
class DFlashTargetAdapter:
    target_model: Any
    target_ops: Any

    @classmethod
    def from_model(
        cls,
        target_model: Any,
        draft_model: Any | None = None,
    ) -> "DFlashTargetAdapter":
        target_ops = resolve_target_ops(target_model)
        if draft_model is not None:
            bind_draft_to_target(draft_model, target_model, target_ops=target_ops)
        return cls(target_model=target_model, target_ops=target_ops)

    def text_model(self) -> Any:
        return self.target_ops.text_model(self.target_model)

    def embed_tokens(self) -> Any:
        return self.target_ops.embed_tokens(self.target_model)

    def logits_from_hidden(self, hidden_states: mx.array) -> mx.array:
        return self.target_ops.logits_from_hidden(self.target_model, hidden_states)

    def make_cache(
        self,
        *,
        enable_speculative_linear_cache: bool,
        quantize_kv_cache: bool = False,
        target_fa_window: Optional[int] = None,
    ) -> list[Any]:
        return self.target_ops.make_cache(
            self.target_model,
            enable_speculative_linear_cache=enable_speculative_linear_cache,
            quantize_kv_cache=quantize_kv_cache,
            target_fa_window=target_fa_window,
        )

    def forward_with_hidden_capture(
        self,
        *,
        input_ids: Optional[mx.array] = None,
        cache: Optional[list[Any]] = None,
        input_embeddings: Optional[mx.array] = None,
        capture_layer_ids: Optional[set[int]] = None,
    ) -> tuple[mx.array, list[mx.array] | dict[int, mx.array]]:
        return self.target_ops.forward_with_hidden_capture(
            self.target_model,
            input_ids=input_ids,
            cache=cache,
            input_embeddings=input_embeddings,
            capture_layer_ids=capture_layer_ids,
        )

    def extract_context_feature(
        self,
        captured: list[mx.array] | dict[int, mx.array],
        target_layer_ids: list[int],
    ) -> mx.array:
        return self.target_ops.extract_context_feature(captured, target_layer_ids)

    def arm_rollback(self, cache_entries: list[Any], *, prefix_len: int) -> None:
        self.target_ops.arm_rollback(cache_entries, prefix_len=int(prefix_len))

    def restore_after_acceptance(
        self,
        cache_entries: list[Any],
        *,
        target_len: int,
        acceptance_length: int,
        drafted_tokens: int = 0,
    ) -> int:
        return int(
            self.target_ops.restore_after_acceptance(
                cache_entries,
                target_len=int(target_len),
                acceptance_length=int(acceptance_length),
                drafted_tokens=int(drafted_tokens),
            )
        )

    def verify_block(
        self,
        *,
        verify_ids: mx.array,
        target_cache: list[Any],
        capture_layer_ids: Optional[set[int]] = None,
    ) -> tuple[mx.array, list[mx.array] | dict[int, mx.array]]:
        return self.target_ops.verify_block(
            target_model=self.target_model,
            verify_ids=verify_ids,
            target_cache=target_cache,
            capture_layer_ids=capture_layer_ids,
        )

    def resolve_verify_len_cap(self, block_tokens: int) -> int:
        return _verify_len_cap_from_env(block_tokens)
