import numpy as np

from algo import settings


class PilotPLL:
    def __init__(
        self,
        fs: float = settings.MPX_FS,
        center_freq: float = settings.PILOT_FREQ,
        bandwidth: float = settings.PLL_BANDWIDTH,
        out_phase_offset: float = 0.0,
    ):
        """
        Args:
            fs: サンプリング周波数 (192000)
            center_freq: 同期対象の公称周波数 (19000)
            bandwidth: ループ帯域幅 (Hz)。ループの追従速度(応答帯域)を決定する。
            out_phase_offset: 38kHz 出力搬送波に加算する位相 [rad]。ループ特性は変更せず、
                NCO 出力にのみ位相回転を与える(ステレオ検波の位相整合に用いる)。
        """
        self.fs = fs
        self.center_freq = center_freq
        self.out_phase_offset = out_phase_offset

        # --- ループ係数の算出 ---
        # 連続時間 2 次 PLL の設計式から離散時間の係数を導出する
        zeta = settings.PLL_DAMPING

        # 自然角周波数 wn
        wn = 2 * np.pi * bandwidth

        # デジタル・ループフィルタ係数 (K1, K2)
        # alpha: 比例ゲイン
        # beta:  積分ゲイン
        self.alpha = (2 * zeta * wn) / fs
        self.beta = (wn * wn) / (fs * fs)

        # --- 内部状態の初期化 ---
        self.phase = 0.0  # 現在のNCOの位相
        self.freq_integrator = 0.0  # 積分器 (周波数偏差の推定値)

    def process(self, signal_in: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        n_samples = len(signal_in)

        # 出力用バッファ
        carrier_38k = np.zeros(n_samples)
        error_log = np.zeros(n_samples)  # 位相誤差の記録(ロック判定・解析用)

        # 1 サンプルあたりの公称位相増分 (19kHz 相当)
        center_phase_step = 2 * np.pi * self.center_freq / self.fs

        # 属性参照を避けるためローカル変数へ展開する
        current_phase = self.phase
        integrator = self.freq_integrator

        for i in range(n_samples):
            sample = signal_in[i]

            # A. NCO 出力の生成
            # 現在位相における余弦値を求める
            nco_cos = np.cos(current_phase)

            # B. 位相比較器 (Phase Detector)
            # 入力と NCO 出力の乗算による位相検波
            error = sample * nco_cos

            # C. ループフィルタ (Loop Filter)
            # 1. 積分項の更新 (積分値 + beta × 位相誤差)
            integrator += self.beta * error

            # 2. 制御量 u の算出 (積分項 + alpha × 位相誤差)
            control = integrator + self.alpha * error

            # D. NCO更新 (Update Phase)
            # 次の位相 = 現在位相 + 公称位相増分 + 制御量 u
            current_phase += center_phase_step + control

            # 位相を [0, 2π) の範囲に折り返す
            if current_phase > 2 * np.pi:
                current_phase -= 2 * np.pi
            elif current_phase < 0:
                current_phase += 2 * np.pi

            # E. 出力生成 (38kHz)
            # 19kHz の位相(current_phase)を 2 倍して 38kHz の正弦波を生成する(周波数逓倍)。
            # 位相補正 out_phase_offset を加算し、ステレオ検波の位相を整合させる。
            carrier_38k[i] = np.sin(2 * current_phase + self.out_phase_offset)

            # 位相誤差の記録
            error_log[i] = error

        self.phase = current_phase
        self.freq_integrator = integrator

        return carrier_38k, error_log
