# 2026-05-13 精度・速度・download 数ランキング

作成日時: 2026-05-13 17:39 JST

## 前提

- 対象: Qwen3.6 35B-A3B / MLX / 4bit / 脱獄系モデルと、DFlash / DDTree の手元 ts-bench 結果。
- 精度の主指標: `TOP_25 Score = 通常成功数 / 25`。
- 速度の主指標: 有効通常結果の平均 `totalDuration`。低いほど速い。
- download 数: Hugging Face API `https://huggingface.co/api/models/{repo_id}` を 2026-05-13 17:39 JST に再取得。
- `20260513-142940` の submodule 復元前 invalid 結果はランキングから除外し、`20260513-162247` の invalid rerun で置き換える。

## 1. 精度ランキング

coding agent 用途ではこの順位を最優先する。未到達、通常失敗、infra failure は TOP_25 Score 上 0 点扱い。

| 順位 | 組み合わせ | TOP_25 Score | 通常成功 | 有効通常結果 | 通常失敗 | infra failure | 備考 |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | `DDTree + TheCluster` | `28.0%` | `7/25` | `10` | `3` | `1` | 最良。valid-only は `70.0%` |
| 2 | `DDTree + Youssofal` | `24.0%` | `6/25` | `23` | `17` | `2` | download 数最大だが精度は TheCluster 未満 |
| 3 | `DFlash + TheCluster` | `20.0%` | `5/25` | `10` | `5` | `1` | 通常 DFlash の比較基準 |
| 3 | `DDTree + froggeric` | `20.0%` | `5/25` | `10` | `5` | `1` | TheCluster DFlash と同率 |
| 3 | `DDTree + vanch007` | `20.0%` | `5/25` | `10` | `5` | `1` | TheCluster DFlash と同率 |
| 6 | `DDTree + nabi-chan` | `16.0%` | `4/25` | `10` | `6` | `1` | tokenizer warning あり |
| 6 | `DFlash + Youssofal` | `16.0%` | `4/25` | `12` | `8` | `1` | crash 後結果を含むため低信頼 |

倍率:

- `DDTree + TheCluster` は `DDTree + Youssofal` より成功数で `1.17x`、TOP_25 Score で `1.17x` 高い。
- `DDTree + TheCluster` は `DFlash + TheCluster` / `DDTree + froggeric` / `DDTree + vanch007` より成功数で `1.40x` 高い。
- `DDTree + TheCluster` は `DDTree + nabi-chan` / `DFlash + Youssofal` より成功数で `1.75x` 高い。

## 2. 速度ランキング

速度はマシン状態の影響が大きいので、採用判断では精度より下位に置く。`DFlash + Youssofal` は最速値だが crash 後結果を含むため低信頼。

| 順位 | 組み合わせ | 平均時間 | 合計時間 | 有効通常結果 | 通常成功 | 信頼度 |
| ---: | --- | ---: | ---: | ---: | ---: | --- |
| 1 | `DFlash + Youssofal` | `130.9s` | `1570.6s` | `12` | `4` | 低。crash 後結果を含む |
| 2 | `DFlash + TheCluster` | `149.0s` | `1490.3s` | `10` | `5` | 中。通常 DFlash 比較基準 |
| 3 | `DDTree + nabi-chan` | `155.0s` | `1549.6s` | `10` | `4` | 中 |
| 4 | `DDTree + vanch007` | `161.7s` | `1616.7s` | `10` | `5` | 中 |
| 5 | `DDTree + froggeric` | `172.9s` | `1729.1s` | `10` | `5` | 中 |
| 6 | `DDTree + TheCluster` | `179.4s` | `1794.0s` | `10` | `7` | 高。精度最良 |
| 7 | `DDTree + Youssofal` | `214.7s` | `4937.4s` | `23` | `6` | 中。最も広く分類済み |

速度倍率:

- raw speed だけなら `DFlash + Youssofal` は `DDTree + TheCluster` より `1.37x` 速いが、低信頼。
- 比較基準として見るなら `DFlash + TheCluster` は `DDTree + TheCluster` より `1.20x` 速い。
- ただし `DDTree + TheCluster` は `DFlash + TheCluster` より精度が `1.40x` 高い。

## 3. download 数ランキング

| 順位 | モデル | downloads | likes | gated | private | TheCluster 比 |
| ---: | --- | ---: | ---: | --- | --- | ---: |
| 1 | `Youssofal/Qwen3.6-35B-A3B-Abliterated-Heretic-MLX-4bit` | `22,901` | `16` | `false` | `false` | `10.22x` |
| 2 | `froggeric/Qwen3.6-35B-A3B-Uncensored-Heretic-MLX-4bit` | `3,639` | `1` | `false` | `false` | `1.62x` |
| 3 | `TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit` | `2,241` | `3` | `false` | `false` | `1.00x` |
| 4 | `vanch007/Huihui-Qwen3.6-35B-A3B-abliterated-mlx-4bit` | `1,651` | `1` | `false` | `false` | `0.74x` |
| 5 | `nabi-chan/Qwen3.6-35B-A3B-Claude-4.7-Opus-abliterated-MLX-4bit` | `1,192` | `2` | `false` | `false` | `0.53x` |

download 数では `Youssofal` が最大。`TheCluster` の `10.22x`、2 位の `froggeric` の `6.29x`。

## 4. 結論

| 観点 | 1 位 | 判断 |
| --- | --- | --- |
| 精度 | `DDTree + TheCluster` | 採用候補。TOP_25 Score `28.0%` で最良 |
| 速度 | `DFlash + Youssofal` | raw speed は最速だが低信頼。実用比較では `DFlash + TheCluster` |
| download 数 | `Youssofal` | 人気・導入性は最大。ただし精度は TheCluster 未満 |

総合採用は引き続き次。

```text
TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit
+ z-lab/Qwen3.6-35B-A3B-DFlash
+ DDTree
```

