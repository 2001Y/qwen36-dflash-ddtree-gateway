# 2026-05-13 ts-bench 観点別ランキング

このメモは、Qwen3.6 35B-A3B 脱獄系候補の DFlash / DDTree 再実行結果を、複数観点でランキングしたものです。

## 前提

正本 artifact:

- `.artifacts/dflash/ts-bench-matrix/20260513-000000-rerun-all-failed-qwen35-a3b/`
- `.artifacts/dflash/ts-bench-matrix/20260513-014500-rerun-ddtree-system-gate-rest/`
- `.artifacts/dflash/ts-bench-matrix/20260513-031000-rerun-dflash-thecluster-dnd/`
- `.artifacts/dflash/ts-bench-matrix/20260513-031500-rerun-ddtree-dnd-failures/`
- `.artifacts/dflash/ts-bench-matrix/20260513-032500-rerun-ddtree-youssofal-bank-account/`
- `.artifacts/dflash/ts-bench-matrix/20260513-034000-rerun-ddtree-nabichan-top25/`
- `.artifacts/dflash/ts-bench-matrix/20260513-121353-youssofal-top25-continuation/`
- `.artifacts/dflash/ts-bench-matrix/20260513-124434-youssofal-ddtree-top25-continuation/`
- `.artifacts/dflash/ts-bench-matrix/20260513-125348-youssofal-ddtree-rest-per-exercise/`
- `.artifacts/dflash/ts-bench-matrix/20260513-142120-youssofal-ddtree-rest2-per-exercise/` は `/private/tmp/mlx-dflash-bench-venv` 消失による infra failure。
- `.artifacts/dflash/ts-bench-matrix/20260513-142638-youssofal-ddtree-rest2-per-exercise/` は `/private/tmp/ts-bench` 消失による infra failure。
- `.artifacts/dflash/ts-bench-matrix/20260513-142940-youssofal-ddtree-rest2-per-exercise/` は `exercism-typescript` submodule 復元前の前半結果を含む。`spiral-matrix` と `transpose` は通常完了として反映し、`house` から `robot-name` までは無効分として完了後に再実行する。

集計ルール:

- 共通 10 exercise を有効完了した組み合わせを主ランキング対象にする。
- 同一 exercise に後続の `infra_failed` がある場合、ts-bench JSON があっても通常結果から除外する。
- `dnd-character` は DFlash / DDTree とも Metal crash を再現したため、精度ランキングには混ぜない。
- `Youssofal + DDTree` は追加評価中だが、現時点では `bank-account` で infra failure が出ているため参考枠にする。
- 速度は system state の影響が大きいため、採用判断では `精度 > 成功効率 > 安定性 > 平均速度` の順で見る。

## 2026-05-13 追記: Youssofal 継続結果

`Youssofal/Qwen3.6-35B-A3B-Abliterated-Heretic-MLX-4bit` は download 数が最大のため、追加で DFlash / DDTree を継続評価した。

### `DFlash + Youssofal`

- artifact: `.artifacts/dflash/ts-bench-matrix/20260513-121353-youssofal-top25-continuation/`
- runtime: `/private/tmp/mlx-dflash-bench-venv` のクリーン venv、`dflash-mlx` は既存成功 commit `20d68db3b3c0ae3dd6d3a2f0d3c10b2344ee514e` に固定。
- 有効結果: `12/25`
- 通常成功: `4/12`
- TOP_25 Score: `16.0%`
- Valid-only Score: `33.3%`
- 合計時間: `1570.6s`
- 成功: `anagram`, `bank-account`, `binary-search`, `crypto-square`
- 通常失敗: `acronym`, `binary-search-tree`, `bowling`, `complex-numbers`, `connect`, `diamond`, `dnd-character`, `flatten-array`
- infra: `dnd-character` 後に DFlash backend が Metal `Impacting Interactivity` で複数回 abort し、gateway crash circuit が開いた。`flatten-array` は crash 後に取れた値なので採用判断では低信頼。

### `DDTree + Youssofal`

