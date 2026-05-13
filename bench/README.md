# bench

このフォルダは、元ワークスペースで行った Qwen3.6 35B-A3B 脱獄系 + DFlash / DDTree 検証の公開用コピーです。

## 内容

- `workspace-files/`
  - `benchmark-ts-bench-matrix.py`
  - `benchmark-engine-matrix-local.py`
  - `run-youssofal-top25-bench-20260513.sh`
  - `start-dflash.command`
  - `start-dflash-backend.command`
  - `start-dflash-gateway.command`
- `ddtree-mlx/`
  - このマシンで DFlash API 変更に合わせて調整した DDTree 実験実装
  - `tests/test_dflash_compat.py` などのテストを含む
- `docs/`
  - `tsbench-rankings-20260513.md`
  - `hf-download-rankings-20260513.md`
- `artifacts/`
  - 主要な `summary.json`

## 含めていないもの

- Hugging Face model cache
- `.venv`
- `.uv-cache`
- 巨大な `results.jsonl`
- iCloud FileProvider 上で未実体化だったファイル

再計測する場合は、`workspace-files/benchmark-ts-bench-matrix.py` を出発点にし、candidate ごとに gateway / backend / artifact directory を分離してください。同一 gateway の crash circuit が後続 candidate に影響すると、比較が汚染されます。

## ベンチの成否

ts-bench matrix は比較に使える結果を取得できていますが、TOP_25 を完全完走した組み合わせはありません。

- `DDTree + TheCluster`: 有効 `10/25`、通常成功 `7`、通常失敗 `3`、infra failure `1`
- `DFlash + TheCluster`: 有効 `10/25`、通常成功 `5`、通常失敗 `5`、infra failure `1`
- `DDTree + Youssofal`: 有効 `3/25`、通常成功 `2`、通常失敗 `1`、infra failure `0`

したがって「ベンチ実行自体は成功したが、全パターン・全問題の完走成功ではない」という扱いです。
