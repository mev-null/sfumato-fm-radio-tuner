# アルゴリズム解説(algo モデリング記録)

algo(Python/NumPy)で FM ステレオ変復調方式を確立する過程の記録。
全体像は [../README.md](../README.md)、信号設計の現状は [architecture.md](architecture.md)、物理定数・レートは `../src/algo/settings.py` を参照。

## 概要

時報の音声ファイルを

1. FM 信号に変調し、
2. IQ 信号に変換、
3. 最後に音声信号に復調した。

通信路は、加法性白色ガウス雑音(AWGN)が重畳するものと仮定してモデル化した。

### モデル全体のシミュレーション動画

https://github.com/user-attachments/assets/f829db6a-4b2d-4762-8efc-568c4f685ed2

## 1.1 Transmit

擬似的な音声信号(440Hz の正弦波)を生成し、FM 変調したうえでガウス雑音を付加するまでの過程をモデル化し、シミュレーションを行った。

### 音声信号 → FM 変調

- 音声信号を RF レートへ補間(アップサンプリング)したうえで FM 変調した
- 補間には線形補間を用いた(当時の実装。現行は `resample_poly` によるポリフェーズ FIR 補間)

### FM 変調信号へのガウス雑音の付加

- 補間後の信号電力と指定 SN 比から雑音電力を算出
- 雑音電力を分散とする正規分布から雑音系列を生成

### 雑音を含む FM 信号の可視化

<img width="1211" height="811" alt="signal_noisy" src="https://github.com/user-attachments/assets/983cb61c-0654-4bc8-b545-12008f4f4705" />

- 観察: 搬送波周波数の両側に変調成分(側波帯)が分布し、全帯域にわたって平坦な雑音床が重畳している。SN 比を高くするほど、信号に対する雑音床の相対レベルは低下する。

## 1.2 Receive

FM 信号を受け取り、

1. 選局 (Mixing): 目的の搬送波を 0 Hz へ周波数変換
2. 帯域制限 (Filtering): 信号帯域外の雑音を除去
3. 間引き (Decimation): サンプリングレートを RF 帯域(2.4MHz)から音声帯域(48kHz)へ変換

を順に実行し、ベースバンド IQ 信号を得るまでの過程をモデル化し、シミュレーションを行った。

### Mixing

受信信号に複素指数 exp(−j2πf_c t) を乗じ、搬送波周波数だけ負の方向へ周波数シフトした。

### ベースバンド IQ 信号の可視化

<img width="1211" height="811" alt="recieved_sign" src="https://github.com/user-attachments/assets/4a3a1f7f-169f-4de6-8bb8-556860d1ed62" />

#### c.f. 最大周波数偏移の修正