- artifact: `.artifacts/dflash/ts-bench-matrix/20260513-124434-youssofal-ddtree-top25-continuation/`
- rest artifact: `.artifacts/dflash/ts-bench-matrix/20260513-125348-youssofal-ddtree-rest-per-exercise/`
- 有効通常結果: `13/25`
- 通常成功: `6/13`
- TOP_25 Score: `24.0%`
- Valid-only Score: `46.2%`
- 成功: `anagram`, `binary-search`, `complex-numbers`, `crypto-square`, `diamond`, `flatten-array`
- 通常失敗: `acronym`, `bank-account`, `binary-search-tree`, `bowling`, `food-chain`, `spiral-matrix`, `transpose`
- infra failure: rest-per-exercise の `connect`, `dnd-character` は server returncode `-6`。initial run の `bank-account` でも server exit があったが、rest-per-exercise の `bank-account` は 918.3s の通常失敗として確定。
- 補足: `food-chain` は ts-bench output JSON から復元した。harness 親プロセスが結果 JSONL 追記前に消え、DDTree server PID `18504` が orphan になったため停止した。`house` 以降は rest2 で継続予定。
- rest2 補足: `/private/tmp` 配下の venv / ts-bench checkout が消えていたため、`20260513-142120` と `20260513-142638` は infra artifact として保存。venv、`ts-bench v1-final`、`exercism-typescript` submodule を復元した。`20260513-142940` は `spiral-matrix` と `transpose` が通常失敗、`two-bucket` が進行中。`house`, `pascals-triangle`, `rational-numbers`, `react`, `rectangles`, `relative-distance`, `robot-name` は submodule 復元前の `ENOENT` のため再実行対象。

現時点では、download 数が最大でも `Youssofal` は `TheCluster + DDTree` を上回っていない。精度主指標では引き続き `TheCluster + DDTree` が第一候補。

## 1. 精度ランキング

`ts-bench overallSuccess` の成功数を主指標にする。coding agent 用途ではこの順位を最優先する。

| 順位 | 組み合わせ | 成功 | 成功率 | 備考 |
| ---: | --- | ---: | ---: | --- |
| 1 | `TheCluster + DDTree` | `7/10` | `70.0%` | 現時点の最良 |
| 2 | `DFlash + TheCluster` | `5/10` | `50.0%` | 平均時間は最速 |
| 2 | `froggeric + DDTree` | `5/10` | `50.0%` | 精度は DFlash + TheCluster と同率 |
| 2 | `vanch007 + DDTree` | `5/10` | `50.0%` | 精度は DFlash + TheCluster と同率 |
| 5 | `nabi-chan + DDTree` | `4/10` | `40.0%` | tokenizer warning あり |

倍率:

- `TheCluster + DDTree` は `5/10` 群より成功数で `1.40x` 良い。
- `TheCluster + DDTree` は `nabi-chan + DDTree` より成功数で `1.75x` 良い。

## 2. 速度ランキング

共通 10 exercise の平均 `totalDuration`。低いほど速い。ただし、不正解が多い候補も速く見えるため、単独では採用判断に使わない。

| 順位 | 組み合わせ | 平均時間 | 合計時間 | 成功 |
| ---: | --- | ---: | ---: | ---: |
| 1 | `DFlash + TheCluster` | `149.0s` | `1490.3s` | `5/10` |
| 2 | `nabi-chan + DDTree` | `155.0s` | `1549.6s` | `4/10` |
| 3 | `vanch007 + DDTree` | `161.7s` | `1616.7s` | `5/10` |
| 4 | `froggeric + DDTree` | `172.9s` | `1729.1s` | `5/10` |
| 5 | `TheCluster + DDTree` | `179.4s` | `1794.0s` | `7/10` |

倍率:

- `DFlash + TheCluster` は `TheCluster + DDTree` より平均時間で `1.20x` 速い。
- ただし `TheCluster + DDTree` は成功数で `1.40x` 良いため、agent task では DDTree 側を優先する。

## 3. 成功効率ランキング

`合計時間 / 成功数`。低いほど、成功 1 件を得るための時間効率が良い。

| 順位 | 組み合わせ | 秒 / 成功 | 成功 | 合計時間 |
| ---: | --- | ---: | ---: | ---: |
| 1 | `TheCluster + DDTree` | `256.3s` | `7/10` | `1794.0s` |
| 2 | `DFlash + TheCluster` | `298.1s` | `5/10` | `1490.3s` |
| 3 | `vanch007 + DDTree` | `323.3s` | `5/10` | `1616.7s` |
| 4 | `froggeric + DDTree` | `345.8s` | `5/10` | `1729.1s` |
| 5 | `nabi-chan + DDTree` | `387.4s` | `4/10` | `1549.6s` |

倍率:

- `TheCluster + DDTree` は `DFlash + TheCluster` より `1.16x` 効率が良い。
- `TheCluster + DDTree` は `vanch007 + DDTree` より `1.26x`、`froggeric + DDTree` より `1.35x`、`nabi-chan + DDTree` より `1.51x` 効率が良い。

## 4. 安定性ランキング

