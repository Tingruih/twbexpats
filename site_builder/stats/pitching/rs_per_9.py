"""RS/9 — run support per nine innings: run support × 27 / outs.

只在 API 沒給 ``rs_per_9`` 時由 ``annotate_row`` 補值。注意 API 的來源欄位
``runsScoredPer9`` 實際上是失分率（RA9 = R × 27 / outs，對照資料庫驗證），
與本公式語意不同；目前模板沒有顯示這個欄位。
"""

from ..core.innings import per_nine


def compute_rs_per_9(run_support, outs):
    return per_nine(run_support, outs)