当初は出力レートを 48kHz(音声帯域)としていたため、帯域制限を 20kHz に設定してシミュレーションを行った。
しかし、最大周波数偏移 (Maximum Frequency Deviation) は日本の FM 放送規格 (±75kHz) に準拠して実装していたため、FM 信号の占有帯域が帯域制限を大きく超え、可視化において期待した結果が得られなかった。
本来はカットオフ周波数を 100kHz 程度に変更すべきであったが、ベースバンド IQ 信号のレートを 48kHz としていたため、暫定的に最大周波数偏移を 7.5kHz に縮小して実装した。
実際の FM 受信機では間引きを多段で行うことから、これを今後の実装課題とした。
[fix: 最大周波数偏移の縮小](https://github.com/mev-null/sfumato-fm-radio-tuner/pull/3/changes/afdc3e510589ab221ce63b8b71e9d62133b2f44d)

## 1.3 Demodulation

IQ 信号の瞬時位相の時間変化から音声信号を復元した。

### IQ 信号 → 位相

実部と虚部から逆正接関数(`np.angle`)により瞬時位相を求める。

### 位相 → 音声情報

アンラップした位相を時間微分(差分)し、瞬時周波数偏移を求める。FM では瞬時周波数偏移が変調信号に比例するため、これが復調音声となる。

### 復調音声の可視化

<img width="1211" height="811" alt="output3" src="https://github.com/user-attachments/assets/5a5b3f1c-a1d5-492b-9918-5766e2ce95a9" />

復調波形は原信号の波形とおおむね一致し、スペクトルのピークも 440Hz に現れており、妥当な結果である。

この時点のモデルで時報音声を復調した結果を以下に示す。

- 変調前の信号
  [time-tone.wav](https://github.com/user-attachments/files/25239643/time-tone.wav)
- 復調後の信号
  [time-tone_restored.wav](https://github.com/user-attachments/files/25239641/time-tone_restored.wav)
  (FM 受信に特有の雑音が重畳していることを確認できる)

## 1.4 Stereo Multiplexing

FM 変復調をステレオ信号に対応させた。
シミュレーションに使用した信号は、L 成分が 440Hz, R 成分が 880Hz のステレオ信号。

<img width="857" height="393" alt="stereo_sine" src="https://github.com/user-attachments/assets/2b5e5257-e11e-4676-8d7c-e58ff5eda417" />

音声信号レート(48kHz)と RF レート(約 2.4MHz)の間のレート変換(送信側の補間・受信側の間引き)において、中間レートとして MPX 信号レート(192kHz)を設けた。

### 送信機

左右チャネルの信号から MPX 信号を生成する。

#### 手順

1. 音声信号レートから MPX 信号レートへ補間(upsampling)
2. MPX 信号レートで、後述の構成に従って MPX 信号を生成
3. MPX 信号を RF レートへ補間(upsampling)
4. FM 変調を行い、RF 信号を生成

<img width="1211" height="811" alt="fm-stereo-signal" src="https://github.com/user-attachments/assets/361cd65f-9424-4ac1-af2d-7238fedf39b6" />

#### MPX 信号の構成

ベースバンドに L+R 信号、19kHz にパイロット信号、38kHz の副搬送波に L-R 信号(DSB-SC)を多重化した複合信号である。
占有帯域は L-R 成分の上側波帯上端である 53kHz までとなる。

<img width="1189" height="790" alt="mpx_signal" src="https://github.com/user-attachments/assets/adeb4c12-eb41-4f08-af76-472c83ad5d5c" />
<img width="1489" height="490" alt="mpx-pds" src="https://github.com/user-attachments/assets/bab0122c-3105-4f71-94da-6b07dcd81f6d" />

受信機は 19kHz のパイロット信号を基準として、38kHz 副搬送波を周波数・位相同期させて再生する。

### 通信路

加法性白色ガウス雑音(AWGN)が重畳するものとしてモデル化した。

<img width="1211" height="811" alt="fm-stereo-signal-awgn" src="https://github.com/user-attachments/assets/86c17e8e-4881-4053-9066-a530c76c38eb" />

### 受信機

#### MPX 信号の復調

1. RF 信号をベースバンド IQ 信号へ周波数変換
2. RF レートのまま IQ 信号を FM 復調し、MPX 信号を得る
3. RF レートから MPX 信号レートへ間引き(decimation)

<img width="1211" height="811" alt="decimated_signal" src="https://github.com/user-attachments/assets/b5ade06a-ec35-4624-8dae-6d16c4a63fae" />

復調した MPX 信号は、送信時の MPX 信号の波形とよく一致している。

#### MPX 信号からのステレオ分離

1. LPF(15kHz)により Main(L+R)成分を抽出
2. Sub(L-R)成分を抽出(後述)
3. ステレオ・マトリクスにより和差の連立方程式を解き、L, R 信号を求める
4. MPX 信号レートから音声信号レートへ間引き(decimation)

<img width="1021" height="1035" alt="stereo-decode-process" src="https://github.com/user-attachments/assets/c508d596-df0f-4da8-88ec-f01d4ecb4069" />

#### Sub 信号の抽出: DSB-SC(Double Sideband Suppressed Carrier: 抑圧搬送波両側波帯)

1. L-R 成分(変調波)の抽出: MPX 信号に BPF(23k〜53k)を適用する。
2. 19kHz パイロット信号から 38kHz 搬送波を再生する。
3. 同期検波: 帯域抽出した MPX 信号に、再生した 38kHz 搬送波を乗算する。
4. 検波後の信号に LPF(15kHz)を適用し、ベースバンドの L-R 信号を得る。

この時点で、音楽信号を実用的な音質で復調できる段階に達した。

- 変調前の音楽: [first_ancem92.wav](https://github.com/user-attachments/files/25324970/first_ancem92.wav)
- 復調後の音楽: [first_ancem92_restored.wav](https://github.com/user-attachments/files/25324963/first_ancem92_restored.wav)

## 1.5 Refine Algorithm

聴取に耐える音質を得るため、エンファシス処理などを追加した。

### 1.5.1 pre-emphasis と de-emphasis の実装

FM 復調は瞬時位相の時間微分に相当する。通信路で加わる白色雑音は、この微分により復調後には周波数に比例した振幅スペクトル(電力スペクトル密度は周波数の 2 乗に比例)をもつ三角雑音となる。
したがって、変調信号の高域成分ほど SN 比が劣化する。
さらに、一般的な音声・音楽信号は高域ほどスペクトル密度が低いため、高域の SN 比はいっそう劣化する。
これらの課題に対処するため、以下の処理を行った。

1. 送信機側で、送信信号にハイシェルフ特性のプリエンファシスを適用し、高域成分を強調する
2. 受信機側で、受信信号に低域通過特性のディエンファシスを適用し、強調した高域を元の特性へ戻すとともに高域雑音を抑圧する

#### 結果

効果を明瞭に示すため、SN 比の低い条件でシミュレーションを行った。

- エンファシス適用前の復調音楽信号
  <img width="1400" height="1000" alt="ancem92_10db_analysis" src="https://github.com/user-attachments/assets/23bfe13e-03c4-4a58-a298-58803de16a13" />
- エンファシス適用後の復調音楽信号
  <img width="1400" height="1000" alt="ancem92_emphasised_10db_analysis" src="https://github.com/user-attachments/assets/9137d37b-cdd3-4cf1-9c2f-9e06f2ef189a" />

高域において、復調信号のスペクトルが原信号と同様に周波数の増加に伴って減衰する特性を示すようになった。
これは、pre-emphasis と de-emphasis により高域の SN 比が改善され、三角雑音が抑圧されたことを示唆する。

### 1.5.2 PLL の実装

ステレオ復調では、パイロット信号(19kHz)から副搬送波(38kHz)を再生する必要がある。
前節までの実装では、MPX 信号に BPF を適用してパイロット信号を抽出し、これに二乗法(正弦波を二乗して周波数・位相を 2 倍にする逓倍)を適用して搬送波を生成していた。
この方式では、再生搬送波の品質が抽出したパイロット信号の品質に直接依存する。パイロット信号に雑音が重畳している場合、その雑音が搬送波の位相雑音として伝搬し、L/R の分離性能が劣化する。
また、実際の受信環境では、ドップラー効果や水晶発振子の周波数偏差により、パイロット信号に周波数ステップ(一定の周波数オフセット)が生じうる。
これらの課題を解決するため、以下のブロック図に示す PLL(Phase-Locked Loop)を実装した。
PLL により、パイロット信号に位相同期し、かつ雑音の少ない正弦波を生成できる。これを再生搬送波として用いることで同期検波の精度が向上し、L-R 信号を高い忠実度で復元できる。

<img width="1935" height="365" alt="PLL-block" src="https://github.com/user-attachments/assets/38084fad-d7c1-4b78-9220-e77ac16c95ce" />

#### 1.5.2.1 デジタル 2 次 Type-II PLL の概要

本システムは、19kHz パイロット信号を入力、NCO の位相を出力とし、出力を入力側へ帰還して位相誤差を求める閉ループ(フィードバック制御系)である。
位相比較器、ループフィルタ(PI)、NCO からなるループ内に積分器が 2 つ(ループフィルタ内と NCO 自身)存在するため、Type-II に分類される。

##### 制御理論の前提(PI 制御)

本節では、本システムの理解に必要な制御理論の要点を整理する。
前述のとおり、受信機ではドップラー効果や水晶発振子の周波数偏差によりパイロット信号に周波数ステップが生じるため、系には定常的な外乱が加わっているとみなせる。
したがって、位相誤差をゼロに保ったまま周波数オフセットを補償するには、制御器がゼロでない一定値(定常値)を出力し続ける必要がある。本実装では、以下の 2 つの制御を組み合わせた PI 制御を採用した。

- P 制御(比例制御): 位相誤差に P ゲインを乗じる。瞬時の位相誤差に比例した修正量を与え、過渡応答の速度を改善する。
- I 制御(積分制御): 位相誤差を累積(積分)し I ゲインを乗じる。離散時間では以下のように記述できる。

  ```
  integrator += i_gain * error
  ```

定常誤差の除去と安定性の確保には、P 制御と I 制御の両方が必要となる。P 制御のみの場合、制御量は

```
control = p_gain * error
```

となる。制御器がゼロでない一定値を出力し続けるには誤差 `error` が常にゼロでない値をとる必要があり、誤差をゼロに収束させることと両立しない。
その結果、入力信号に対して一定の位相差が残留する **定常位相誤差(Steady-State Phase Error)** が生じ、ステレオ信号の正確な分離が困難になる。

一方、I 制御のみの場合、制御量は

```
control = integrator
```

となり、定常位相誤差は解消できる。
しかし、NCO 自体の積分特性と合わせてループ内に積分器が 2 段直列に並ぶ二重積分系となり、位相余裕が失われる。
このため系は持続振動(発振)を生じやすく、過渡応答も劣化するため、実装上適さない。
最終的な PI 制御のコードを以下に示す。

```
control = p_gain * error + integrator
```

##### Gain の決定

PI 制御を採用した場合、系の安定性と応答は P ゲインと I ゲインにより決まる。両係数は、ループ帯域幅(`bandwidth`)と減衰係数 `zeta` の 2 変数を用いて以下のように決定した。

```
wn = 2 * np.pi * bandwidth  # wn: 自然角周波数
alpha = (2 * zeta * wn) / fs  # P-gain * Ts
beta = (wn * wn) / (fs * fs)  # I-gain * Ts**2
```

##### c.f. Gain の変数変換について

制御器(PI)の伝達関数は `p_gain + i_gain / s`、制御対象(NCO)は積分器であり `1/s` であるから、PLL 全体の開ループ伝達関数は `(p_gain*s + i_gain)/s**2` で表せる。
よって、閉ループ伝達関数 G(s) は `(p_gain*s + i_gain)/(s**2 + p_gain*s + i_gain)` と導出される。分母は s の 2 次式であり、2 次系の標準形

```
s**2 + 2*zeta*wn*s + wn**2
```

と分母の係数を比較すると、連続時間におけるゲインは

```
p_gain = 2*zeta*wn
i_gain = wn**2
```

これを前進オイラー法により離散化し、サンプル周期 Ts = 1/fs を乗じることで、離散時間の PI ゲイン `alpha`, `beta` が得られる。

#### 1.5.2.2 システムの最適化

PLL の導入後も、ステレオ・セパレーションは 0.84 dB(目標 42 dB)に留まり、THD / SINAD も目標に達していなかった。原因の分析と対策は ADR に記録した。本節では施策と結果のみを要約する(原因分析の図と導出は今後追記する)。

- **復調純度(THD / SINAD)— [ADR-006](adr/adr-006-receiver-filter-fir-iir.md)**
  - THD / SINAD はステレオ・マトリクスを通さないモノラル経路(main = L+R)で測定し、FM 復調チェーン単体の純度を評価する。
  - 19 kHz パイロットの漏洩を、15 kHz 通過 / 18 kHz 阻止の等リプル FIR による 192k→48k ポリフェーズ間引きで除去する。
  - 複素ミキシング後・周波数弁別器の前段にチャネル選択 LPF を挿入し、2·fc のイメージを除去してから瞬時位相を求める。
  - 位相特性が性能を律速する段には線形位相 FIR、それ以外の段には低次 IIR を用いる。
- **ステレオ・セパレーション — [ADR-007](adr/adr-007-stereo-separation.md)**
  - main LPF と sub BPF を同一タップ長の線形位相 FIR とし、main を群遅延分だけ遅延させて main / sub の総群遅延を一致させる(遅延整合)。
  - PLL の NCO 出力に定数の位相オフセット(`STEREO_CARRIER_PHASE_RAD`)を加え、38 kHz 再生搬送波を副搬送波に位相整合する。
  - PLL のループ帯域を 50 Hz → 200 Hz に拡大し、NCO の残留位相誤差を低減する(高 SNR 側でセパレーションが向上し、低 SNR でも劣化しないことを SNR スイープで確認した)。

結果(1 kHz・SNR 40 dB・シード固定、`make eval` の測定条件):

| メトリクス | 対策前 | 対策後 | 目標(Sony ST-5130) |
|---|---|---|---|
| THD | 1.45 % | 0.0072 % | ≤ 0.3 %(達成・ハードゲート昇格) |
| セパレーション | 0.84 dB | 45.04 dB | ≥ 42 dB(達成・ハードゲート昇格) |
| SINAD | 32 dB | 66.8 dB | ≥ 75 dB(未達・残り 8.2 dB) |

残る SINAD の目標との差は [roadmap.md](roadmap.md) の「今後の課題(モデル)」で追跡する。
