import numpy as np
import os
import time
from pathlib import Path
import matplotlib.pyplot as plt

from algo import settings
from algo.radio.transmitter import FmTransmitter
from algo.radio.receiver import FmReceiver
from algo.radio.channel import add_awgn
from algo.component.radio_ui import RadioUI
from algo.utils.load_and_preprocess_wav import load_and_preprocess_wav
from algo.utils.output_audio import save_audio
from algo.utils.audio_source import AudioSource


def main():
    # --- UI起動 ---
    RadioUI.header()

    # --- 設定 ---
    # パス解決(カレントディレクトリに依存しない): 入力 inputs/・出力 outputs/ をプロジェクトルート基準とする。
    root_dir = Path(__file__).resolve().parents[2]  # プロジェクトルート
    INPUT_FILE = str(root_dir / settings.INPUT_FILE)
    base_name = os.path.splitext(os.path.basename(INPUT_FILE))[0]
    OUTPUT_FILE = str(root_dir / "outputs" / f"{base_name}_restored.wav")
    TARGET_SNR = settings.DEFAULT_SNR_DB

    # 入力音源が存在しない場合は試験信号を合成する
    if not os.path.exists(INPUT_FILE):
        RadioUI.log(
            "SYSTEM",
            "Input file missing. Generating Stereo Time Signal...",
            RadioUI.YELLOW,
        )
        source = AudioSource()
        # ステレオ時報信号の生成 (L: 低い周波数, R: 高い周波数)
        melody = source.stereo_time_tone()
        save_audio(melody, fs=48000, filename=INPUT_FILE)

    # --- 1. 送信機 (Transmitter) ---
    print(f"\n{RadioUI.BOLD}--- [1] Transmitter Station ---{RadioUI.RESET}")
    RadioUI.log(
        "PREPROCESS", f"Loading '{os.path.basename(INPUT_FILE)}'...", RadioUI.BLUE
    )

    # ステレオWAVの読み込み (N, 2)
    audio_data = load_and_preprocess_wav(INPUT_FILE, settings.AUDIO_FS)

    RadioUI.log("MODULATION", "FM Stereo Modulation in progress...", RadioUI.BLUE)
    tx = FmTransmitter()
    rf_signal = tx.modulate(audio_data)

    RadioUI.on_air_animation(duration=2)

    # --- 2. 通信路 (Channel) ---
    print(f"{RadioUI.BOLD}--- [2] Wireless Channel ---{RadioUI.RESET}")
    RadioUI.log("CHANNEL", f"Applying AWGN (SNR={TARGET_SNR}dB)...", RadioUI.YELLOW)

    # AWGN の付加
    noisy_rf_signal = add_awgn(rf_signal, TARGET_SNR)
    time.sleep(1)

    # --- 3. 受信機 (Receiver) ---
    print(f"\n{RadioUI.BOLD}--- [3] Receiver Device ---{RadioUI.RESET}")
    RadioUI.tuning_animation()

    rx = FmReceiver()

    # A. RF信号 -> MPX信号 (192kHz)
    RadioUI.log("DEMODULATION", "Quadrature Demodulation to MPX...", RadioUI.CYAN)
    mpx_signal = rx.process(noisy_rf_signal)

    # B. パイロットへの同期と 38kHz 搬送波の再生
    RadioUI.log("STEREO", "Recovering 38kHz Sub-carrier...", RadioUI.CYAN)
    carrier_38k = rx._recover_carrier(mpx_signal)

    # C. ステレオ分離 (マトリクス復号)
    RadioUI.log("STEREO", "Decoding L/R Channels...", RadioUI.CYAN)
    demodulated_audio = rx._stereo_decode(mpx_signal, carrier_38k)

    # --- 4. 保存 ---
    print(f"\n{RadioUI.BOLD}--- [4] Output ---{RadioUI.RESET}")
    RadioUI.log("IO", f"Saving audio to {OUTPUT_FILE}", RadioUI.GREEN)

    # ピークを gain に正規化して保存する(入力との振幅比較には normalize=False を用いる)
    save_audio(demodulated_audio, rx.audio_fs, OUTPUT_FILE, normalize=True, gain=0.9)
    RadioUI.reception_success(OUTPUT_FILE)

    # --- 5. 解析グラフの生成 (ステレオ) ---
    try:
        RadioUI.log("VISUALIZER", "Generating Stereo Analysis Graph...", RadioUI.DIM)

        # 補助関数: 入力形状によらず L, R の 2 系列を返す
        def split_channels(data):
            # 1次元 (N,) -> モノラル (L=R)
            if data.ndim == 1:
                return data, data
            # 2次元 (N, 2) -> ステレオ
            elif data.ndim == 2 and data.shape[1] == 2:
                return data[:, 0], data[:, 1]
            # 2次元 (N, 1) -> モノラル
            elif data.ndim == 2 and data.shape[1] == 1:
                flat = data.flatten()
                return flat, flat
            else:
                raise ValueError(f"Unexpected data shape: {data.shape}")

        # 入力・出力を L/R 系列に分解する
        in_l, in_r = split_channels(audio_data)
        out_l, out_r = split_channels(demodulated_audio)

        # 復調波形は受信フィルタの群遅延だけ遅延し、振幅スケールも入力と異なる。
        # 相互相関で遅延を推定して時間整列し、RMS で振幅を整合させ、定常区間を重ねて表示する(表示専用)。
        def estimate_lag(in_ch, out_ch):
            m = min(len(in_ch), len(out_ch))
            seg = slice(m // 4, m // 4 + min(40000, m // 2))
            x = in_ch[seg] - np.mean(in_ch[seg])
            y = out_ch[seg] - np.mean(out_ch[seg])
            xc = np.correlate(y, x, mode="full")
            return int(np.argmax(np.abs(xc)) - (len(x) - 1))

        limit = 1000  # 拡大表示するサンプル数
        lag = estimate_lag(in_l, out_l)  # 群遅延 [サンプル]
        start = min(len(in_l) // 4, max(0, len(in_l) - limit - abs(lag)))

        def gain_match(in_ch, out_ch):
            """遅延整列した全区間の RMS 比から、出力に乗じる振幅補正係数を求める(表示用)。

            受信機の周波数弁別器は出力を最大周波数偏移で正規化していないため、
            出力は入力に対して一定の利得(約 −14.7 dB)をもつ。時間波形と PSD の
            双方に同一の係数を適用し、入出力を同一スケールで比較できるようにする。
            """
            if lag >= 0:
                i, o = in_ch, out_ch[lag:]
            else:
                i, o = in_ch[-lag:], out_ch
            n = min(len(i), len(o))
            ri, ro = np.sqrt(np.mean(i[:n] ** 2)), np.sqrt(np.mean(o[:n] ** 2))
            return ri / ro if ro > 0 else 1.0

        gain_l = gain_match(in_l, out_l)
        gain_r = gain_match(in_r, out_r)
        out_l = out_l * gain_l
        out_r = out_r * gain_r

        def aligned(in_ch, out_ch):
            """定常区間を遅延整列して (入力, 出力) を返す(表示用。出力は振幅補正済み)。"""
            i = in_ch[start : start + limit]
            o = out_ch[start + lag : start + lag + limit]
            return i, o

        plt.figure(figsize=(14, 10))
        t_axis = np.arange(limit) / settings.AUDIO_FS * 1000
        delay_ms = lag / settings.AUDIO_FS * 1000

        # --- [左上] Left Ch 時間波形(遅延整列・振幅整合)+ 残差 ---
        in_l_d, out_l_d = aligned(in_l, out_l)
        plt.subplot(2, 2, 1)
        plt.plot(t_axis, in_l_d, label="In (L)", color="blue", alpha=0.5)
        plt.plot(
            t_axis, out_l_d, label="Out (L)", color="cyan", alpha=0.8, linestyle="--"
        )
        plt.plot(
            t_axis, in_l_d - out_l_d, label="In−Out", color="gray", alpha=0.6, lw=0.8
        )
        plt.title(f"Left Channel (Time Domain, delay {delay_ms:.2f}ms aligned)")
        plt.xlabel("Time [ms]")
        plt.ylabel("Amplitude")  # 直流成分を持たない信号のため 0 を中心に正負へ振れる
        plt.legend(loc="upper right")
        plt.grid(True, alpha=0.3)

        # --- [右上] Right Ch 時間波形(遅延整列・振幅整合)+ 残差 ---
        in_r_d, out_r_d = aligned(in_r, out_r)
        plt.subplot(2, 2, 2)
        plt.plot(t_axis, in_r_d, label="In (R)", color="red", alpha=0.5)
        plt.plot(
            t_axis, out_r_d, label="Out (R)", color="orange", alpha=0.8, linestyle="--"
        )
        plt.plot(
            t_axis, in_r_d - out_r_d, label="In−Out", color="gray", alpha=0.6, lw=0.8
        )
        plt.title("Right Channel (Time Domain, delay aligned)")
        plt.xlabel("Time [ms]")
        plt.ylabel("Amplitude")
        plt.legend(loc="upper right")
        plt.grid(True, alpha=0.3)

        # --- [左下] Left Ch 周波数特性 (PSD) ---
        plt.subplot(2, 2, 3)
        plt.title(
            f"Left Channel (PSD, output gain-matched {20 * np.log10(gain_l):+.1f} dB)"
        )
        plt.psd(in_l, Fs=settings.AUDIO_FS, NFFT=1024, color="blue", label="In (L)")
        plt.psd(
            out_l,
            Fs=settings.AUDIO_FS,
            NFFT=1024,
            color="cyan",
            label="Out (L)",
            linestyle="--",
        )
        plt.xlim(0, 15000)
        plt.legend(loc="upper right")

        # --- [右下] Right Ch 周波数特性 (PSD) ---
        plt.subplot(2, 2, 4)
        plt.title(
            f"Right Channel (PSD, output gain-matched {20 * np.log10(gain_r):+.1f} dB)"
        )
        plt.psd(in_r, Fs=settings.AUDIO_FS, NFFT=1024, color="red", label="In (R)")
        plt.psd(
            out_r,
            Fs=settings.AUDIO_FS,
            NFFT=1024,
            color="orange",
            label="Out (R)",
            linestyle="--",
        )
        plt.xlim(0, 15000)
        plt.legend(loc="upper right")

        plt.tight_layout()

        # 保存と表示
        image_filename = str(root_dir / "outputs" / f"{base_name}_analysis.png")
        plt.savefig(image_filename)
        RadioUI.log("IO", f"Graph saved to {image_filename}", RadioUI.GREEN)
        plt.show()

    except Exception as e:
        import traceback

        traceback.print_exc()
        RadioUI.log("ERROR", f"Graph generation failed: {e}", RadioUI.RED)


if __name__ == "__main__":
    main()
