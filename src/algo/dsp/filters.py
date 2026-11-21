"""受信機で用いる FIR フィルタの設計(係数算出)。"""

import numpy as np
from scipy import signal

from algo import settings


def design_audio_decimation_fir() -> np.ndarray:
    """15kHz 帯域制限 + 192k→48k 間引きを兼ねる線形位相 FIR の係数 h を返す。

    仕様は settings: 通過域端 AUDIO_BAND_HZ(15k)/ 阻止域端 AUDIO_LPF_STOP_HZ(18k)/
    阻止域減衰量 AUDIO_LPF_STOP_ATTEN_DB(60dB)。等リプル設計(remez / Parks-McClellan)で
    阻止域に通過域の 10 倍の重みを与え、19kHz パイロットを阻止域内で減衰させる。
    係数は固定(将来の HW 移植では係数 ROM に相当)であるため設計は本モジュールで完結させ、
    適用(ポリフェーズ間引き upfirdn(h, x, up=1, down=4))は受信機側で行う。
    """
    bands = [0, settings.AUDIO_BAND_HZ, settings.AUDIO_LPF_STOP_HZ, settings.MPX_FS / 2]
    desired = [1, 0]
    weights = [1, 10]

    # タップ数の見積もり: Kaiser の近似式 N ≈ (A − 8) / (2.285 · 2π · Δf/fs)
    # (Δf=4kHz, fs=192kHz, A=60dB → ≈175)を等リプル設計にも準用する。
    numtaps = 175
    return signal.remez(numtaps, bands, desired, weight=weights, fs=settings.MPX_FS)


def design_stereo_fir() -> tuple[np.ndarray, np.ndarray]:
    """ステレオ復調用の線形位相 FIR(main LPF と sub BPF)を返す (roadmap 1.5.3)。

    両者を同一タップ長 STEREO_FIR_TAPS(奇数)として群遅延 (N-1)/2 を一致させ、
    main/sub の遅延整合を可能にする。線形位相であるため「副搬送波 = 2 × パイロット」の
    位相関係が保存され、ステレオ・セパレーションが成立する。
    """
    n = settings.STEREO_FIR_TAPS
    main_lpf = signal.firwin(n, settings.AUDIO_BAND_HZ, fs=settings.MPX_FS)
    sub_bpf = signal.firwin(
        n,
        [settings.SUB_BAND_LOW_HZ, settings.SUB_BAND_HIGH_HZ],
        pass_zero=False,
        fs=settings.MPX_FS,
    )
    return main_lpf, sub_bpf
