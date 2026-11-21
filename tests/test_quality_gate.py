"""
復調品質の回帰ゲート(roadmap 1.7)。

実際の TX→通信路→RX パイプライン出力をメトリクスで評価し、
(A) 絶対しきい値ゲート と (B) baseline 回帰ゲート により品質を保証する。

運用方針(ラチェット):
- 絶対しきい値ゲート(A)は市販製品(Sony)のスペックを目標値とする。現行アルゴリズムが
  未達の間は strict xfail とし、CI を成功状態に保ちつつ目標との差を毎回測定する。
  アルゴリズムが仕様に到達すると xpass(strict により失敗扱い)となり、ハードゲートへの
  昇格時期であることが通知される。昇格は該当テストの xfail マークを除去して行う。
- 回帰ゲート(B)はハードゲートとする。baseline からの劣化を毎回のコミットで検出し、品質の下限を保持する。
- しきい値・許容幅・PLL tol が None の場合、および baseline が未生成の場合は skip する。

数値は利用者が確定する(rule 12 / docs/adr/adr-005-demod-quality-gate.md)。
"""

import pytest

from algo import settings
from algo.eval.characterize import build_report, current_conditions, load_baseline


@pytest.fixture(scope="module")
def report():
    """TX/RX の計算コストが大きいため、測定はモジュール単位で 1 回のみ行い、テスト間で共有する。"""
    return build_report()


# --- (A) 絶対しきい値ゲート(Sony スペック目標 / strict xfail で追跡) --------
# dB 系(SINAD・セパレーション)は値が大きいほど良好 → 下限を課す。
# THD・ロック時間は値が小さいほど良好 → 上限を課す。
# 未達の間は xfail(成功扱い)、到達すると xpass(strict により失敗扱い)となりハードゲートへの昇格を促す。

_SONY_TARGET = "Sony 製品スペック目標。到達したら xfail を外しハードゲートへ昇格する"


# THD はモノラル復調経路で Sony 絶対しきい値(0.3%)に到達したためハードゲートへ昇格。
# (roadmap 1.7 ラチェット運用。SINAD・セパレーションは未達のため strict xfail のまま追跡)
def test_thd_below_absolute_ceiling(report):
    if settings.THD_MAX is None:
        pytest.skip("settings.THD_MAX 未設定(利用者が観測値から確定する)")
    assert report["metrics"]["thd"] <= settings.THD_MAX


@pytest.mark.xfail(reason=_SONY_TARGET, strict=True)
def test_sinad_above_absolute_floor(report):
    if settings.SINAD_MIN_DB is None:
        pytest.skip("settings.SINAD_MIN_DB 未設定(利用者が観測値から確定する)")
    assert report["metrics"]["sinad_db"] >= settings.SINAD_MIN_DB


# セパレーションはステレオ復調の線形位相 FIR 化・遅延整合・搬送波位相整合・PLL 帯域最適化で
# Sony 絶対しきい値(42dB)に到達したためハードゲートへ昇格(roadmap 1.5.3 / 1.7 ラチェット)。
def test_separation_above_absolute_floor(report):
    if settings.SEPARATION_MIN_DB is None:
        pytest.skip("settings.SEPARATION_MIN_DB 未設定(利用者が観測値から確定する)")
    assert report["metrics"]["separation_db"] >= settings.SEPARATION_MIN_DB


def test_pll_lock_within_budget(report):
    if settings.PLL_LOCK_MAX_S is None:
        pytest.skip("settings.PLL_LOCK_MAX_S 未設定(利用者が観測値から確定する)")
    lock = report["metrics"]["pll_lock_time_s"]
    if lock is None:
        pytest.skip("PLL_LOCK_TOL/HOLD_SAMPLES 未設定でロック時間が未計測")
    assert lock <= settings.PLL_LOCK_MAX_S


# --- (B) baseline 回帰ゲート ---------------------------------------------------
# baseline.json の基準値から、品質が低下する方向へ許容幅を超えて変化した場合に fail とする。


def test_no_regression_against_baseline(report):
    if settings.REGRESSION_TOL is None:
        pytest.skip("settings.REGRESSION_TOL 未設定(利用者が許容幅を確定する)")

    base = load_baseline()
    if base is None:
        pytest.skip("baseline.json 未生成(先に make characterize を実行する)")

    # 測定条件が異なる場合、基準値は無効であり比較しない。
    assert base["conditions"] == current_conditions(), (
        "測定条件が baseline と異なる。make characterize で baseline を再生成する"
    )

    tol = settings.REGRESSION_TOL
    cur = report["metrics"]
    base_m = base["metrics"]

    # 値が大きいほど良好な指標: 低下を検出する
    assert cur["sinad_db"] >= base_m["sinad_db"] * (1 - tol)
    assert cur["separation_db"] >= base_m["separation_db"] * (1 - tol)

    # 値が小さいほど良好な指標: 増加を検出する
    assert cur["thd"] <= base_m["thd"] * (1 + tol)

    # PLL ロック時間は双方が None でない場合のみ比較する
    if cur["pll_lock_time_s"] is not None and base_m["pll_lock_time_s"] is not None:
        assert cur["pll_lock_time_s"] <= base_m["pll_lock_time_s"] * (1 + tol)
