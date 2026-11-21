# FM変調・送信機モデル
import numpy as np
from scipy import signal

from algo import settings
from algo.dsp.emphasis import EmphasisFilter


class FmTransmitter:
    def __init__(
        self,
        carrier_freq: float = settings.CARRIER_FREQ,
        audio_fs: float = settings.AUDIO_FS,
        rf_fs: float = settings.RF_FS,
        mpx_fs: float = settings.MPX_FS,
        max_deviation: float = settings.MAX_DEVIATION,
    ):
        """
        FM ステレオ送信機モデル
        """
        self.fc = carrier_freq
        self.audio_fs = audio_fs
        self.rf_fs = rf_fs
        self.mpx_fs = mpx_fs
        self.kf = max_deviation  # 周波数偏移感度 kf [Hz / 単位振幅]

        self.PILOT_FREQ = settings.PILOT_FREQ
        self.SUB_FREQ = settings.SUB_FREQ

        self.emphasis = EmphasisFilter(
            fs=self.audio_fs, time_constant=settings.TIME_CONSTANT
        )

    def modulate(self, audio_data: np.ndarray) -> np.ndarray:
        """
        音声信号(ステレオ (N, 2) またはモノラル (N,))を FM 変調し、実数 RF 信号を返す
        """
        # 1. 前処理 (L/R チャネルへの分解とプリエンファシス)
        if audio_data.ndim == 2:
            l_ch = audio_data[:, 0]
            r_ch = audio_data[:, 1]
        else:
            # モノラル入力は L=R として扱う
            l_ch = audio_data
            r_ch = audio_data

        l_pre = self.emphasis.pre_emphasis(l_ch)
        r_pre = self.emphasis.pre_emphasis(r_ch)

        # 2. 補間 (Audio 48k → MPX 192k)
        l_upsampled = self._upsample(l_pre, self.audio_fs, self.mpx_fs)
        r_upsampled = self._upsample(r_pre, self.audio_fs, self.mpx_fs)

        # 3. MPX 信号 (コンポジット信号) の生成
        mpx_signal = self._generate_mpx(l_upsampled, r_upsampled)

        # 4. RF レートへの補間 (MPX 192k → RF 2.304M)
        mpx_at_rf = self._upsample(mpx_signal, self.mpx_fs, self.rf_fs)

        # 5. FM 変調 (MPX の時間積分を搬送波の位相に加算)
        num_samples = len(mpx_at_rf)
        t = np.arange(num_samples) / self.rf_fs

        phase_integral = np.cumsum(mpx_at_rf) / self.rf_fs

        theta = 2 * np.pi * self.fc * t + 2 * np.pi * self.kf * phase_integral
        rf_signal = np.cos(theta)

        return rf_signal

    def _upsample(self, data: np.ndarray, fs_from: float, fs_to: float) -> np.ndarray:
        """
        整数比の補間を行う(ポリフェーズ FIR によるアップサンプリング)
        """
        up_factor = int(fs_to // fs_from)

        return signal.resample_poly(data, up_factor, 1)

    def _generate_mpx(
        self,
        l_signal: np.ndarray,
        r_signal: np.ndarray,
    ) -> np.ndarray:
        """
        L/R 信号(192kHz)から MPX 信号(192kHz)を生成する

        各成分の振幅配分(変調度の比率)
            - Main (L+R): 45%
            - Sub  (L-R): 45%
            - Pilot     : 10%
        """
        num_samples = len(l_signal)
        t = np.arange(num_samples) / self.mpx_fs

        # 1. Main Channel (L+R)
        # (L+R) / 2 * 0.9 = (L+R) * 0.45
        main = (l_signal + r_signal) * 0.45

        # 2. Pilot Signal (19kHz)
        pilot = 0.1 * np.sin(2 * np.pi * self.PILOT_FREQ * t)

        # 3. Sub Channel (L-R) DSB-SC (38kHz)
        # DSB-SC 変調: L-R 信号と 38kHz 副搬送波(sin)の乗算
        carrier = np.sin(2 * np.pi * self.SUB_FREQ * t)
        sub = ((l_signal - r_signal) * 0.45) * carrier

        # MPX 合成
        mpx = main + pilot + sub

        return mpx