`dnd-character` で DFlash / DDTree とも Metal `Impacting Interactivity` が再現したため、完全安定な候補はない。ここでは共通 10 exercise 到達、infra failure 数、warning の有無で見る。

| 順位 | 組み合わせ | 有効完了 | infra failure | 評価 |
| ---: | --- | ---: | ---: | --- |
| 1 | `TheCluster + DDTree` | `10` | `1` | `dnd-character` 以外では最も高精度 |
| 2 | `DFlash + TheCluster` | `10` | `1` | gateway crash circuit が再現 |
| 3 | `vanch007 + DDTree` | `10` | `1` | 精度は `5/10` |
| 4 | `froggeric + DDTree` | `10` | `1` | `dnd-character` で早期 server exit |
| 5 | `nabi-chan + DDTree` | `10` | `1` | tokenizer warning と `4/10` 成功 |
| 参考 | `Youssofal + DDTree` | `2` | `1` | `bank-account` で server exit。rest-per-exercise 再評価中 |

infra failure:

- DFlash `TheCluster` + `dnd-character`: `dflash_gateway_crash_circuit_open`
- DDTree `TheCluster` + `dnd-character`: server exit `-6`
- DDTree `froggeric` + `dnd-character`: server exit `-6`
- DDTree `vanch007` + `dnd-character`: server exit `-6`
- DDTree `nabi-chan` + `dnd-character`: server exit `-6`

## 5. 総合ランキング

総合は `精度 > 成功効率 > 安定性 > 平均速度` の順で評価する。

| 順位 | 組み合わせ | 結論 |
| ---: | --- | --- |
| 1 | `TheCluster + DDTree` | 採用候補。最も成功数が多く、成功 1 件あたり時間も最良。 |
| 2 | `DFlash + TheCluster` | 速度重視の比較基準。平均時間は最速だが、成功率は DDTree TheCluster に劣る。 |
| 3 | `vanch007 + DDTree` | 成功数は DFlash TheCluster と同じで、froggeric より成功効率が良い。 |
| 4 | `froggeric + DDTree` | 成功数は `5/10` だが、成功効率で vanch007 に劣る。 |
| 5 | `nabi-chan + DDTree` | 速度だけなら上位だが、成功数と tokenizer warning のため低順位。 |
| 参考 | `Youssofal + DDTree` | `bank-account` で infra failure が出ているため総合順位から除外。 |

## 結論

現時点の第一候補は次の組み合わせ。

```text
TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit
+ z-lab/Qwen3.6-35B-A3B-DFlash
+ DDTree
```

速度だけなら `DFlash + TheCluster` が最速だが、coding agent 用途では ts-bench の TOP_25 Score が最重要なので `TheCluster + DDTree` を本命にする。`dnd-character` の Metal crash は通常の不正解ではなく、TOP_25 Score 上は 0 点として扱いつつ、原因分類では runtime / harness 側の別課題として分離する。

## 6. DDTree と DFlash の関係

DDTree は DFlash と別物として単独比較しているわけではありません。今回の `DDTree + <target>` はすべて、次の構成です。

```text
<Qwen3.6 35B-A3B uncensored target>
+ z-lab/Qwen3.6-35B-A3B-DFlash
+ DDTree
```

つまり `DDTree + TheCluster` は「TheCluster target に DFlash draft を組み合わせ、さらに DDTree の検証木を使う」経路です。`DFlash + TheCluster` は「同じ target / draft を通常 DFlash gateway で使う」経路です。

## 7. 全組み合わせの実行成否

全組み合わせが成功したわけではありません。TOP_25 を完全完走した組み合わせもありません。

| 組み合わせ | TOP_25 状態 | 有効結果 | 通常成功 | 通常失敗 | infra failure | 備考 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `DFlash + TheCluster` | crash 前まで有効 | `10/25` | `5` | `5` | `1` | `dnd-character` で crash circuit |
| `DFlash + Youssofal` | crash 後まで部分評価 | `12/25` | `4` | `8` | `1` | `dnd-character` 後に backend abort。`flatten-array` は低信頼 |
| `DFlash + froggeric` | 未評価 | `0/25` | `0` | `0` | `0` | DFlash engine abort 後のため未実行 |
| `DFlash + vanch007` | 未評価 | `0/25` | `0` | `0` | `0` | DFlash engine abort 後のため未実行 |
| `DFlash + nabi-chan` | 未評価 | `0/25` | `0` | `0` | `0` | DFlash engine abort 後のため未実行 |
| `DDTree + TheCluster` | crash 前まで有効 | `10/25` | `7` | `3` | `1` | `dnd-character` で server exit |
| `DDTree + Youssofal` | 部分評価中 | `13/25` | `6` | `7` | `2` | `connect` / `dnd-character` で server exit。rest2 の invalid 7 件は再実行対象 |
| `DDTree + froggeric` | crash 前まで有効 | `10/25` | `5` | `5` | `1` | `dnd-character` で server exit |
| `DDTree + vanch007` | crash 前まで有効 | `10/25` | `5` | `5` | `1` | `dnd-character` で server exit |
| `DDTree + nabi-chan` | crash 前まで有効 | `10/25` | `4` | `6` | `1` | tokenizer warning あり |

