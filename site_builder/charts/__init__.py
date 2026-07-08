"""Matplotlib static-chart engine (build-time PNG output).

Depends only on stats/, constants, util/ — same layer as graph/.
"""

# 先 import style 讓 matplotlib.use("Agg") 保證在任何子模組的 pyplot
# import 之前執行（子模組經由本套件載入時，__init__ 一定先跑）。
from . import style  # noqa: F401
