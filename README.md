# Qwen3.6 35B-A3B Heretic + DFlash + DDTree Gateway

Apple Silicon Mac で、`TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit` を DFlash / DDTree 前提で使うための再現用リポジトリです。

このリポジトリは次を含みます。

- DFlash backend をオンデマンド起動し、未使用 5 分で停止する OpenAI 互換 gateway
- 現行の TheCluster + `z-lab/Qwen3.6-35B-A3B-DFlash` 標準設定
- DDTree 実験実装のコピー
- ts-bench 比較で使ったスクリプト、ランキング、主要 summary artifact

モデル重み、Hugging Face キャッシュ、`.venv`、巨大な実行ログは含めません。

## 結論

現時点の本命構成はこれです。

```text
TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit
+ z-lab/Qwen3.6-35B-A3B-DFlash
+ DDTree
```

ts-bench の有効比較では、`TheCluster + DDTree` が最も良い結果でした。

| 観点 | 最良 | 数値 |
| --- | --- | ---: |
| TOP_25 Score | `TheCluster + DDTree` | `7/25`, `28.0%` |
| Valid-only Score | `TheCluster + DDTree` | `7/10`, `70.0%` |
| 成功効率 | `TheCluster + DDTree` | `256.3s / success` |
| 平均速度 | `DFlash + TheCluster` | `149.0s / task` |

速度だけなら通常 DFlash が速い場面があります。ただし coding agent では「正解に到達すること」を優先するため、採用候補は `TheCluster + DDTree` です。

ベンチは「比較結果の取得」には成功しています。ただし TOP_25 全完走ではありません。`TheCluster + DDTree` は crash 前までの有効 10 exercise で `7/10` 成功し、TOP_25 Score としては `7/25 = 28.0%` です。`dnd-character` は Metal crash 系の infra failure として分離しています。

詳細は [bench/docs/tsbench-rankings-20260513.md](bench/docs/tsbench-rankings-20260513.md) を見てください。

Hugging Face download 数のランキングは [bench/docs/hf-download-rankings-20260513.md](bench/docs/hf-download-rankings-20260513.md) に置いています。今回の対象では `Youssofal/Qwen3.6-35B-A3B-Abliterated-Heretic-MLX-4bit` が最大で、`TheCluster` の約 `9.97x` です。ただし追加ベンチでは、download 数最大の `Youssofal` は `DDTree` で `23/25` まで有効通常結果を取り、`6/25` 成功に留まったため、`TheCluster + DDTree` を上回っていません。

## 必要なもの

- Apple Silicon Mac
- macOS
- Python 3.11 以上。検証時は Python 3.12 系
- `uv`
- Hugging Face アカウント。TheCluster を標準にする場合はログイン推奨
- 十分な SSD 空き容量

SSD は最低でも `60GB` 程度、現実的には `80GB` 以上空けることを推奨します。理由は、target model、DFlash draft、HF cache、実行 artifact、仮想環境が同時に必要になるためです。

メモリは大きいほど安定します。35B-A3B 4bit でも、長い context、prefix cache、DDTree 検証を重ねると unified memory と SSD swap の影響が出ます。

## セットアップ

```bash
git clone https://github.com/2001Y/qwen36-dflash-ddtree-gateway.git
cd qwen36-dflash-ddtree-gateway
cp .env.example .env
```

Hugging Face にログインします。

```bash
huggingface-cli login
```

HF ログインなしでまず試したい場合は、`Youssofal/Qwen3.6-35B-A3B-Abliterated-Heretic-MLX-4bit` を使えます。2026-05-13 時点の Hugging Face API では `private=false` / `gated=false` として確認しています。ただし大容量 Xet download なので、ログインなしだと rate limit や download speed で不利になる可能性があります。

```env
DFLASH_MODEL=Youssofal/Qwen3.6-35B-A3B-Abliterated-Heretic-MLX-4bit
DFLASH_DRAFT=z-lab/Qwen3.6-35B-A3B-DFlash
```

Youssofal でも 35B-A3B / MLX / 4bit / Heretic 系なので、同じ DFlash draft を明示して DFlash / DDTree 経路で起動できます。ただし手元ベンチでは `DFlash + Youssofal` は `4/25`、`DDTree + Youssofal` は `23/25` まで有効で `6/25` 成功です。TOP_25 枠は分類完了済みで、総合採用判断ではまだ TheCluster を上位にしています。

仮想環境を作り、DFlash と DDTree 実験実装を入れます。

```bash
uv venv .venv --python python3.12
source .venv/bin/activate
uv pip install -U pip
uv pip install -U "git+https://github.com/bstnxbt/dflash-mlx@20d68db3b3c0ae3dd6d3a2f0d3c10b2344ee514e" huggingface_hub fastapi uvicorn
uv pip install -e bench/ddtree-mlx
```

2026-05-13 の検証では、`dflash-mlx` 最新 commit `90ec8d4d901b90e434a743a8ee83b6823cf10a42` で DDTree 経路の callback signature 回帰に当たったため、既存成功 commit に固定しています。

`uv` がない場合は先に入れてください。

```bash
brew install uv
```

## DFlash gateway を起動する

通常はこちらを使います。

