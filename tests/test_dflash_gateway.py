import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import dflash_gateway


def make_cached_model(hub: Path, model_id: str) -> None:
    snapshot = hub / f"models--{model_id.replace('/', '--')}" / "snapshots" / "main"
    snapshot.mkdir(parents=True)


class DFlashGatewayModelDiscoveryTests(unittest.TestCase):
    def test_discovers_local_qwen35_targets_with_shared_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hf_home = Path(tmp) / "hf"
            hub = hf_home / "hub"
            make_cached_model(hub, "TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit")
            make_cached_model(hub, "Youssofal/Qwen3.6-35B-A3B-Abliterated-Heretic-MLX-4bit")
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


if __name__ == "__main__":
    unittest.main()
