#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import time


def _result_text(result: object) -> str:
    text = getattr(result, "text", None)
    if isinstance(text, str):
        return text
    return str(result)


def main() -> int:
    started = time.monotonic()
    try:
        request = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": f"invalid JSON: {exc}"}), file=sys.stderr)
        return 2

    model_id = request.get("model")
    images = request.get("images")
    prompt = request.get("prompt")
    if not isinstance(model_id, str) or not model_id:
        print(json.dumps({"ok": False, "error": "model is required"}), file=sys.stderr)
        return 2
    if not isinstance(images, list) or not images or not all(isinstance(item, str) for item in images):
        print(json.dumps({"ok": False, "error": "images must be a non-empty list of strings"}), file=sys.stderr)
        return 2
    if not isinstance(prompt, str) or not prompt:
        prompt = "Describe the image for a coding agent."

    max_tokens = int(request.get("max_tokens", 768))
    temperature = float(request.get("temperature", 0.0))

    try:
        from mlx_vlm import generate, load
        from mlx_vlm.prompt_utils import apply_chat_template
        from mlx_vlm.utils import load_config

        model, processor = load(model_id)
        config = load_config(model_id)
        formatted_prompt = apply_chat_template(processor, config, prompt, num_images=len(images))
        result = generate(
            model=model,
            processor=processor,
            prompt=formatted_prompt,
            image=images,
            max_tokens=max_tokens,
            temperature=temperature,
            verbose=False,
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": repr(exc)}), file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "model": model_id,
                "text": _result_text(result),
                "duration_ms": round((time.monotonic() - started) * 1000, 3),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