## 8. 失敗ケース込みのランキング

ここでは通常失敗と infra failure を両方含める。通常失敗は ts-bench が最後まで走ったがテストが通らなかったもの、infra failure は Metal crash / server exit / gateway crash circuit です。

精度は失敗率ではなく、ts-bench の数値スコアとして扱う。TOP_25 が完走していないため、2 種類を併記する。

- `TOP_25 Score`: `通常成功数 / 25`。未到達・通常失敗・infra failure・再実行待ちは 0 点扱い。
- `Valid-only Score`: `通常成功数 / 有効実行数`。crash 前に実際に完了した問題だけを見る参考値。

### 精度: TOP_25 Score 順

| 順位 | 組み合わせ | TOP_25 Score | 通常成功 | 有効実行 | 通常失敗 | infra failure | 未確定 |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `DDTree + TheCluster` | `28.0%` | `7/25` | `10` | `3` | `1` | `14` |
| 2 | `DFlash + TheCluster` | `20.0%` | `5/25` | `10` | `5` | `1` | `14` |
| 2 | `DDTree + froggeric` | `20.0%` | `5/25` | `10` | `5` | `1` | `14` |
| 2 | `DDTree + vanch007` | `20.0%` | `5/25` | `10` | `5` | `1` | `14` |
| 5 | `DDTree + nabi-chan` | `16.0%` | `4/25` | `10` | `6` | `1` | `14` |
| 参考 | `DFlash + Youssofal` | `16.0%` | `4/25` | `12` | `8` | `1` | `12` |
| 参考 | `DDTree + Youssofal` | `24.0%` | `6/25` | `13` | `7` | `2` | `10` |
| 未評価 | `DFlash + froggeric` | N/A | N/A | `0` | `0` | `0` | N/A |
| 未評価 | `DFlash + vanch007` | N/A | N/A | `0` | `0` | `0` | N/A |
| 未評価 | `DFlash + nabi-chan` | N/A | N/A | `0` | `0` | `0` | N/A |

`DDTree + TheCluster` は `DFlash + TheCluster` より TOP_25 Score が `1.40x` 高い。`Youssofal` は download 数最大だが、DFlash / DDTree の追加評価ではまだ TheCluster を上回っていない。

### 精度: Valid-only Score 参考

| 順位 | 組み合わせ | Valid-only Score | 通常成功 / 有効実行 | 備考 |
| ---: | --- | ---: | ---: | --- |
| 1 | `DDTree + TheCluster` | `70.0%` | `7/10` | 主ランキング 1 位 |
| 3 | `DFlash + TheCluster` | `50.0%` | `5/10` | 速度は最速 |
| 3 | `DDTree + froggeric` | `50.0%` | `5/10` | 同率 |
| 3 | `DDTree + vanch007` | `50.0%` | `5/10` | 同率 |
| 参考 | `DDTree + Youssofal` | `46.2%` | `6/13` | `food-chain` は output JSON から復元。rest2 は進行中 |
| 6 | `DDTree + nabi-chan` | `40.0%` | `4/10` | tokenizer warning あり |
| 参考 | `DFlash + Youssofal` | `33.3%` | `4/12` | crash 後結果を含むため低信頼 |

### 速度: 通常実行の平均時間順

| 順位 | 組み合わせ | 有効結果 | 平均時間 | 合計時間 | 成功 |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | `DFlash + TheCluster` | `10` | `149.0s` | `1490.3s` | `5` |
| 2 | `DDTree + nabi-chan` | `10` | `155.0s` | `1549.6s` | `4` |
| 3 | `DDTree + vanch007` | `10` | `161.7s` | `1616.7s` | `5` |
| 4 | `DDTree + froggeric` | `10` | `172.9s` | `1729.1s` | `5` |
| 5 | `DDTree + TheCluster` | `10` | `179.4s` | `1794.0s` | `7` |
| 参考 | `DDTree + Youssofal` | `13` | `215.9s` | `2806.6s` | `6` |
| 参考 | `DFlash + Youssofal` | `12` | `130.9s` | `1570.6s` | `4` |

