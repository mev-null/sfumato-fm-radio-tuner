# ADR-005: [algo] 復調品質ゲートの方針(characterize / baseline / 回帰 / 絶対しきい値)

- ステータス: Accepted
- 日付: 2026-06-05
- 領域: algo
- 関連: [../roadmap.md](../roadmap.md) / [../architecture.md](../architecture.md) / [adr-001(保留)](../future/adr/adr-001-rf-frontend-low-if-adc.md)

## コンテキスト

1.6 で品質メトリクスの純粋関数(`src/algo/eval/metrics.py`: THD / SINAD / L-R セパレーション / PLL ロック時間)と CI ゲート(`make eval` = pytest)は整備済みである。しかし、実際の復調パイプライン出力を評価して品質を判定する機構が存在しない。roadmap で(当時)「方式の確立は 1.7 の定量評価に合格して初めて成立し、これが Phase 2/HDL の合格基準」と定めていた以上、品質を運用規律ではなく機構で保証する回帰ゲートが必要である。

ゲートの構成には複数の論点がある:

1. **絶対しきい値のみ** — 各メトリクスに固定の下限/上限を置く。
   - 利点: 単純で基準が明確。欠点: 適切な初期値が不明な段階では設定できない。基準内での微小な劣化を検出できない。
2. **回帰(baseline)のみ** — 既知の良好な値からの劣化を許容幅で検出する。
   - 利点: 微小な劣化も検出できる。欠点: baseline が低品質であればその水準で固定される。絶対的な品質保証を与えない。
3. **両建て(絶対 + 回帰)** — 絶対しきい値で品質の下限を、回帰ゲートで劣化検出を担う。
   - 利点: 品質の下限と劣化検出の両方を担保できる。欠点: 機構が複雑になる。

品質の下限(MVP 合格基準)の保証と継続的な劣化検出は異なる要件であり、一方のみでは不十分である。検討の結果、両建てに収束した。

加えて、しきい値の数値を誰が決定するかという論点がある。本プロジェクトは学習者主体(rules.md 12)であり、品質基準の確定は方式理解の中核をなす。よって**機構は scaffold として用意し、数値は観測値に基づき利用者が確定する**方針とする。

## 決定

**両建て(絶対しきい値ゲート + baseline 回帰ゲート)** を採用する。具体的には:

- **characterize**: 決定論パイプライン(`eval/harness.py`)で TX→AWGN(seed 固定)→RX を実行し、メトリクスを集計する(`eval/characterize.py`)。測定条件は `settings.py` の `EVAL_*`(単一トーン 1kHz・1 秒・SNR=40dB・seed=12345)に固定する。トーン周波数は FFT ビン中心に一致するコヒーレント周波数とする。
- **baseline.json**: characterize の結果スナップショット。`schema_version` と `conditions` を含め、条件が変われば基準を無効化できるようにする。生成は **`make characterize` 実行時のみ**(`--update`)。回帰ゲートの基準が意図せず変更されることを防ぐ。
- **回帰ゲート**: baseline から品質が低下する方向に `REGRESSION_TOL` を超えて変化した場合に fail とする。dB 系(SINAD・セパレーション)は低下、THD・ロック時間は増加を片側検定で検出する。`conditions` 不一致時は比較しない。
- **絶対しきい値ゲート**: `THD_MAX` / `SINAD_MIN_DB` / `SEPARATION_MIN_DB` / `PLL_LOCK_MAX_S` を下限/上限として assert する。目標値は **市販製品スペック**(下記「絶対しきい値の根拠」)に置く。現行アルゴリズムが未達の間は **strict xfail** とし、CI を成功状態に保ちつつ目標との差を測定する。到達すると xpass(strict により失敗扱い)によりハードゲートへの昇格を通知する(ラチェット)。
- **回帰ゲートはハード**: `REGRESSION_TOL = 0.02`(2%)。パイプラインは決定論的(seed 固定)であり本来は同値となるため、tol は numpy/scipy/BLAS の実行環境差による数値ドリフトを許容するための幅である。
- **PLL ロックは未確定**: `pll_lock_time` の `tol` は `PilotPLL` の誤差出力(乗算検波の生値)に対する絶対値で、MPX のパイロット振幅に依存する。固定の汎用値がないため `settings.py` に `None` で置き、ゲートは `pytest.skip`。観測ログに基づき利用者が決定する。
- **スコープ外(本 ADR では扱わない)**: 複数 SNR スイープ(SINAD カーブ)。MVP は単一 SNR 1 点とし、スイープは 1.7 完了後の拡張とする。

baseline 更新タイミング: **改善を確認した場合に限り手動で `make characterize` を実行**し、生成された diff を PR レビューで確認してからコミットする。

## 絶対しきい値の根拠(出典)

目標は、市販製品が満たす品質をアルゴリズムに課す方針で定める(現状値を追認するボトムアップではなく、仕様から定めるトップダウン)。基準は **Sony ST-5130 FM ステレオチューナ**の公称仕様。市販 FM 受信 IC(Skyworks/Silicon Labs Si4730/35)とも整合する。

