"""Tests for the DDTree-to-dflash compatibility boundary."""

import os
import sys
import types

import mlx.core as mx

import ddtree_mlx.dflash_compat as compat


class _FakeTargetOps:
    def __init__(self):
        self.calls = []

    def text_model(self, target_model):
        self.calls.append(("text_model", target_model))
        return "text-model"

    def embed_tokens(self, target_model):
        self.calls.append(("embed_tokens", target_model))
        return lambda token_ids: token_ids + 1

    def logits_from_hidden(self, target_model, hidden_states):
        self.calls.append(("logits_from_hidden", target_model))
        return hidden_states + 2

    def make_cache(
        self,
        target_model,
        *,
        enable_speculative_linear_cache,
        quantize_kv_cache=False,
        target_fa_window=None,
    ):
        self.calls.append(
            (
                "make_cache",
                target_model,
                enable_speculative_linear_cache,
                quantize_kv_cache,
                target_fa_window,
            )
        )
        return ["cache"]

    def forward_with_hidden_capture(
        self,
        target_model,
        *,
        input_ids=None,
        cache=None,
        input_embeddings=None,
        capture_layer_ids=None,
    ):
        self.calls.append(
            (
                "forward_with_hidden_capture",
                target_model,
                tuple(capture_layer_ids or ()),
            )
        )
        return input_ids + 3, {1: input_ids + 4}

    def extract_context_feature(self, captured, target_layer_ids):
        self.calls.append(("extract_context_feature", tuple(target_layer_ids)))
        return compat.extract_context_feature_from_dict(captured, target_layer_ids)

    def arm_rollback(self, cache_entries, *, prefix_len):
        self.calls.append(("arm_rollback", prefix_len))

    def restore_after_acceptance(
        self,
        cache_entries,
        *,
        target_len,
        acceptance_length,
        drafted_tokens=0,
    ):
        self.calls.append(
            (
                "restore_after_acceptance",
                target_len,
                acceptance_length,
                drafted_tokens,
            )
        )
        return 123

    def verify_block(
        self,
        *,
        target_model,
        verify_ids,
        target_cache,
        capture_layer_ids=None,
    ):
        self.calls.append(
            ("verify_block", target_model, tuple(capture_layer_ids or ()))
        )
        return verify_ids + 5, {1: verify_ids + 6}


def test_target_adapter_delegates_to_target_ops():
    fake_ops = _FakeTargetOps()
    original_resolve = compat.resolve_target_ops
    original_bind = compat.bind_draft_to_target
    bind_calls = []

    try:
        compat.resolve_target_ops = lambda target_model: fake_ops
        compat.bind_draft_to_target = (
            lambda draft_model, target_model, *, target_ops: bind_calls.append(
                (draft_model, target_model, target_ops)
            )
        )

        adapter = compat.DFlashTargetAdapter.from_model(
            "target",
            draft_model="draft",
        )
        assert bind_calls == [("draft", "target", fake_ops)]
        assert adapter.text_model() == "text-model"
        assert adapter.make_cache(enable_speculative_linear_cache=True) == ["cache"]

        ids = mx.array([[1, 2]], dtype=mx.uint32)
        logits, captured = adapter.forward_with_hidden_capture(
            input_ids=ids,
            cache=[],
            capture_layer_ids={1},
        )
        mx.eval(logits, captured[1])
        assert logits.tolist() == [[4, 5]]
        assert captured[1].tolist() == [[5, 6]]

        feature = adapter.extract_context_feature(captured, [0])
        mx.eval(feature)
        assert feature.tolist() == [[5, 6]]

        verify_logits, verify_hidden = adapter.verify_block(
            verify_ids=ids,
            target_cache=[],
            capture_layer_ids={1},
        )
        mx.eval(verify_logits, verify_hidden[1])
        assert verify_logits.tolist() == [[6, 7]]
        assert verify_hidden[1].tolist() == [[7, 8]]

        adapter.arm_rollback([], prefix_len=10)
        assert adapter.restore_after_acceptance(
            [],
            target_len=12,
            acceptance_length=3,
            drafted_tokens=4,
        ) == 123
        assert ("arm_rollback", 10) in fake_ops.calls
        assert ("restore_after_acceptance", 12, 3, 4) in fake_ops.calls
    finally:
        compat.resolve_target_ops = original_resolve
        compat.bind_draft_to_target = original_bind


