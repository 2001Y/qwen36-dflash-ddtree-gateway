# 2026-05-13 DFlash / DDTree Youssofal 追加課題

`_docs/issue.md` は iCloud FileProvider の dataless 状態で読み取りが固まるため、この追記は独立ファイルに分離する。

## 1. `.venv` の dataless 化

- 症状: 既存 `.venv` 配下の `fastapi-0.136.1.dist-info/METADATA` などが `blocks=0` になり、DFlash backend 起動が import 中に停止した。
- 対応: `/private/tmp/mlx-dflash-bench-venv` にクリーン venv を作成し、ベンチスクリプトから `BENCH_PYTHON` / `DFLASH_PYTHON` / `DFLASH_BIN` で参照するようにした。
- 追加対応: `start-dflash.command` と benchmark harness は外部 venv を受け取れるように修正済み。

## 2. `dflash-mlx` 最新 commit の回帰

- 最新取得 commit: `90ec8d4d901b90e434a743a8ee83b6823cf10a42`
- 既存成功 commit: `20d68db3b3c0ae3dd6d3a2f0d3c10b2344ee514e`
- 症状: 最新 commit では DDTree 経路で `_cast_floating_model.<locals>._cast() missing 1 required positional argument: 'x'` が出た。
- 対応: クリーン venv の `dflash-mlx` は既存成功 commit に固定した。
- 追加課題: upstream に合わせるなら、`model.apply()` callback signature の変更を DDTree 側で吸収するか、DFlash 側の該当 commit の意図を確認する。

## 3. Youssofal DDTree の `bank-account` infra failure

- artifact: `.artifacts/dflash/ts-bench-matrix/20260513-124434-youssofal-ddtree-top25-continuation/`
- 症状: `bank-account` で DDTree server が returncode `-6` で終了。
- stderr: Metal `Discarded (victim of GPU error/recovery)`
- 分類: ts-bench の通常不正解ではなく runtime / GPU recovery 系の infra failure。
- 対応: `.artifacts/dflash/ts-bench-matrix/20260513-125348-youssofal-ddtree-rest-per-exercise/` で 1 exercise = 1 server に分離して再評価中。
- 再評価結果: `bank-account` は 918.3s の通常失敗として確定。`binary-search` は 55.2s で成功。`binary-search-tree` は 55.7s の通常失敗。`bowling` は 113.3s の通常失敗。`complex-numbers` は 82.4s で成功。`connect` は server returncode `-6` の infra failure。`crypto-square` は 62.0s で成功。`diamond` は 74.9s で成功。`dnd-character` は server returncode `-6` の infra failure。`flatten-array` は 50.0s で成功。`food-chain` は ts-bench output JSON から 367.3s の通常失敗として復元した。
- 追加症状: `food-chain` では benchmark harness 親プロセスが `results.jsonl` 追記前に消え、DDTree server PID `18504` が orphan になった。
- 対応: `food-chain` のログと output JSON は保存し、orphan DDTree server だけ停止した。`house` 以降は `_shell/run-youssofal-ddtree-rest2-per-exercise-20260513.sh` で継続する。

## 4. per-exercise 実行時の依存キャッシュ肥大化

- 症状: 初回の per-exercise artifact が `2.0GB` まで肥大化した。原因は各 exercise の `out_dir` 配下に `uv-cache` を作り、Aider / Playwright 依存が再取得されたこと。
- 対応: 失敗 artifact は直接削除済み。
- 修正: `UV_CACHE_DIR`, `UV_TOOL_DIR`, `UV_TOOL_BIN_DIR`, `PLAYWRIGHT_BROWSERS_PATH` を `/private/tmp` 配下の共有パスに固定した。

## 5. rest2 再開時の `/private/tmp` 揮発

- 症状: `20260513-142120-youssofal-ddtree-rest2-per-exercise` は `/private/tmp/mlx-dflash-bench-venv/bin/python` が消えており、全 exercise が `status=127` で即終了した。
- 症状: venv 復旧後の `20260513-142638-youssofal-ddtree-rest2-per-exercise` は `/private/tmp/ts-bench` がなく、`FileNotFoundError` で startup failure になった。
- 症状: `ts-bench` 復旧後の `20260513-142940-youssofal-ddtree-rest2-per-exercise` は、`exercism-typescript` submodule 復元前に前半 exercise が `ENOENT: exercism-typescript/exercises/practice` で即終了した。
- 対応: `dflash-mlx` は既存成功 commit `20d68db3b3c0ae3dd6d3a2f0d3c10b2344ee514e` で venv を再作成し、`ts-bench` は `laiso/ts-bench` の `v1-final` を `/private/tmp/ts-bench` に復元、`git submodule update --init --recursive` で `exercism-typescript` を復元した。
- 修正: DDTree root は `/private/tmp/ddtree-mlx` ではなく repo 内の `_release/qwen36-dflash-ddtree-gateway/bench/ddtree-mlx` を使うように runner を変更した。
- 現状: `20260513-142940-youssofal-ddtree-rest2-per-exercise` が進行中。`spiral-matrix` と `transpose` は通常失敗として反映し、`two-bucket` が実行中。submodule 復元前の `house`, `pascals-triangle`, `rational-numbers`, `react`, `rectangles`, `relative-distance`, `robot-name` はランキングに混ぜず、完了後に再実行する。

## 6. 現時点の採用判断

- download 数最大は `Youssofal`。
- ただし追加計測時点では `TheCluster + DDTree` の ts-bench 成績を上回っていない。
- coding agent 用途の第一候補は引き続き `TheCluster/Qwen3.6-35B-A3B-Heretic-MLX-4bit + z-lab/Qwen3.6-35B-A3B-DFlash + DDTree`。