| 設定値 | 値 | 出典(Sony ST-5130 / 測定条件) | クロスチェック(Si4730/35) |
|---|---|---|---|
| `THD_MAX` | 0.3%(= 0.003 線形比) | ステレオ THD 0.3% @ 400Hz・100%変調 | typ 0.1% / max 0.5% |
| `SEPARATION_MIN_DB` | 42 dB | ステレオセパレーション 42 dB @ 400Hz | typ 42 dB(min 35) |
| `SINAD_MIN_DB` | 75 dB | FM S/N 75 dB(モノ) | ステレオ S/N typ 58 dB |

- Sony ST-5130 仕様: <https://reverb.com/item/68501767-sony-st-5130-fm-stereo-fm-am-tuner-fully-capacitors-upgraded-led-hifi-fuse>
- Sony ST-S170 仕様(参考・SNR 69dB / THD 0.5%): <https://www.hifiengine.com/manual_library/sony/st-s170.shtml>
- Si4730/35-D60 データシート Table 7「FM Receiver Characteristics」: <https://www.skyworksinc.com/-/media/Skyworks/SL/documents/public/data-sheets/Si4730-31-34-35-D60.pdf>

注意:
- 本メトリクスの `sinad_db` は **SINAD**(雑音+歪み込み)で、Sony の "S/N" は雑音のみ。THD 0.3% は歪み下限 ≈ 50 dB に相当するため、SINAD が 75 dB に達するには THD も同時に抑える必要がある。`SINAD_MIN_DB = 75` は雑音側の到達目標として置く。
- セパレーションの Sony 値は 400Hz、本測定は 1kHz。中域では同程度で、目標として妥当とみなす。
- 値の単位整合: `metrics.thd` は線形比を返すため百分率 0.3% を 0.003 で置く。

## 影響

### 良い影響
- 品質の下限(回帰ゲート)と製品スペック到達(絶対しきい値)の両方を CI で自動判定できる。`make eval` を介して既存 CI に変更なく組み込める。
- ラチェット運用により「1.7 合格 = Sony 絶対ゲートがすべて昇格した状態」として達成判定が測定可能になる(= 方式確立)。目標との差が毎回の CI 実行で可視化される。
- メトリクス関数は実装に依存しない純粋関数。将来 HDL へ移植する場合も、同じ characterize 機構をシミュレーション出力に適用してモデル↔実装のアクセプタンス・オラクルとして再利用できる(移植は保留中、[../future/](../future/README.md))。

### 受け入れるトレードオフ / 負の影響
- 絶対ゲートは strict xfail のため、未達の間は xfail(成功扱い)として表示され、pass と判別しにくい。目標との差は characterize の出力で確認する。
- baseline は手動更新のため、更新漏れ・誤更新の可能性が残る。diff のレビューに依存する。
- 単一 SNR・単一トーンの 1 点測定であり、帯域全体・低 SNR 領域の品質は別途評価を要する。
- しきい値の出典(Sony ST-5130)は 1970 年代のアナログチューナで、現代の DSP 受信機とは測定条件・前提が異なりうる。クロスチェックに市販 IC を併記してある。

### 将来への含み
- SNR スイープ・多トーン・帯域端での評価は 1.7 完了後に拡張する。
- 1.8(因果・ストリーミング参照モデル)や 75kHz 偏移の検証にも同じ characterize 機構を適用できる。
- 将来の移植メモ: HDL へ移植する場合は、同一メトリクスによりモデルと実装を同一条件で比較する([../future/roadmap-hardware.md](../future/roadmap-hardware.md) 2.3)。

## 備考
- 実装: `src/algo/eval/harness.py`(ドライバ)/ `characterize.py`(集計・baseline I/O)/ `tests/test_quality_gate.py`(ゲート)/ `settings.py`(条件・しきい値)/ `Makefile`(`characterize` ターゲット)。
- メトリクス定義には専用の ADR を設けない。`src/algo/eval/metrics.py`(実装)と契約テスト `tests/test_metrics.py` を正本とする。

### 追記(2026-06-07): THD/SINAD の測定基準をモノラル経路へ
当初 THD/SINAD はステレオ復調後の L チャンネルで測定していたが、副搬送波検波の残差が
混入していた。**モノラル復調経路(`_mono_decode`、main=L+R)で測る方式に変更**し、FM 復調
チェーン単体の純度を評価する(Sony の SINAD は元々モノ規格)。`baseline.json` は schema v2。
これにより THD・セパレーションが Sony 絶対ゲートに到達し、strict xfail → ハードゲートへ昇格した。
詳細・根拠は [adr-006-receiver-filter-fir-iir.md](adr-006-receiver-filter-fir-iir.md) / [adr-007-stereo-separation.md](adr-007-stereo-separation.md)。
