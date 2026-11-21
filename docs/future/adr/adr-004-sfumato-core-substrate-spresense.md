# ADR-004: [hdl] Sfumato 核の実装基板 = 外部 DSP(Sony Spresense)候補 / 目的は物理 ANC ではなく環境調和

- ステータス: Deferred (2026-08-31)(保留前は Proposed・方向性の記録)
- 保留理由: 2026-08-31 にプロジェクトを「Python/NumPy の DSP モデルが成果物」と再定義し、FPGA 移植を将来の拡張としたため。決定内容は再開時の出発点として保持する(経緯は [../README.md](../README.md))。
- 日付: 2026-06-04
- 領域: hdl(実装基板の選択)。適応オーディオの方式モデリングは二本立ての原則どおり algo を前段に置く。
- 関連: [../../philosophy.md](../../philosophy.md) / [../architecture-hardware.md](../architecture-hardware.md) / [../roadmap-hardware.md](../roadmap-hardware.md) / [adr-003-brain-implementation-approach.md](adr-003-brain-implementation-approach.md) / [adr-002-audio-output-sigma-delta-dac.md](adr-002-audio-output-sigma-delta-dac.md)

## コンテキスト

ビジョン図の **sfumato 核**(= 適応オーディオ「Sfumato DSP Core」+ コンテキスト認識「Brain」、[../architecture-hardware.md](../architecture-hardware.md)「全体ビジョン」)の実装基板を検討する。現ビジョンは sfumato 核も Muscle=FPGA 内に置き、音声信号を直接処理する適応 DSP を RTL、Brain は Register Bus 越しにパラメータだけ書く疎結合([adr-003](adr-003-brain-implementation-approach.md))としていた。ここに **「Sony Spresense を導入し、復調済みの音声に対して *環境音と調和する* 適応処理を行わせる」** という案が出たため、方向性を記録する。MVP の範囲外(Phase 3 / 4)であるが、信号 I/F・出力トポロジ・二系統開発の原則に影響するため、早期に記録する。

前提(動かさない):

- **復調(基盤 = radio)は FPGA に残す。** MVP(FM ステレオ放送を FPGA で受信・再生する)は不変かつ最優先とする。本 ADR は MVP の進行を妨げない。
- **目的は環境音の「調和・連続」であって、物理キャンセル(ANC)ではない。** philosophy.md L9 は放送音声と聴取環境を「分離せず**連続させる**」と定義する。環境音を*打ち消す* ANC はこの思想と方向性が逆であり、かつ広帯域の音響 ANC は遅延要件(マイク→出力が sub-ms 級)が厳しく、チップ間を往復するトポロジに適合しない。**本 ADR は物理 ANC を採らない。** 環境音に応じた動的 EQ / マスキング補償 / モーフによって、放送音声を聴取空間の音響と*調和させる*方向に限定する。

制約:

- GW1NR-9C は小規模(LUT ≈ 8.6k、BRAM・乗算器も限定)。適応オーディオと環境推論をそのまま RTL で実装することは面積の制約上困難である([adr-003](adr-003-brain-implementation-approach.md) と同じ制約)。
- 適応・推論系は反復開発が多く、アルゴリズムが頻繁に変更される。RTL は反復開発に適さない。
- 身体性のループ「マイク知覚 → 場の理解 → 音の変容」([../../philosophy.md](../../philosophy.md) L16)は、マイク入力・DSP・エッジ推論が一箇所に集約されるほどインタフェース境界が減少する。

実現方式の候補:

1. **FPGA 内 RTL(現ビジョン)** … 適応 DSP を RTL、環境センシングは [adr-003](adr-003-brain-implementation-approach.md) の案で実装し、Register Bus でパラメータ制御。
   - 利点: 単一基板・最小遅延。`make sim` の algo↔hdl 検証にそのまま乗る。信号がチップ間を経由しない(「一つの身体」が単一チップとして実現される)。
   - 欠点: 小規模 FPGA 上で適応 DSP と推論の面積が競合する。反復開発が遅い。
2. **外部 DSP / Sony Spresense(本 ADR の主対象)** … 復調音声を I2S 等で Spresense へ渡し、マルチマイクで環境を聴き、適応 EQ / モーフを掛ける。環境センシング(Brain 相当)も同居。
   - 利点: 身体ループ(マイク+DSP+エッジ AI)を一基板に集約できる。C による反復開発が速い。FPGA 面積を消費しない。Spresense はマルチマイク・音声 DSP・エッジ AI を前提とするボードであり、本用途に適合する。
   - 欠点: 信号経路にチップ間境界(I2S・遅延)が生じる。依存ツールチェーン(Spresense SDK)が増加する。sfumato 核については、二系統開発が「algo → RTL」ではなく「algo → Spresense C」となる。
