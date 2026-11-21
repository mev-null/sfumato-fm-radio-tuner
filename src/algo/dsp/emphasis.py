import numpy as np
from scipy import signal
from algo import settings


class EmphasisFilter:
    """
    FM 放送用のプリエンファシス・ディエンファシスフィルタ。
    アナログ時定数 tau から離散時間の係数を求めて適用する。プリエンファシスは
    1 + s*tau の後退差分近似(FIR)、ディエンファシスは極 p = exp(-T/tau) の 1 次 IIR とする。
    """

    def __init__(
        self,
        fs: float = settings.AUDIO_FS,
        time_constant: float = settings.TIME_CONSTANT,
    ):
        """
        Args:
            fs (float): サンプリング周波数 (Hz)
            time_constant (float): 時定数 (秒). Default: 50e-6
        """
        self.fs = fs
        self.tau = time_constant

        self.b_pre, self.a_pre = self._calc_coeffs(mode="pre")
        self.b_de, self.a_de = self._calc_coeffs(mode="de")

    def _calc_coeffs(self, mode: str):
        """
        プリエンファシス / ディエンファシスの離散時間係数を算出する
        """
        if mode == "pre":
            # --- Pre-emphasis (High-Shelf Filter) ---

            # y[n] = x[n] + alpha * (x[n] - x[n-1])
            # alpha = tau / T = tau * fs
            # 1 次差分(高域通過)成分を原信号に加算する

            alpha = self.tau * self.fs  # 例: 50e-6 * 48000 = 2.4

            # 係数: b0 = 1 + alpha, b1 = -alpha
            # H(z) = (1+alpha) - alpha*z^-1
            b = [1.0 + alpha, -alpha]
            a = [1.0]

            return b, a

        else:
            # --- De-emphasis (Low-Pass Filter) ---
            # 1 次 IIR 低域通過フィルタ(直流利得 1)
            # y[n] = (1-p)*x[n] + p*y[n-1]  (p = exp(-1/(fs*tau)))

            dt = 1.0 / self.fs
            p = np.exp(-dt / self.tau)  # 極の位置

            # IIR フィルタ係数
            # H(z) = (1-p) / (1 - p*z^-1)
            b = [1.0 - p]
            a = [1.0, -p]

            return b, a

    def pre_emphasis(self, data: np.ndarray) -> np.ndarray:
        """
        [送信] 高域を強調する (ハイシェルフ特性)
        """
        return signal.lfilter(self.b_pre, self.a_pre, data)

    def de_emphasis(self, data: np.ndarray) -> np.ndarray:
        """
        [受信] 高域を減衰させてプリエンファシスを補償し、高域雑音を抑圧する (低域通過特性)
        """
        return signal.lfilter(self.b_de, self.a_de, data)
