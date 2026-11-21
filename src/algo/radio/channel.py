import numpy as np


def add_awgn(
    signal: np.ndarray,
    snr_db: float,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """
    信号に白色ガウス雑音(AWGN)を加える

    Args:
        signal: 入力信号（複素数または実数）
        snr_db: 信号対雑音比 (dB)
        rng: 乱数生成器。再現性が必要な場面(品質メトリクスのゲート等)では
            `np.random.default_rng(seed)` を渡して雑音系列を固定する。
            None の場合は呼び出しごとに新しい乱数系列を用いる(通常のシミュレーション用)。

    Returns:
        noisy_signal: 雑音を付加した信号
    """
    if rng is None:
        rng = np.random.default_rng()

    sig_power = np.mean(np.abs(signal) ** 2)

    # dB 値を線形比に変換する: SNR = Ps / Pn
    # 10^(SNR/10) = Ps / Pn  =>  Pn = Ps / 10^(SNR/10)
    noise_power = sig_power / (10 ** (snr_db / 10))

    # 雑音生成(実数の雑音系列。複素入力の場合は実部にのみ加わる)
    noise_std = np.sqrt(noise_power)
    noise = rng.normal(0, noise_std, len(signal))

    return signal + noise
