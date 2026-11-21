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
from algo.utils.visualizer import plot_stereo_analysis


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
        image_filename = str(root_dir / "outputs" / f"{base_name}_analysis.png")
        plot_stereo_analysis(
            audio_data, demodulated_audio, settings.AUDIO_FS, image_filename
        )
        RadioUI.log("IO", f"Graph saved to {image_filename}", RadioUI.GREEN)
        plt.show()

    except Exception as e:
        import traceback

        traceback.print_exc()
        RadioUI.log("ERROR", f"Graph generation failed: {e}", RadioUI.RED)


if __name__ == "__main__":
    main()