def test_extract_context_feature_from_dict_supports_dict_and_list():
    first = mx.array([[[1.0, 2.0]]])
    second = mx.array([[[3.0, 4.0]]])

    from_dict = compat.extract_context_feature_from_dict(
        {1: first, 3: second},
        [0, 2],
    )
    from_list = compat.extract_context_feature_from_dict(
        [None, first, None, second],
        [0, 2],
    )
    mx.eval(from_dict, from_list)

    assert from_dict.tolist() == [[[1.0, 2.0, 3.0, 4.0]]]
    assert from_list.tolist() == [[[1.0, 2.0, 3.0, 4.0]]]


def test_verify_len_cap_matches_dflash_default_and_env_override():
    fake_ops = _FakeTargetOps()
    original_resolve = compat.resolve_target_ops
    original_env = os.environ.get("DFLASH_VERIFY_LEN_CAP")
    try:
        compat.resolve_target_ops = lambda target_model: fake_ops
        adapter = compat.DFlashTargetAdapter.from_model("target")

        os.environ.pop("DFLASH_VERIFY_LEN_CAP", None)
        assert adapter.resolve_verify_len_cap(8) == 8

        os.environ["DFLASH_VERIFY_LEN_CAP"] = "3"
        assert adapter.resolve_verify_len_cap(8) == 3

        os.environ["DFLASH_VERIFY_LEN_CAP"] = "99"
        assert adapter.resolve_verify_len_cap(8) == 8
    finally:
        compat.resolve_target_ops = original_resolve
        if original_env is None:
            os.environ.pop("DFLASH_VERIFY_LEN_CAP", None)
        else:
            os.environ["DFLASH_VERIFY_LEN_CAP"] = original_env


def test_load_runtime_components_uses_current_dflash_bundle_api():
    original_bundle_module = sys.modules.get("dflash_mlx.runtime.bundle")
    original_context = compat.build_offline_runtime_context
    calls = []

    class _FakeContext:
        verify = "verify-config"

    class _FakeBundle:
        target_model = "target"
        tokenizer = "tokenizer"
        draft_model = "draft"
        resolved_draft_ref = "resolved-draft"

    def fake_load_runtime_bundle(**kwargs):
        calls.append(kwargs)
        return _FakeBundle()

    try:
        compat.build_offline_runtime_context = lambda **kwargs: _FakeContext()
        sys.modules["dflash_mlx.runtime.bundle"] = types.SimpleNamespace(
            load_runtime_bundle=fake_load_runtime_bundle
        )

        loaded = compat.load_runtime_components(
            model_ref="target-ref",
            draft_ref="draft-ref",
            draft_quant="w4",
            verify_mode="adaptive",
            split_full_attention_sdpa=True,
            quantize_kv_cache=True,
        )

        assert loaded == ("target", "tokenizer", "draft", "resolved-draft")
        assert calls == [
            {
                "model_ref": "target-ref",
                "draft_ref": "draft-ref",
                "draft_quant": "w4",
                "verify_config": "verify-config",
                "split_full_attention_sdpa": True,
                "quantize_kv_cache": True,
                "lazy": True,
            }
        ]
    finally:
        compat.build_offline_runtime_context = original_context
        if original_bundle_module is None:
            sys.modules.pop("dflash_mlx.runtime.bundle", None)
        else:
            sys.modules["dflash_mlx.runtime.bundle"] = original_bundle_module


if __name__ == "__main__":
    test_target_adapter_delegates_to_target_ops()
    test_extract_context_feature_from_dict_supports_dict_and_list()
    test_verify_len_cap_matches_dflash_default_and_env_override()
    test_load_runtime_components_uses_current_dflash_bundle_api()
    print("All dflash compat tests passed!")
