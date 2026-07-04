① 職責拆分是否過細 —— 這是最主要的問題

- 重災區:stats/batting/、stats/pitching/。13+13 個檔案裡多數是「1 docstring + 3~5 行函式」,而且多半只是 round(x/y, n)。建議併為 batting/rates.py + pitching/rates.py,可一併消掉 core/annotate.py:9-27 近 20 行 import。import 站點僅 6 處,合併風險低。
- 反向問題(檔案太大):sync/statcast.py 542 行把 game 抓取 / pitch 回寫 / sabermetrics 抓取 / FIP 計算 / merge 全塞一起;render/pages.py 454 行把 orchestration 與資料塑形(statcast_by_year 組裝 pages.py:330-375、chart data、fielding 聚合)混在單一 build 函式。兩者都可再切一層。
- 死程式碼:db/players.py:39-46 get_positions 全庫無呼叫。
- 相對地,stats/discipline/、stats/batted_ball/ 的細拆是合理的——它們各自持有一個「定義」(barrel 窗、hard-hit 門檻),且都吃共用的 aggregate_pitches 結果,不重複遍歷。

② 數據正確性

- combine.py / weighted.py 合計列加權(最實質):_wpct 對每個 rate 都用同一個權重欄位(total_pitches / bbe / count)。當 rate 的真實分母等於權重時(swing%、csw%、zone%、barrel%、gb/fb%)是精確的;但 whiff_pct(分母=揮棒數)、z_swing_pct/o_swing_pct(分母=區內/區外球)、z_contact_pct、hr_fb_pct(分母=飛球)被用 total_pitches/bbe 加權,只在「跨層合計(合計)」列會算出偏差值(可差幾個百分點)。正解:比照 career.py 對 AVG/OBP 的做法,存原始分子/分母並加總後重算,而非平均已算好的比率。
- xwpct.py:分子 FIP 是自責分尺度、分母 LEAGUE_RA9 是全失分尺度,系統性略高估;docstring 稱「Pythagenpat exponent 1.83」名稱有誤(1.83 是固定指數,非動態)。
- xbh.py:2B/3B/HR 皆為真實 0 時回 None 而非 0,有打數卻無長打者顯示空白。
- api/players.py:65-71:同函式 transactions 有 sorted(reverse=True),rosterEntries 卻直接 [0],取最新的假設未驗證。
- 兩個 cache 的 INSERT OR REPLACE:只 upsert 本次回傳的 league,某 league 這次沒回傳時舊列殘留。
- 邊界(低):era.py/whip.py 對 ER/BB 為 None 但 IP 存在時算出 0 而非 None(MLB 資料實務不缺,可接受)。

③ 小數精細度 / 截斷

- compute_ev90(exit_velocity.py:24):idx = min(int(len*0.9), len-1),int() 截斷 + 0-indexed,n=10 時直接取最大值 → EV90 偏高。註解已自承「小於 10 顆會與 TJStats 不符」,但 ≥10 也有系統性 off-by-one。建議用線性內插或一致的 nearest-rank。
- wOBA 兩種精度:compute_pitch_woba(woba.py:23,經 ratio 捨入到 3 位)vs compute_season_woba(woba.py:59,不捨入);前者的 3 位值又在 combine.py 被 PA 加權後再捨入(先捨再算)。應讓 pitch 版回未捨入值對齊。
- per-9 家族位數不一:k/bb/h 為 1 位、hr/rs 為 2 位。
- slash-line 型別混用:field_maps.py 把 win_pct/strike_pct/p_avg/p_obp/p_slg/p_ops/各 _pct 以 str() 存 DB;compute 版又回 fmt_avg 字串,opponent_slash.py:47-48 只好 safe_float 反解析回 float 才能算 OPS。
- 捨入模式不一致:filters.floatformat(Python 預設 round-half-even)vs filters.pct_fmt(ROUND_HALF_UP)。

④ 函式功能重複

- per-9 ×5、bb_pct≡k_pct(維度②同源)
- 三個 table builder(arsenal/outcomes/vs_pitch_types)骨架相同,僅 rate 欄位不同 → 可抽 build_pitch_type_table(pitches, columns_fn, ...)
- 兩個 cache 模組三組相同 load/save/get(僅 fip 多「進行中賽季強制重抓」)→ 抽 cached_lookup(load, fetch, save, force_refresh, always_refetch)
- api/stats.py 5 函式共 ~10 份相同 try/except/extend 樣板;api/tjstats.py 兩函式相同 requests→BeautifulSoup→select 流程
- pre-count 邏輯兩份:extract.py:96-182(抽取時計算)與 core/pitches.py:99-135 ensure_pre_strikes(cache 回填)各實作一次、reset 策略略不同
- type_name「有真名就升級」的小 pattern 散在 movement/plinko/usage_by_count 多處

⑤ 重造輪子 / 可重用既有 function

- batting/pitching counting 公式手寫 None-guard 除法,util.numbers.ratio() 早已存在(分母皆非負,not den 與 <=0 等價,可直接換)。注意:batted_ball 與 discipline 層已全面採用 ratio/mean_round,殘留主要在 batting/pitching。
- api/tjstats.py 用 print("WARNING") 而非 logging、手寫 float()+except 而非 float_or_none
- filters.jsonld 重複 dumps_json 的 compact separators(但需 Markup+HTML-safe,僅部分可重用)
- db/season_stats.load_season_row 用泛型 loads_json(...,{}) 而非既有 loads_json_dict/list
- 反例(做得對,值得肯定):sync/statcast.py 正確重用 compute_pitcher/batter_statcast,完全沒有重造逐球分類;graph/movement.py、graph/plinko.py 重用 core/pitches 的分類 helper;JSON 處理在 api/db 全走 util.json,無裸 json.loads。

⑥ 檔名是否符合功能

- pitching/strike_pct(counting,回字串)vs discipline/pitch_strike_pct(pitch-level,回 float):同名同顯示標籤「Strike%」但定義與型別皆不同 → 建議其一改名(如 strike_pct_counting)。
- babip.py/go_ao.py/p_per_pa.py:docstring 寫 batter+pitcher 共用,卻放 batting/(pitcher 版從 ..batting.* import)→ 宜移到 stats/core/ 或 stats/shared/。
- db/game_logs.py:名字像「game_logs 表存取層」,實際只有一個 pitch-cache 讀取函式;寫入散在 sync/players.py。db/players.py 同樣只讀、寫在 sync → 「db 層」持久化職責散落在 db/ 與 sync/ 兩處。
- api/games.py::sport_obj_to_abbr 較適合放 levels.py。