```bash
./scripts/start-dflash-gateway.command
```

gateway は `http://127.0.0.1:8000` で待ち受けます。backend は最初の生成リクエスト時に `http://127.0.0.1:8001` で起動されます。

```text
client
  -> http://127.0.0.1:8000/v1/chat/completions
  -> dflash_gateway.py
  -> scripts/start-dflash-backend.command
  -> scripts/start-dflash.command
  -> dflash-mlx backend on 127.0.0.1:8001
```

最初の 1 回は、モデルのダウンロードまたはメモリロードで長く待ちます。gateway は backend が `/v1/models` を返すまで待ってから request を転送します。

OpenAI 互換クライアントには次を設定します。

```text
Base URL: http://127.0.0.1:8000/v1
API Key: dummy
Model: TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit
```

疎通確認:

```bash
curl -s http://127.0.0.1:8000/v1/models
```

生成確認:

```bash
curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit",
    "messages": [{"role": "user", "content": "Return exactly OK"}],
    "max_tokens": 8,
    "temperature": 0
  }'
```

## 自動停止条件

`DFLASH_GATEWAY_IDLE_SECONDS=300` が標準です。最後に `/v1/*` の生成系リクエストを転送してから 300 秒間アクセスがなければ、gateway が backend process group に `SIGTERM` を送り、必要なら `SIGKILL` します。

手動停止:

```bash
curl -X POST 'http://127.0.0.1:8000/gateway/stop?force=1'
```

状態確認:

```bash
curl -s http://127.0.0.1:8000/gateway/metrics
```

ログ:

```text
.artifacts/dflash/gateway/events.jsonl
.artifacts/dflash/gateway/backend-*.log
```

## DDTree server を起動する

DDTree 実験経路を直接試す場合はこちらを使います。

```bash
./scripts/start-ddtree-server.command
```

endpoint は標準で `http://127.0.0.1:8216/v1` です。

```bash
curl -s http://127.0.0.1:8216/health
```

```bash
curl -s http://127.0.0.1:8216/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit",
    "messages": [{"role": "user", "content": "Return exactly OK"}],
    "max_tokens": 8,
    "temperature": 0,
    "tree_budget": 4
  }'
```

## 現行標準設定

coding agent 向けの標準候補です。

```text
DFLASH_PROFILE=balanced
DFLASH_MAX_CTX=24000
DFLASH_PREFILL_STEP_SIZE=4096
DFLASH_PREFIX_CACHE_MAX_ENTRIES=4
DFLASH_PREFIX_CACHE_MAX_BYTES=8589934592
DFLASH_PREFIX_CACHE_L2=0
DDTREE_TREE_BUDGET=4
```

L2 prefix cache は SSD 空き容量が十分ある場合だけ有効化します。

```text
DFLASH_PREFIX_CACHE_L2=1
DFLASH_PREFIX_CACHE_L2_MAX_BYTES=53687091200
```

ただし 2026-05-13 時点の検証マシンは空き容量が厳しかったため、標準は L1 のみです。

## ベンチフォルダ

[bench](bench) に、今回の検証で使ったものを入れています。

- [bench/workspace-files](bench/workspace-files): 元ワークスペースからコピーした起動スクリプトと ts-bench matrix runner
- [bench/ddtree-mlx](bench/ddtree-mlx): このマシンで手を入れた DDTree 実験実装
- [bench/docs](bench/docs): ts-bench ランキング
- [bench/docs/hf-download-rankings-20260513.md](bench/docs/hf-download-rankings-20260513.md): 対象モデルの Hugging Face download 数ランキング
- [bench/artifacts](bench/artifacts): 主要 `summary.json`

巨大な `results.jsonl`、model cache、`.venv`、`.uv-cache` は含めていません。

ベンチの状態は次の扱いです。

- 実行基盤: ts-bench matrix の実行と summary artifact の取得には成功
- 完走状態: TOP_25 を完全完走した組み合わせはなし
- 主結果: `TheCluster + DDTree` が有効 10 exercise で `7/10` 成功
- 参考結果: `DFlash + Youssofal` は `12/25` まで有効、`4/25` 成功
- 参考結果: `DDTree + Youssofal` は `23/25` まで有効、`6/25` 成功。TOP_25 枠は分類完了

## 注意点

- DDTree は DFlash の代替ではありません。今回の `DDTree + TheCluster` は、TheCluster target と DFlash draft を使い、その上に DDTree 検証木を載せる構成です。
- `Youssofal/Qwen3.6-35B-A3B-Abliterated-Heretic-MLX-4bit` は HF ログインなしで試せる代替候補です。ただし本リポジトリの第一候補は、手元 ts-bench で最良だった TheCluster です。
- `GET /v1/models` は標準では backend を起動せず、静的な model list を返します。生成リクエストで backend を起動します。
- `dnd-character` は DFlash / DDTree とも Metal crash 系の infra failure を再現しました。通常の不正解とは分けて扱っています。
- `Youssofal` は download 数では最大ですが、現時点の ts-bench では TheCluster を上回っていません。
- oMLX は使っていません。DFlash 実験では `dflash-mlx` 直結のほうが制御しやすいためです。
