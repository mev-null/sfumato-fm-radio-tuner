# sfumato-fm-radio-tuner

FM ステレオ放送の送信 → 通信路(AWGN)→ 受信を、Python/NumPy で一貫してモデル化したプロジェクト。決定論の評価ハーネスで THD・SINAD・ステレオ・セパレーションを毎回測定し、CI の品質ゲートで市販チューナ(Sony ST-5130)の公称スペックを目標に据える。

English: [README.md](README.md)

<img width="1400" height="1000" alt="first_ancem92_analysis" src="https://github.com/user-attachments/assets/a0f4a1f1-e2b0-4021-9e59-ff494015a0eb" />

*ステレオ音楽のシミュレーション結果(`make run`)。上段: 遅延整列した入力と復調出力の時間波形の重ね合わせ、および残差(In−Out)。下段: 入力と出力のパワースペクトル密度。左右チャネルそれぞれについて示す。*

## デモ

実ステレオ音楽を**製品スペック水準**で復調できる。品質は目視ではなく測定値で判定する。`make eval` がシード固定の決定論的パイプラインを実行し、結果を Sony ST-5130 スペックでゲートする。

| メトリクス | 現状 | 目標(Sony ST-5130) | 状態 |
|---|---|---|---|
| THD(全高調波歪み) | 0.0072 % | ≤ 0.3 % | ✅ 達成 |
| セパレーション(L−R 分離) | 45.0 dB | ≥ 42 dB | ✅ 達成 |
| SINAD(信号対雑音+歪み) | 66.8 dB | ≥ 75 dB | ⏳ 追跡中 |

評価条件は 1 kHz・SNR 40 dB・シード固定(`src/algo/settings.py` の `EVAL_*`)。数値の根拠は ADR([005](docs/adr/adr-005-demod-quality-gate.md) / [006](docs/adr/adr-006-receiver-filter-fir-iir.md) / [007](docs/adr/adr-007-stereo-separation.md))、アルゴリズムの解説は [docs/algorithm.md](docs/algorithm.md)。

