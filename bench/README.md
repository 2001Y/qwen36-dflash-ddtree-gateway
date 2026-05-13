# bench

このフォルダは、元ワークスペースで行った Qwen3.6 35B-A3B 脱獄系 + DFlash / DDTree 検証の公開用コピーです。

## 内容

- `workspace-files/`
  - `benchmark-ts-bench-matrix.py`
  - `start-dflash.command`
  - `start-dflash-backend.command`
  - `start-dflash-gateway.command`
- `ddtree-mlx/`
  - このマシンで DFlash API 変更に合わせて調整した DDTree 実験実装
  - `tests/test_dflash_compat.py` などのテストを含む
- `docs/`
  - `tsbench-rankings-20260513.md`
- `artifacts/`
  - 主要な `summary.json`

## 含めていないもの

- Hugging Face model cache
- `.venv`
- `.uv-cache`
- 巨大な `results.jsonl`
- iCloud FileProvider 上で未実体化だったファイル

再計測する場合は、`workspace-files/benchmark-ts-bench-matrix.py` を出発点にし、candidate ごとに gateway / backend / artifact directory を分離してください。同一 gateway の crash circuit が後続 candidate に影響すると、比較が汚染されます。

