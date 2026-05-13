# 2026-05-13 Hugging Face download 数ランキング

Qwen3.6 35B-A3B / MLX / 4bit / 脱獄系として、今回の ts-bench 対象にした 5 モデルの Hugging Face download 数です。

取得日時: 2026-05-13 11:14 JST 付近  
取得方法: Hugging Face API `https://huggingface.co/api/models/{repo_id}`  
共通 draft: `z-lab/Qwen3.6-35B-A3B-DFlash`

| 順位 | モデル | downloads | likes | gated | private | 手元ベンチ状態 |
| ---: | --- | ---: | ---: | --- | --- | --- |
| 1 | `Youssofal/Qwen3.6-35B-A3B-Abliterated-Heretic-MLX-4bit` | `21,866` | `16` | `false` | `false` | `DDTree` は `3/25` まで有効。`DFlash` は継続ベンチ開始 |
| 2 | `froggeric/Qwen3.6-35B-A3B-Uncensored-Heretic-MLX-4bit` | `3,386` | `1` | `false` | `false` | `DDTree` 有効 `10/25` |
| 3 | `TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit` | `2,193` | `3` | `false` | `false` | 現時点の ts-bench 最良 |
| 4 | `vanch007/Huihui-Qwen3.6-35B-A3B-abliterated-mlx-4bit` | `1,629` | `1` | `false` | `false` | `DDTree` 有効 `10/25` |
| 5 | `nabi-chan/Qwen3.6-35B-A3B-Claude-4.7-Opus-abliterated-MLX-4bit` | `1,096` | `2` | `false` | `false` | `DDTree` 有効 `10/25` |

## 判断

- download 数では `Youssofal` が最大です。`TheCluster` の約 `9.97x` です。
- ただし手元 ts-bench の現時点成績では `TheCluster + DDTree` が最良です。
- `Youssofal` は download 数と非 gated という導入性が強いので、`DFlash + Youssofal` と `DDTree + Youssofal` の TOP_25 継続ベンチ対象にしています。