**復調音声(ステレオ音楽)**: [原曲](https://github.com/user-attachments/files/25324970/first_ancem92.wav) → [復調後](https://github.com/user-attachments/files/28670715/first_ancem92.wav)

## 仕組み

```
音声(48k) → pre-emphasis → MPX(192k) → RF(2.304M) → FM変調
   → [AWGN] →
複素ミキシング → チャネル選択 LPF → 直交復調 → ↓12 → MPX(192k)
   → PLL で 38k 再生 → 線形位相 FIR マトリクス分離 → ↓4 → de-emphasis → 音声(48k)
```

ブロック図は [docs/diagrams/signal-chain.mmd](docs/diagrams/signal-chain.mmd)(README 英語版 / [docs/architecture.md](docs/architecture.md) に埋め込み)。レートは 48k × 4 = 192k、× 12 = 2.304M の整数比で、物理定数・レート・しきい値はすべて `src/algo/settings.py` に集約する。

`src/algo/` の構成:

| パス | 役割 |
|---|---|
| `radio/` | 放送リンク。`transmitter.py`(pre-emphasis・MPX 生成・FM 変調)、`channel.py`(`rng` 注入式の AWGN)、`receiver.py`(複素ミキシング・チャネル選択・直交復調・間引き・PLL 搬送波再生・遅延整合したステレオ・マトリクス、測定用モノラル経路) |
| `dsp/` | 部品。`filters.py`(FIR 設計)、`emphasis.py`、`pll.py`(逐次形 2 次 Type-II PLL。ブロック図 [docs/diagrams/pll-block.mmd](docs/diagrams/pll-block.mmd)) |
| `eval/` | 品質評価。`metrics.py`(純粋関数: THD / SINAD / セパレーション / PLL ロック時間)、`harness.py`(決定論パイプライン)、`characterize.py`(集計・`baseline.json`) |
| `utils/` | WAV 入出力・合成音源・可視化 |
| `settings.py` | レート・帯域・FM 定数・PLL 係数・ゲートしきい値の単一の定義元 |

### 評価ハーネスと品質ゲート(ラチェット)

`make eval`(pytest)は TX → AWGN → RX をシード固定で実行し、単一 1 kHz トーン(THD / SINAD)と L のみ駆動のステレオ信号(セパレーション)を測る。判定は 2 段([ADR-005](docs/adr/adr-005-demod-quality-gate.md)、`tests/test_quality_gate.py`):

- **絶対しきい値ゲート**: 目標は Sony ST-5130 スペックからトップダウンに置く。未達のメトリクスは `xfail(strict=True)` とし、CI を成功状態に保ちつつ目標との差を毎回測定する。目標に到達すると xpass(失敗扱い)となり、ハードゲートへの昇格時期であることを通知する。THD とセパレーションはこの手順で昇格済み、SINAD は追跡中。
- **回帰ゲート**(ハード): 全メトリクスを `src/algo/eval/baseline.json` と比べ、品質が低下する方向に 2 % を超えて変化した場合に fail とする。baseline の更新は `make characterize` による意図的操作のみで、diff は PR でレビューする。測定条件が変わったら比較せず無効とする。

回帰ゲートが品質の下限を保持し、絶対ゲートが目標仕様への到達を判定する。完了の判定を主観ではなく測定値で定義する。

この仕組みの帰結として、THD / SINAD はステレオ・マトリクスを通さないモノラル経路(`_mono_decode`)で測り FM 復調チェーン単体の純度を評価する([ADR-006](docs/adr/adr-006-receiver-filter-fir-iir.md))。セパレーションは遅延整合した線形位相 FIR・搬送波の定数位相補正・PLL 帯域の拡大(50 → 200 Hz)で 0.84 dB → 45 dB に改善した([ADR-007](docs/adr/adr-007-stereo-separation.md))。

## Getting Started

前提: [uv](https://docs.astral.sh/uv/) / Python 3.12+。

```bash
make install       # uv sync
make run           # 送信 → 通信路 → 受信のシミュレーション
make eval          # 品質ゲート(pytest。CI と同じ)
make characterize  # 再測定して baseline.json を書き換える(意図的操作)
make fmt           # ruff format + ruff check --fix
make lint          # ruff check
```

`make run` は `inputs/first_ancem92.wav`(`settings.INPUT_FILE`)を読み、`outputs/<name>_restored.wav`(復調音声)と `outputs/<name>_analysis.png`(時間波形の重ね合わせ・残差・PSD)を書き出す。入力ファイルが無い場合はステレオの時報音を合成して代用する。`inputs/` `outputs/` は gitignore 済み。

## ドキュメント

| 内容 | 参照先 |
|---|---|
| アルゴリズム解説(変復調・MPX・エンファシス・PLL・最適化の記録) | [docs/algorithm.md](docs/algorithm.md) |
| 信号設計・パイプライン・パッケージ構成・評価基盤 | [docs/architecture.md](docs/architecture.md) |
| 進捗・今後の課題 | [docs/roadmap.md](docs/roadmap.md) |
| 保留中のハードウェア・トラック(FPGA 計画・ハードウェア ADR 001–004・ボード図) | [docs/future/](docs/future/) |
| 思想 | [docs/philosophy.md](docs/philosophy.md) |
| 開発時の作業ガイド / 開発ルール | [CLAUDE.md](CLAUDE.md) / [.claude/rules.md](.claude/rules.md) |

## 将来の拡張

**FPGA 移植(保留)。** モデルは将来ハードウェアへ移植できるよう設計している(位相特性が性能を律速する段は線形位相 FIR、レートはすべて整数比、PLL は逐次形)。Tang Nano 9K 向けのスキャフォールドは [src/hdl/](src/hdl/README.md) にあり、独立した README と Makefile を持つ。計画・ハードウェア ADR・ボード図は [docs/future/](docs/future/)。着手時期は未定で、成果物はモデルである。

## クレジット・ライセンス

- **"first_ancem92.wav"** — ステレオ FM 復調の忠実度を検証するために作曲したオリジナル曲。
  - 作曲・制作: mev-null © 2026
  - ライセンス: [CC BY-NC-ND 4.0](https://creativecommons.org/licenses/by-nc-nd/4.0/)(共有自由・クレジット必須・商用/二次創作は不可)
- **コード**: [MIT License](LICENSE)
