"""OPS — on-base plus slugging: OBP + SLG（兩者皆為已捨入到三位的值）.

採 MLB Stats API 的慣例：OPS 是「捨入後 OBP + 捨入後 SLG」，不是用未捨入的
分數相加。對照資料庫驗證：API 的打者 ``ops`` 與投手 ``p_ops`` 全部等於
``obp + slg``（0/301、0/416 列不符），若改用精確值相加反而約兩成的列會差 .001。
呼叫端必須傳入已捨入的 OBP、SLG，同一張表的合計列才會與 API 的單季列一致。
"""

from ...util.numbers import round_half_up


def compute_ops(obp, slg):
    # OBP 或 SLG 缺值
    if obp is None or slg is None:
        return None
    # 兩個三位小數相加只會有浮點尾差，round_half_up 以最短 repr 捨入即可消除
    return round_half_up(obp + slg, 3)