速度だけでは `DFlash + TheCluster` が最速。ただし成功数は `DDTree + TheCluster` が `1.40x` 上。

### 成功効率: 合計時間 / 成功数

| 順位 | 組み合わせ | 秒 / 成功 | 成功 | 合計時間 |
| ---: | --- | ---: | ---: | ---: |
| 1 | `DDTree + TheCluster` | `256.3s` | `7` | `1794.0s` |
| 2 | `DFlash + TheCluster` | `298.1s` | `5` | `1490.3s` |
| 3 | `DDTree + vanch007` | `323.3s` | `5` | `1616.7s` |
| 4 | `DDTree + froggeric` | `345.8s` | `5` | `1729.1s` |
| 5 | `DDTree + nabi-chan` | `387.4s` | `4` | `1549.6s` |
| 参考 | `DDTree + Youssofal` | `467.8s` | `6` | `2806.6s` |
| 参考 | `DFlash + Youssofal` | `392.6s` | `4` | `1570.6s` |

## 9. 失敗テストケース一覧

### `DFlash + TheCluster`

- 成功: `anagram`, `bank-account`, `binary-search`, `crypto-square`, `diamond`
- 通常失敗: `acronym`, `binary-search-tree`, `bowling`, `complex-numbers`, `connect`
- infra failure: `dnd-character` -> `dflash_gateway_crash_circuit_open`
- 未到達: `flatten-array` 以降

### `DDTree + TheCluster`

- 成功: `anagram`, `bank-account`, `binary-search`, `complex-numbers`, `connect`, `crypto-square`, `diamond`
- 通常失敗: `acronym`, `binary-search-tree`, `bowling`
- infra failure: `dnd-character` -> `server_exited_during_ts_bench`
- 未到達: `flatten-array` 以降

### `DDTree + froggeric`

- 成功: `anagram`, `bank-account`, `binary-search`, `crypto-square`, `diamond`
- 通常失敗: `acronym`, `binary-search-tree`, `bowling`, `complex-numbers`, `connect`
- infra failure: `dnd-character` -> `server_exited_during_ts_bench`
- 未到達: `flatten-array` 以降

### `DDTree + vanch007`

- 成功: `anagram`, `bank-account`, `binary-search`, `crypto-square`, `diamond`
- 通常失敗: `acronym`, `binary-search-tree`, `bowling`, `complex-numbers`, `connect`
- infra failure: `dnd-character` -> `server_exited_during_ts_bench`
- 未到達: `flatten-array` 以降

### `DDTree + nabi-chan`

- 成功: `anagram`, `binary-search`, `crypto-square`, `diamond`
- 通常失敗: `acronym`, `bank-account`, `binary-search-tree`, `bowling`, `complex-numbers`, `connect`
- infra failure: `dnd-character` -> `server_exited_during_ts_bench`
- 未到達: `flatten-array` 以降

### `DDTree + Youssofal`

- 成功: `anagram`, `binary-search`, `complex-numbers`, `crypto-square`, `diamond`, `flatten-array`
- 通常失敗: `acronym`, `bank-account`, `binary-search-tree`, `bowling`, `food-chain`, `spiral-matrix`, `transpose`
- infra failure: rest-per-exercise の `connect`, `dnd-character` -> `server_exited_during_ts_bench`
- 再実行対象: `house`, `pascals-triangle`, `rational-numbers`, `react`, `rectangles`, `relative-distance`, `robot-name`。`20260513-142940` の前半は submodule 復元前の `ENOENT`。
- 進行中: `two-bucket`
- 未到達: `variable-length-quantity`, `wordy`

### `DFlash + Youssofal`

- 成功: `anagram`, `bank-account`, `binary-search`, `crypto-square`
- 通常失敗: `acronym`, `binary-search-tree`, `bowling`, `complex-numbers`, `connect`, `diamond`, `dnd-character`, `flatten-array`
- infra failure: `dnd-character` 後に Metal crash circuit。`flatten-array` は crash 後結果のため低信頼。
- 未到達: `food-chain` 以降

### DFlash の未評価 3 候補

以下は TOP_25 の本比較として未評価。

- `DFlash + froggeric`
- `DFlash + vanch007`
- `DFlash + nabi-chan`

理由は、`DFlash + TheCluster` と `DFlash + Youssofal` がどちらも途中で crash circuit を開き、同一 gateway で残り DFlash 候補を続けると評価が汚染されるためです。比較するなら candidate ごとに gateway / backend / artifact を完全分離して再計測する。
