"""
ヘッドレス・決定論パイプライン(characterize 用ドライバ)。

main.py の TX→通信路→RX を、UI・実音源・グローバル乱数を排除して実行し、
同一入力に対して同一出力を得る決定論的な実行層。しきい値による判定は行わず、
メトリクスへ渡す信号の取得のみを責務とする。判定は characterize.py / tests 側で行う。

決定論の担保:
- AWGN は `np.random.default_rng(seed)` を注入してノイズ列を固定する。
- 評価トーンは settings の EVAL_* 条件から生成する。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from algo import settings
from algo.radio.channel import add_awgn
from algo.radio.receiver import FmReceiver
from algo.radio.transmitter import FmTransmitter
from algo.utils.audio_source import AudioSource


@dataclass
class PipelineResult:
    """パイプライン 1 回分の出力。メトリクス関数への入力をまとめる。"""

    mono: np.ndarray  # モノラル復調 main=L+R [audio_fs]（THD/SINAD 用）
    left: np.ndarray  # ステレオ復調 L チャンネル [audio_fs]
    right: np.ndarray  # ステレオ復調 R チャンネル [audio_fs]
    pll_error: np.ndarray  # PLL 位相比較器の誤差系列 [mpx_fs]
    audio_fs: float  # L/R のサンプリング周波数 [Hz]
    mpx_fs: float  # pll_error のサンプリング周波数 [Hz]


def _steady_state(
    x: np.ndarray, n_coherent: int, fir_taps: int, decim: int
) -> np.ndarray:
    """upfirdn 出力から定常区間 n_coherent サンプルを切り出す(mono / L / R 共通)。

    線形位相 FIR の群遅延 (fir_taps-1)/2(入力レート基準)を出力レートに換算した長さだけ
    先頭の過渡応答区間を除去し、その位置からコヒーレント長の区間を抽出する。
    """
    group_delay = (fir_taps - 1) // 2 // decim
    return x[group_delay : group_delay + n_coherent]


def run_pipeline(audio: np.ndarray, snr_db: float, seed: int) -> PipelineResult:
    """audio を TX→AWGN(seed固定)→RX に通し、L/R と PLL 誤差を返す。

    main.py の受信手順を UI なしで再現する。PilotPLL.process は内部状態を
    更新するため 1 回のみ呼び出し、得られた搬送波を _stereo_decode に渡す
    (_recover_carrier は併用せず、同等の正規化を本関数内で行う)。

    Args:
        audio: 入力音声 (N,) モノラル または (N, 2) ステレオ
        snr_db: 通信路の SN比 [dB]
        seed: AWGN の乱数シード(再現性のため固定)

    Returns:
        PipelineResult: 復調 L/R と PLL 誤差系列
    """
    rng = np.random.default_rng(seed)

    tx = FmTransmitter()
    rx = FmReceiver()

    rf_signal = tx.modulate(audio)
    noisy_rf = add_awgn(rf_signal, snr_db, rng=rng)

    mpx_signal = rx.process(noisy_rf)

    # モノラル復調(main=L+R のみ)。THD/SINAD はステレオ・マトリクスを経由しない
    # この経路で測定し、FM 復調チェーン単体の品質を評価する。
    mono = rx._mono_decode(mpx_signal)

    # 搬送波再生と位相誤差系列の取得(_recover_carrier は誤差系列を返さないため、ここで取得する)
    carrier_38k, pll_error = rx.pll.process(mpx_signal)

    # _recover_carrier と同一の正規化(振幅をピーク値 1.0 に正規化)
    peak = np.max(np.abs(carrier_38k))
    if peak > 0:
        carrier_38k = carrier_38k / peak

    lr = rx._stereo_decode(mpx_signal, carrier_38k)

    # 測定窓の切り出し(受信機は未加工のストリーミング出力を返すため、定常区間の抽出は
    # 測定側の責務とする)。
    # mono: THD/SINAD は各成分が FFT ビン中心に一致すること(コヒーレント標本化)を前提とするため、
    #   audio FIR の群遅延に相当する過渡応答区間を除去し、入力と同じコヒーレント長(整数周期)を抽出する。
    mono_ss = _steady_state(
        mono, n_coherent=len(audio), fir_taps=len(rx.audio_fir), decim=rx.audio_dec
    )
    # L/R: セパレーションは電力比であり、コヒーレント標本化を要しない。ステレオ FIR の分だけ群遅延が
    #   増加するため、両端の過渡区間を群遅延にマージンを加えた長さだけ除去し、残る定常区間で測定する。
    warm192 = 2 * rx.stereo_group_delay + (len(rx.audio_fir) - 1) // 2
    warm = warm192 // rx.audio_dec + 50
    return PipelineResult(
        mono=mono_ss,
        left=lr[warm:-warm, 0],
        right=lr[warm:-warm, 1],
        pll_error=pll_error,
        audio_fs=rx.audio_fs,
        mpx_fs=rx.mpx_fs,
    )


def single_tone(
    freq: float = settings.EVAL_TONE_FREQ,
    duration: float = settings.EVAL_DURATION_S,
) -> np.ndarray:
    """THD/SINAD 用の単一トーン (N,) を生成する。"""
    return AudioSource(sample_rate=settings.AUDIO_FS).sine_tone(freq, duration)


def one_channel_driven(
    freq: float = settings.EVAL_TONE_FREQ,
    duration: float = settings.EVAL_DURATION_S,
) -> np.ndarray:
    """セパレーション用に L だけ駆動・R 無音のステレオ (N, 2) を生成する。"""
    return AudioSource(sample_rate=settings.AUDIO_FS).stereo_sine_tone(
        freq_l=freq, freq_r=0.0, duration=duration
    )
