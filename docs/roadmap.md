# Roadmap

進捗・フェーズ管理の**正本**。進捗を動かしたらこのファイルを直接更新する。
方式の決定理由は [adr/](adr/)、設計の現状は [architecture.md](architecture.md) を参照。

**本プロジェクトの成果物は Python/NumPy の DSP モデル**(`src/algo/`)と、その復調品質を測る評価基盤である。達成基準は定量的に置く: 復調品質を市販チューナ(Sony ST-5130)スペックで測り、CI の品質ゲートで守る([ADR-005](adr/adr-005-demod-quality-gate.md))。
FPGA(Tang Nano 9K)への移植は将来の拡張候補として保留し、旧 Phase 2〜4・調達表・hdl セットアップは [future/roadmap-hardware.md](future/roadmap-hardware.md) に退避した(2026-08-31)。

## Phase 1: モデリングとシミュレーション

Python/NumPy による FM ステレオ変復調モデル。成果の詳細は [README.md](../README.md)、アルゴリズムの解説は [algorithm.md](algorithm.md) を参照。

- [x] 1.1 送信(音声 → FM 変調 → AWGN 付加)
- [x] 1.2 受信(選局 Mixing → 帯域制限 → デシメーション → ベースバンド IQ)
- [x] 1.3 復調(IQ → 位相 → 微分で音声復元)
- [x] 1.4 ステレオ MPX(MPX 生成 / 分離、DSB-SC によるサブキャリア検波)
- [x] 1.5.1 pre-emphasis / de-emphasis(高域のノイズ耐性向上)
- [x] 1.5.2 PLL(デジタル 2 次 Type-II)によるパイロット同期・搬送波再生
- [x] 1.5.3 PLL を含む受信系の最適化([algorithm.md 1.5.2.2](algorithm.md#1522-システムの最適化) / [ADR-007](adr/adr-007-stereo-separation.md))
  - ステレオ復調を線形位相 FIR 化(`stereo_main_lpf`/`stereo_sub_bpf`、同長=群遅延一致)し
    main を群遅延分だけ遅延させて sub と整合させた。IIR の非線形位相特性により損なわれていた「副搬送波=2×パイロット」の位相関係を回復した。
  - 38kHz 搬送波に位相補正(PLL の NCO 出力に定数オフセット、`STEREO_CARRIER_PHASE_RAD`)。
  - PLL 帯域を 50→200Hz に最適化(高 SNR では残留位相誤差 ε が律速要因となるため広帯域が有利。低 SNR でも悪化しないことを SNR スイープで確認)。
  - 結果: セパレーション 0.84→**45.04dB**(Sony 42dB 超過 → ハードゲート昇格)。
- [x] 1.6 評価基盤の整備(品質を運用規律ではなく**機構**で保証する。CI において lint と同列のゲートとする)
  - [x] `add_awgn` の乱数シード固定(再現性。`radio/channel.py` は `rng` 注入式で固定可能)
  - [x] `pytest` 導入・`tests/` 雛形・`make eval` ターゲット・GitHub Actions(CI: fmt-check + lint + eval)
  - [x] メトリクス層 `algo/eval/metrics.py`(THD/SINAD・L-R セパレーション・PLL ロック時間)— 契約テスト 5 件が成功
        ※ 将来の移植メモ: 純粋関数なので、HDL シミュレーション出力を同じ関数に通せばモデル↔実装のアクセプタンス・オラクルとして再利用できる
- [ ] 1.7 復調品質の定量評価とゲート化(characterize → `baseline.json` → 回帰ゲート → 絶対しきい値)
  - [x] characterize ハーネス(決定論パイプライン `eval/harness.py` / 集計 `eval/characterize.py`)
  - [x] `baseline.json` 機構(`make characterize` で生成、`schema_version`/`conditions` 付き)
  - [x] 回帰ゲート(ハード)・絶対しきい値ゲート(`tests/test_quality_gate.py`、`make eval` に同梱)
  - [x] 方針を ADR-005 で確定([adr/adr-005-demod-quality-gate.md](adr/adr-005-demod-quality-gate.md))
  - [x] 絶対しきい値の目標を市販製品スペック(Sony ST-5130)に設定 — THD ≤0.3% / セパレーション ≥42dB / S/N ≥75dB
  - [ ] **目標との差の解消**(現状 THD 0.0072% 昇格済 / セパレーション 45.04dB 昇格済 / SINAD 66.8dB — 差 8.2dB)。
        ステレオ分離の前にモノラル復調経路で THD/SINAD を測る方針へ切替(`_mono_decode`、baseline schema v2)。
        THD はモノラルで Sony 絶対ゲート(≤0.3%)に到達しハードゲートへ昇格済み。
        SINAD は2段で改善: (1) 19kHz パイロットの漏洩を 15kHz 間引き FIR(`dsp/filters.py`、ポリフェーズ)で除去 40.9→49.8dB、
        (2) 複素ミキサ後のチャネル選択 LPF(`_channel_select`、2*fc 像除去)で 49.8→66.8dB。
        ※ (2) は受信の共通段であるため、当時未達であったセパレーションが 1.67→0.84dB と微小に変動した(いずれも実質的に分離が成立していない領域であり、baseline を更新した)。
        ステレオ L/R の最終間引きも mono と同じ 15kHz ポリフェーズ FIR に統一(パイロット除去を反映)。
        セパレーションは 1.5.3 で 0.84→45.04dB に改善し Sony 絶対ゲート(≥42dB)へ昇格(上記 1.5.3)。
        **残る目標との差は SINAD のみ(目標 75dB・現状 66.8dB・差 8.2dB)**。THD・セパレーションは昇格済み。
  - [ ] PLL ロック tol/hold の確定(観測ログから `settings.py` を埋める)

  > 運用(ラチェット): 回帰ゲートが品質の下限を保持し、Sony 絶対ゲートは strict xfail で目標を追跡する。
  > アルゴリズムが各メトリクスで Sony 仕様に到達すると、xpass(strict により失敗扱い)によりハードゲートへの昇格を通知する。
  > **1.7 の合格 = Sony 絶対ゲートがすべてハードゲートへ昇格した状態**(= 方式確立)。
  > 改善を確認した時点で `make characterize` により baseline(品質の下限)を更新する。
- [ ] 1.8 因果・ストリーミング参照モデル化(判別器を I/Q 差分形へ / フィルタを状態付き逐次形へ)
- [ ] デシメーション多段化の整理(現状: 係数 12 単段 FIR、`radio/receiver.py`)
- [ ] 最大周波数偏移 75kHz での品質検証(settings は復帰済み・定量未確認、[algorithm.md 1.2 c.f.](algorithm.md#cf-最大周波数偏移の修正) 参照)

> **「完了(x)」は実装済みを表す。方式の確立は 1.7 の定量評価に合格して初めて成立**する。
> 将来の移植メモ: 1.8 は固定小数点化の前段にあたる。現行復調は `np.unwrap` の全体処理で、そのままではストリーミング実装(HW を含む)に適用できない。移植側の計画は [future/roadmap-hardware.md](future/roadmap-hardware.md)。

## 今後の課題(モデル)

1. **SINAD の改善 66.8→75 dB**(差 8.2 dB)。バイパス実験により、現行アーキテクチャの性能限界(約 67 dB)に到達していることを確認済み([ADR-006](adr/adr-006-receiver-filter-fir-iir.md))。次の段階として、TX 側のイメージ成分(192k→2.304M 補間)と測定系の雑音床の寄与を分離して評価する。
2. **PLL ロック時間メトリクスの有効化**(現状 `pll_lock_time_s: null`)。`PLL_LOCK_TOL` / `PLL_LOCK_HOLD_SAMPLES` を観測ログから確定し、`PLL_LOCK_MAX_S` を置いてゲートに乗せる。
3. **algorithm.md 1.5.2.2 の本文の拡充**。現在は ADR-006/007 の要約と結果表のみであり、原因分析の図と導出を追記する。

## セットアップ・チェックリスト

1. `make install`(uv sync で `.venv` 構築)
2. `make run`(シミュレーション実行、`outputs/` に結果)
3. `make eval`(品質ゲート。CI と同じ)
