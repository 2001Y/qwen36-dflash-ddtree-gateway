import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

import dflash_gateway


def make_cached_model(hub: Path, model_id: str) -> None:
    snapshot = hub / f"models--{model_id.replace('/', '--')}" / "snapshots" / "main"
    snapshot.mkdir(parents=True)


def json_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def json_loads(payload: bytes | None) -> object:
    assert payload is not None
    return json.loads(payload)


class DFlashGatewayModelDiscoveryTests(unittest.TestCase):
    def test_hf_hub_cache_takes_precedence_over_hf_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            explicit_hub = Path(tmp) / "explicit-hub"
            hf_home = Path(tmp) / "hf-home"

            with patch.dict(os.environ, {"HF_HUB_CACHE": str(explicit_hub), "HF_HOME": str(hf_home)}, clear=False):
                cache_root = dflash_gateway.hf_hub_cache_root()

        self.assertEqual(cache_root, explicit_hub)

    def test_discovers_local_qwen35_targets_with_shared_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hf_home = Path(tmp) / "hf"
            hub = hf_home / "hub"
            make_cached_model(hub, "TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit")
            make_cached_model(hub, "Youssofal/Qwen3.6-35B-A3B-Abliterated-Heretic-MLX-4bit")
            make_cached_model(hub, "mlx-community/Qwen3.6-35B-A3B-nvfp4")
            make_cached_model(hub, "z-lab/Qwen3.6-35B-A3B-DFlash")

            with patch.dict(os.environ, {"HF_HOME": str(hf_home)}, clear=False):
                specs = dflash_gateway.discover_local_model_specs(Path(tmp))

        self.assertEqual(
            [spec.id for spec in specs],
            [
                "TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit",
                "Youssofal/Qwen3.6-35B-A3B-Abliterated-Heretic-MLX-4bit",
            ],
        )
        self.assertEqual({spec.draft for spec in specs}, {"z-lab/Qwen3.6-35B-A3B-DFlash"})

    def test_reads_plain_env_file_defaults_when_cache_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / ".env").write_text(
                "\n".join(
                    [
                        "DFLASH_MODEL=TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit",
                        "DFLASH_DRAFT=z-lab/Qwen3.6-35B-A3B-DFlash",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"HF_HUB_CACHE": str(workspace / "empty-hub")}, clear=True):
                specs = dflash_gateway.discover_local_model_specs(workspace)

        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0].id, "TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit")
        self.assertEqual(specs[0].draft, "z-lab/Qwen3.6-35B-A3B-DFlash")

    def test_models_payload_is_openai_compatible(self) -> None:
        specs = (
            dflash_gateway.ModelSpec(
                id="TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit",
                draft="z-lab/Qwen3.6-35B-A3B-DFlash",
            ),
        )

        payload = dflash_gateway.models_payload(specs)

        self.assertEqual(payload["object"], "list")
        self.assertEqual(payload["data"][0]["id"], "TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit")
        self.assertEqual(payload["data"][0]["object"], "model")
        self.assertEqual(payload["data"][0]["owned_by"], "dflash")

    def test_responses_payload_converts_to_chat_payload(self) -> None:
        handler = object.__new__(dflash_gateway.GatewayHandler)
        config = SimpleNamespace(
            default_model=dflash_gateway.ModelSpec(
                id="TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit",
                draft="z-lab/Qwen3.6-35B-A3B-DFlash",
            ),
            default_chat_max_tokens=4096,
        )
        handler.server = SimpleNamespace(config=config, logger=SimpleNamespace(write=lambda *args, **kwargs: None))

        payload = handler._responses_payload_to_chat(
            {
                "model": "TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit",
                "instructions": "System note",
                "input": [
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": "Return exactly OK"}],
                    }
                ],
                "max_output_tokens": 8,
                "stream": True,
            }
        )

        self.assertEqual(payload["model"], "TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit")
        self.assertEqual(payload["messages"][0], {"role": "system", "content": "System note"})
        self.assertEqual(payload["messages"][1], {"role": "user", "content": "Return exactly OK"})
        self.assertEqual(payload["max_tokens"], 8)
        self.assertTrue(payload["stream"])

    def test_response_payload_is_responses_compatible(self) -> None:
        handler = object.__new__(dflash_gateway.GatewayHandler)
        payload = handler._make_responses_payload(
            model="TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit",
            text="OK",
            chat_response={"usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4}},
        )

        self.assertEqual(payload["object"], "response")
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["output_text"], "OK")
        self.assertEqual(payload["output"][0]["content"][0]["type"], "output_text")
        self.assertEqual(payload["usage"]["total_tokens"], 4)

    def test_responses_image_input_is_rewritten_with_vlm_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            handler = object.__new__(dflash_gateway.GatewayHandler)
            config = SimpleNamespace(
                workspace=Path(tmp),
                vlm_enabled=True,
                vlm_model="mlx-community/Qwen3.6-35B-A3B-nvfp4",
                vlm_input_dir=Path(tmp) / "vlm-inputs",
            )
            manager = SimpleNamespace(stop_backend=lambda **kwargs: {"stopped": False})
            handler.server = SimpleNamespace(config=config, manager=manager, logger=SimpleNamespace(write=lambda *args, **kwargs: None))
            payload = {
                "model": "TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit",
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "この画面を見て"},
                            {"type": "input_image", "image_url": "data:image/png;base64,aGVsbG8="},
                        ],
                    }
                ],
            }

            with patch.object(handler, "_run_vlm_summary", return_value="OKボタンが見える") as run_vlm:
                rewritten = handler._prepare_multimodal_request(
                    request_id="req-test",
                    route="/v1/responses",
                    content_type="application/json",
                    body=json_bytes(payload),
                )

        self.assertIsNotNone(rewritten)
        data = json_loads(rewritten)
        self.assertEqual(data["input"][0]["content"], [{"type": "input_text", "text": "この画面を見て"}])
        self.assertIn("OKボタンが見える", data["input"][1]["content"][0]["text"])
        run_vlm.assert_called_once()

    def test_chat_image_input_is_rewritten_with_vlm_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            handler = object.__new__(dflash_gateway.GatewayHandler)
            config = SimpleNamespace(
                workspace=Path(tmp),
                vlm_enabled=True,
                vlm_model="mlx-community/Qwen3.6-35B-A3B-nvfp4",
                vlm_input_dir=Path(tmp) / "vlm-inputs",
            )
            manager = SimpleNamespace(stop_backend=lambda **kwargs: {"stopped": False})
            handler.server = SimpleNamespace(config=config, manager=manager, logger=SimpleNamespace(write=lambda *args, **kwargs: None))
            payload = {
                "model": "TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Analyze this"},
                            {"type": "image_url", "image_url": {"url": "data:image/png;base64,aGVsbG8="}},
                        ],
                    }
                ],
            }

            with patch.object(handler, "_run_vlm_summary", return_value="A screenshot with an error"):
                rewritten = handler._prepare_multimodal_request(
                    request_id="req-test",
                    route="/v1/chat/completions",
                    content_type="application/json",
                    body=json_bytes(payload),
                )

        self.assertIsNotNone(rewritten)
        data = json_loads(rewritten)
        self.assertEqual(data["messages"][0]["content"], [{"type": "text", "text": "Analyze this"}])
        self.assertEqual(data["messages"][1]["role"], "user")
        self.assertIn("A screenshot with an error", data["messages"][1]["content"])


if __name__ == "__main__":
    unittest.main()
