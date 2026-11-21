# ADR-002: [hdl] 音声出力経路は自作 ΣΔ DAC(MVP)、I2S 外部 DAC は任意上位

- ステータス: Deferred (2026-08-31)(保留前は Proposed)
- 保留理由: 2026-08-31 にプロジェクトを「Python/NumPy の DSP モデルが成果物」と再定義し、FPGA 移植を将来の拡張としたため。決定内容は再開時の出発点として保持する(経緯は [../README.md](../README.md))。
- 日付: 2026-06-04
- 領域: hdl
- 関連: [../roadmap-hardware.md](../roadmap-hardware.md) / [../architecture-hardware.md](../architecture-hardware.md) / [../diagrams/system-architecture.mmd](../diagrams/system-architecture.mmd)

## コンテキスト

algo の復調出力を実機で再生する経路を確定する必要がある。背景・制約:

- Tang Nano 9K(GW1NR-9C)に **DAC が無い**。MVP の到達点は FM ステレオ放送の受信・再生であり、可能な限りブレッドボードで完結させる。
- プロジェクトの目的は **DSP を FPGA 内に自作して習得する**こと(ADR-001 と同じ思想)。出力段も既製品に依存しない方針とする。
- 全体ビジョン図([system-architecture.mmd](../diagrams/system-architecture.mmd))では出力が `I2S Tx → 外部 DAC/Amp` と描かれていたが、これは roadmap 2.2 の baseline(自作 ΣΔ DAC)と矛盾していた。本 ADR でどちらが本線かを確定する。

実現方式の候補は以下:

1. **自作 ΣΔ(1bit)DAC + 外付け RC LPF + イヤホンジャック**
   - 利点: FPGA 内製により 1bit DAC の設計を習得できる。外付けは RC + ジャックのみでブレッドボードで完結。MCLK 等の制約が無い。
   - 欠点: 音質は RC 定数とオーバーサンプリング比に依存。高音質化には設計・調整を要する。
2. **PWM DAC + RC**
   - 利点: 実装が最も単純。
   - 欠点: ΣΔ に比べて雑音整形の効果が小さく、同等の音質には高いクロック周波数を要する。
3. **既製 I2S DAC(PCM5102A 等)**
   - 利点: 音質が安定する。I2S Tx の RTL のみを実装すればよい。
   - 欠点: DSP 自作の目的から外れる。外付けモジュールを要する(PCM5102A は MCLK 不要品を選ぶ)。

DSP 自作の目的・ブレッドボード完結性を優先し、**案1** に収束。音質不足時の代替手段として案3を任意上位に残す。

## 決定

**MVP は自作 ΣΔ DAC** に決定する。具体的には:

- 信号経路(本線): `Sfumato/復調出力 → ΣΔ DAC(FPGA 内製 1bit)→ RC LPF(外付け)→ イヤホンジャック`。
- まず正弦波テーブルを `make sim` で波形確認 → 実機でイヤホン出力 → ステレオ 2ch 化(roadmap 2.2 の順)。
- **任意上位**: ΣΔ の音質が不十分な場合に限り、`I2S Tx → PCM5102A(MCLK 不要品)` へ置き換え可能とする。ビジョン図の I2S 経路はこの任意上位を指し、本線ではない。
- スコープ外(やらないこと): MCLK 必須の I2S DAC、MVP 段階での外部 DAC 採用。

## 影響

### 良い影響
- 出力段まで一貫して自作し、1bit DAC・雑音整形の設計を習得できる。
- 外付けが RC + ジャックのみで、出力パスがブレッドボードで完結する(調達も最小)。

### 受け入れるトレードオフ / 負の影響
- 音質が RC 定数・オーバーサンプリング比に依存し、調整工数を要する。
- 高音質を求める段階で I2S DAC へ置き換える可能性が残る(その場合は本 ADR を更新)。

### 将来への含み
- 置き換えを行う場合は、本 ADR を Superseded にせず、任意上位の採用として追記更新する。
- RC フィルタ定数の実測値が決まったら [../architecture-hardware.md](../architecture-hardware.md) に反映する。

## 備考
- 調達候補(ジャック・抵抗・コンデンサ / 任意の PCM5102A)は [../roadmap-hardware.md](../roadmap-hardware.md) の「ハードウェア調達」を参照。
