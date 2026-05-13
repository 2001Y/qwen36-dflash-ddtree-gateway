# VLM 統合メモ 2026-05-14

## 結論

- `MLX + DFlash + DDTree + VLM` を単一 backend で実現する完成品はまだ採用しない。
- この workspace では、画像入力だけ `mlx-vlm` で要約し、その結果を既存の `TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit + DFlash + DDTree` の text agent へ渡す。
- VLM model は `mlx-community/Qwen3.6-35B-A3B-nvfp4` を採用する。
- gateway / backend の責務は memory load のオンデマンド制御であり、download は引き続き `scripts/download-models.command` の責務とする。

## 外部エージェント候補

| 候補 | VLM 統合 | 評価 |
| --- | --- | --- |
| Codex CLI / Codex app | text / screenshot / diagram を扱う公式 multimodal coding agent | 現時点の品質基準。クラウド側の context 圧縮、sandbox、検証ログ、approval が強い |
| Claude Code | screenshot / image paste を公式 docs が案内 | 品質は高いが、ユーザー評価では Codex より劣る場面がある |
| OpenCode | image lesson / vision model 前提の画像入力導線あり | harness としては実用的。Codex 品質と同等とは未確認 |
| Pi | image input 対応 model を `models.json` で指定できる。拡張性重視 | 面白いが、Codex 級品質を示す公開 ts-bench は未確認 |
| Hermes Agent | HF model card が local MLX server 連携を案内 | VLM 連携候補。coding harness 品質は別途検証が必要 |
| Gemini CLI | Gemini model 前提の multimodal agent | local MLX とは別系統 |

## Pi について

Pi の `What we didn't build` は、plan mode、MCP、sub-agent、permission UI、background bash を core に焼き込まず、extensions / skills / packages / tmux など低レイヤーの道具に逃がす思想である。  
これは理論的には正しい。特に、agent harness が大きくなりすぎると、model・tool・context・権限の責務境界が濁る。

ただし、Codex と同じ品質かは別問題。Codex は model、context compression、sandbox、approval、diff、test evidence、resume、cloud task execution が統合された product であり、Pi は「小さい core と拡張性」を優先する harness である。  
2026-05-14 時点で、Pi と Codex を同一 model で ts-bench 比較した信頼できる公開結果は確認できていない。

## mxfp4 / nvfp4

| model | HF tag | サイズ | 月間 download | 採用判断 |
| --- | --- | ---: | ---: | --- |
| `mlx-community/Qwen3.6-35B-A3B-mxfp4` | Image-Text-to-Text / MLX / 4-bit | 19.3 GB | 11,056 | 省容量寄り |
| `mlx-community/Qwen3.6-35B-A3B-nvfp4` | Image-Text-to-Text / MLX / 4-bit | 20.4 GB | 59,110 | 品質・採用シグナル優先 |

この構成では VLM は coding 本体ではなく、画像を正確に読む前処理に使う。そのため、速度より画像理解の安定性を優先し `nvfp4` を採用する。

## 実装

- `vlm_image_summarizer.py`
  - `mlx_vlm.load`
  - `mlx_vlm.prompt_utils.apply_chat_template`
  - `mlx_vlm.generate`
  を使い、画像を coding/tool agent 用の構造化テキストへ変換する。
- `dflash_gateway.py`
  - `/v1/responses` と `/v1/chat/completions` の `input_image` / `image_url` を検出する。
  - 画像がある場合は text backend を停止して memory を空ける。
  - base64 data URL は `.artifacts/dflash/vlm-inputs/<request_id>/` に一時 materialize する。
  - VLM 要約を user message として追加し、画像本体は backend へ渡さない。
- `scripts/download-models.command`
  - `DFLASH_DOWNLOAD_VLM=1` の場合だけ `DFLASH_VLM_MODEL` を download 対象に加える。

## 環境変数

```env
DFLASH_VLM_ENABLED=1
DFLASH_VLM_MODEL=mlx-community/Qwen3.6-35B-A3B-nvfp4
DFLASH_VLM_TIMEOUT=900
DFLASH_VLM_MAX_TOKENS=768
DFLASH_VLM_TEMPERATURE=0
```

## Download

gateway は download を行わない。VLM model を使う machine では、事前に次を実行する。

```zsh
DFLASH_DOWNLOAD_VLM=1 ./scripts/download-models.command
```

## 残課題

- VLM は現時点で preprocessing 専用。DFlash/DDTree と同じ speculative decoding path には乗せない。
- OpenAI Responses API の built-in hosted tools はこの gateway では実装しない。
- function tool call の完全な Responses streaming 変換は別タスクとして残る。
- VLM summary の品質は、実画像を使って OCR / UI layout / error screenshot / diagram で別途評価する。

## 実機確認

2026-05-14 00:31 JST に LaunchAgent 経由の gateway で確認した。

- request id: `b1d7eee9-d886-4d83-ab14-da1bdb163f78`
- route: `POST /v1/responses`
- 入力: `data:image/png;base64` の小さい PNG。画像内 text は `Return exactly OK`。
- VLM: `mlx-community/Qwen3.6-35B-A3B-nvfp4`
- VLM preprocessing: `68.5s`
- DFlash backend cold start: 約 `31.0s`
- request 全体: `107.2s`
- 最終 response: `Return exactly OK`
- usage: `input_tokens=823`, `output_tokens=4`, `total_tokens=827`

補足:

- Codex sandbox 内で `vlm_image_summarizer.py` を直接実行すると `No Metal device available` で失敗する。これは DFlash と同じ制約であり、実機確認は LaunchAgent / Terminal など Metal にアクセスできる外側プロセスで行う。
- `mxfp4` / `nvfp4` は DFlash target 自動検出から除外した。これらは VLM preprocessing 専用として扱う。