3. **FPGA 内ソフトコア(RISC-V 等)** … [adr-003](adr-003-brain-implementation-approach.md) 案2。単一基板のまま柔軟性を上げる。
   - 利点: 単一基板を保ちつつソフトで書ける。
   - 欠点: コアとメモリが面積を消費し、Muscle と競合する。Spresense に比べ、音声 I/O・エッジ AI の既存資産が乏しい。

## 決定

**未決(Proposed)。** 現時点の方向性のみ記録する:

- **MVP では sfumato 核を作らない。** FM 復調 → 自作 ΣΔ DAC 出力([adr-002](adr-002-audio-output-sigma-delta-dac.md))までの Muscle 最小経路を先に成立させる。
- **sfumato 核(適応オーディオ + それを駆動する環境センシング)の有力候補として、外部 DSP = Sony Spresense(案2)を記録する。** 動機は身体ループの一基板への集約・反復開発の速度・FPGA 面積の節約である。
- **スコープを「環境調和」に固定する。** 物理 ANC(環境音の打ち消し)は本 ADR では採用しない。やる場合は別 ADR で独立サブ目標(Spresense 単体・耳元マイク前提)として切り出す。
- **出力 / DAC の所在は未確定。** MVP は FPGA 自作 ΣΔ DAC を出力とする([adr-002](adr-002-audio-output-sigma-delta-dac.md)、学習目標として温存)。Spresense の組み込み方 —
  - (a) FPGA 復調音 → I2S → Spresense 加工 → FPGA へ戻し自作 ΣΔ DAC から出力(往復・自作 DAC を残す)、
  - (b) Spresense 側 DAC/コーデックから最終出力(配線シンプル・自作 DAC は範囲外)
  — は Phase 3 着手時に本 ADR を更新して確定する。当面は (a) を基準に検討する。
- **制御 I/F の扱い。** Spresense が morph 自体を持つ場合、[adr-003](adr-003-brain-implementation-approach.md) の Register Bus(パラメータ書き換えの疎結合)は信号路 I/F(I2S 等)に置き換わる。なお「Spresense は環境推論しパラメータだけ FPGA に書き、morph は FPGA RTL」という案1寄りの折衷も残す(疎結合設計はその場合も活きる)。

## 影響

### 良い影響
- 身体ループ(マイク知覚 → 場の理解 → 音の変容)を一基板に集約でき、Register Bus で morph/context を分断する現ビジョンよりインタフェース境界が減少する。
- 適応・推論を C で迅速に反復開発できる。GW1NR-9C における面積競合を回避できる。
- MVP の進行を妨げない(Muscle 最小経路と独立)。物理 ANC の厳しい遅延要件を回避しつつ、sfumato 境界①(放送と環境の連続)を狙える。

### 受け入れるトレードオフ / 負の影響
- 信号経路にチップ間境界(I2S・遅延)が生じる。
- 出力トポロジ次第で、自作 ΣΔ DAC([adr-002](adr-002-audio-output-sigma-delta-dac.md))の学習目標としての意義が薄れうる((b) 採用時)。
- 依存ツールチェーン(Spresense SDK)が増加する。sfumato 核では二系統開発が「algo → RTL」から「algo → Spresense C」へ変わる(復調は従来どおり RTL、核はソフトウェアと、責務により分かれる)。

### 将来への含み
- Phase 3 着手時に本 ADR を Proposed → Accepted へ更新し、候補1〜3 と出力トポロジ (a)/(b) を確定。確定後 [../architecture-hardware.md](../architecture-hardware.md) の sfumato 核の節と algo↔hdl 対応表へ反映する。
- 物理 ANC を志向する場合は別 ADR を新設(本 ADR のスコープ外)。

## 備考
- 本決定の動機は思想([../../philosophy.md](../../philosophy.md) L9「分離せず連続させる」/ L16 身体ループ)にある。
- [adr-003](adr-003-brain-implementation-approach.md) の候補④「外部エッジ AI コプロセッサ(Spresense)」と相互参照。Brain(環境センシング)も本 ADR の Spresense に同居しうる。
- Spresense は Phase 3 着手の直前まで調達しない([../roadmap-hardware.md](../roadmap-hardware.md) ハードウェア調達方針)。
