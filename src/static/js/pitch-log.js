/**
 * pitch-log.js — 逐球 Pitch Log 載入與渲染
 * 載入於：tab_gamelogs.j2（逐場紀錄 Tab）
 *
 * 作用：點擊比賽列展開箭頭時，動態 fetch 並渲染該場比賽的逐球資料表格。
 * 資料格式：JSON 陣列（每個物件為一球的速度/球種/結果等）
 *
 * 主要函式：
 *  - pitchLogCache            ：記憶體快取，避免同一場比賽重複 fetch
 *  - _buildPitchTable(pitches)：將逐球 JSON 資料轉成 HTML 表格字串
 *  - _loadPitchLogData(src)   ：fetch + 解析 JSON + 存入快取，回傳 Promise
 *  - prefetchPitchLogRow(row) ：預先 fetch 單一比賽列的 pitch log（但不渲染）
 *  - prefetchFilteredPitchLogs：批次預載目前篩選結果中所有可見比賽的 pitch log
 *  - togglePitchLog(id)       ：展開/收合逐球區域，首次展開時觸發懶載入渲染
 */
var pitchLogCache = Object.create(null);
var escapePitchLogHtml = window.TW.escapeHtml;

// 格式化數值，null/空值回傳 '-'
function _fmt(v, d) {
    if (v == null || v === '') return '-';
    return d != null ? Number(v).toFixed(d) : v;
}

// 單球結果中文對照（值來自 MLB API playEvents[].details.description）
//
// 涵蓋範圍依據 /api/v1/pitchCodes 的 39 個官方代碼逐一比對。extract.py 只收
// isPitch=true 的事件，因此下面第一組（實測驗證）已是 Result 欄實際會出現的
// 全部字串；第二、三組為官方代碼存在但實測未出現的情況，先備妥避免漏譯。
var RESULT_ZH = {
    // 一、已實測驗證：本站 DB 15,506 場（2002–2026，含 MiLB）+ 抽樣 420 場
    // MLB（2008–2025）出現過的全部 isPitch 描述，共 16 種
    'Ball':                      '壞球',                 // B
    'Ball In Dirt':              '落地壞球',             // *B
    'Intent Ball':               '故意壞球',             // I
    'Pitchout':                  '防盜壘外投球',         // P
    'Called Strike':             '未揮棒好球',           // C
    'Swinging Strike':           '揮空',                 // S
    'Swinging Strike (Blocked)': '揮空（觸地）',         // W
    'Foul':                      '界外',                 // F
    'Foul Tip':                  '擦棒被捕',             // T、O（觸擊擦棒也回傳此值）
    'Foul Bunt':                 '觸擊界外',             // L
    'Foul Pitchout':             '外投球界外',           // R
    'Missed Bunt':               '觸擊落空',             // M
    'In play, out(s)':           '擊出（出局）',         // X、Y
    'In play, no out':           '擊出（未出局）',       // D、J
    'In play, run(s)':           '擊出（得分）',         // E、Z
    'Hit By Pitch':              '觸身球',               // H

    // 二、官方代碼存在但實測未出現（Q/K/A/V），描述字串依同組代碼的命名規則推得
    'Swinging Pitchout':         '外投球揮空',           // Q
    'Unknown Strike':            '好球（未分類）',       // K
    'Automatic Strike':          '自動好球',             // A
    'Automatic Ball':            '自動壞球',             // V

    // 三、自動好壞球（違規判定）：實測皆為 isPitch=false / type=no_pitch，
    // 目前不會進入逐球資料；此處備妥，日後若放寬過濾條件即可直接對應
    'Automatic Ball - Intentional':                   '自動壞球（故意四壞）',     // VB
    'Automatic Ball - Pitcher Pitch Timer Violation': '自動壞球（投手違反計時）', // VP
    'Automatic Ball - Catcher Pitch Timer Violation': '自動壞球（捕手違反計時）', // VC
    'Automatic Ball - Shift Violation':               '自動壞球（違反佈陣限制）', // VS
    'Automatic Strike - Batter Pitch Timer Violation': '自動好球（打者違反計時）', // AC
    'Automatic Strike - Batter Timeout Violation':     '自動好球（打者違規暫停）', // AB
};

// 蒐集該場實際出現過的 result，依出現次數由多到少排序（次數相同維持首次出現順序），
// 序列化後掛在 Result 表頭上，供 tooltip 顯示中文對照
function _resultLegend(pitches) {
    var counts = Object.create(null);
    var order = [];
    for (var i = 0; i < pitches.length; i++) {
        var r = pitches[i].result;
        if (!r) continue;
        if (counts[r] == null) {
            counts[r] = 0;
            order.push(r);
        }
        counts[r]++;
    }
    order.sort(function (a, b) { return counts[b] - counts[a]; });
    return order.map(function (r) { return [r, RESULT_ZH[r] || '']; });
}

// pitch_type 會成為 CSS class token，只接受單一、有限長度的安全 token。
function _pitchTypeClass(value) {
    var token = String(value == null ? '' : value).toLowerCase();
    return /^[a-z0-9_-]{1,32}$/.test(token) ? token : 'unknown';
}

// 蒐集該場實際出現過的球種，依出現次數由多到少排序（次數相同維持首次出現
// 順序），序列化後掛在 Type 表頭上，供 tooltip 顯示中英對照。比照「進階數據」
// 逐球種表格的 pitch_legend() 邏輯：中英文名經 window.TW.pitchTypeInfo() 讀
// #pitch-type-data（單一真相來源＝constants.py 的 PITCH_TYPES），查無中文譯名
// 的非球種代碼（IN/PO 等）直接略過，顯示名重複時只留一行。
function _typeLegend(pitches) {
    var counts = Object.create(null);
    var order = [];
    var nameByCode = Object.create(null);
    for (var i = 0; i < pitches.length; i++) {
        var code = String(pitches[i].pitch_type || '').toUpperCase();
        if (!code) continue;
        if (counts[code] == null) {
            counts[code] = 0;
            order.push(code);
            nameByCode[code] = pitches[i].pitch_name || code;
        }
        counts[code]++;
    }
    order.sort(function (a, b) { return counts[b] - counts[a]; });

    var pairs = [];
    var seen = Object.create(null);
    for (var j = 0; j < order.length; j++) {
        var info = window.TW.pitchTypeInfo(order[j]);
        if (!info || !info.zh) continue;
        var name = nameByCode[order[j]];
        if (seen[name]) continue;
        seen[name] = true;
        pairs.push([name, info.zh]);
    }
    return pairs;
}

// 將逐球 JSON 數據轉成 HTML 表格字串（編號/球數/局倒/球種/車速/區帶等欄位）
function _buildPitchTable(pitches) {
    var hasVideo = pitches.some(function (p) { return p.video || p.play_id; });
    var legend = _resultLegend(pitches);
    var legendAttr = legend.length
        ? ' data-legend="' + escapePitchLogHtml(JSON.stringify(legend)) + '"'
        : '';
    var typeLegend = _typeLegend(pitches);
    var typeLegendAttr = typeLegend.length
        ? ' data-legend="' + escapePitchLogHtml(JSON.stringify(typeLegend)) + '"'
        : '';
    var h = '<table class="pitch-log-table"><thead><tr>' +
        '<th data-tooltip="投球序號">#</th><th data-tooltip="投球前球數\\nBall-Strike">Count</th><th data-tooltip="局數">INN</th><th data-tooltip="球種"' + typeLegendAttr + '>Type</th><th data-tooltip="球速">Speed</th>' +
        '<th data-tooltip="進壘區域" data-diagram="zone">Zone</th><th data-tooltip="單球結果"' + legendAttr + '>Result</th><th data-tooltip="擊球初速">EV</th><th data-tooltip="擊球仰角">LA</th>' +
        '<th data-tooltip="誘導垂直位移">iVB</th><th data-tooltip="水平位移">HB</th><th data-tooltip="轉速">Spin</th><th data-tooltip="出手延伸距離">Ext</th>' +
        '<th class="num pa-event-cell" data-tooltip="打席結果">PA Event</th>' +
        (hasVideo ? '<th data-tooltip="逐球影片">Video</th>' : '') +
        '</tr></thead><tbody>';
    for (var i = 0; i < pitches.length; i++) {
        var p = pitches[i];
        var countStr = (p.pre_balls != null && p.pre_strikes != null)
            ? (p.pre_balls + '-' + p.pre_strikes)
            : '-';
        var cls = p.pa_event ? ' class="pitch-pa-final"' : '';
        var pt = _pitchTypeClass(p.pitch_type);
        var pn = p.pitch_name || p.pitch_type || '\u2014';
        h += '<tr' + cls + '>' +
            '<td class="num">' + (i+1) + '</td>' +
            '<td class="num">' + escapePitchLogHtml(countStr) + '</td>' +
            '<td class="num">' + escapePitchLogHtml(_fmt(p.inning)) + '</td>' +
            '<td><span class="pitch-tag pitch-' + pt + '">' + escapePitchLogHtml(pn) + '</span></td>' +
            '<td class="num">' + escapePitchLogHtml(_fmt(p.speed,1)) + '</td>' +
            '<td class="num">' + escapePitchLogHtml(_fmt(p.zone)) + '</td>' +
            '<td>' + escapePitchLogHtml(p.result || '\u2014') + '</td>' +
            '<td class="num">' + escapePitchLogHtml(_fmt(p.ev,1)) + '</td>' +
            '<td class="num">' + escapePitchLogHtml(_fmt(p.la,1)) + '</td>' +
            '<td class="num">' + escapePitchLogHtml(_fmt(p.ivb,1)) + '</td>' +
            '<td class="num">' + escapePitchLogHtml(_fmt(p.hb,1)) + '</td>' +
            '<td class="num">' + escapePitchLogHtml(_fmt(p.spin)) + '</td>' +
            '<td class="num">' + escapePitchLogHtml(_fmt(p.extension,2)) + '</td>' +
            '<td class="num pa-event-cell">' + (p.pa_event ? '<span class="pa-event-tag">' + escapePitchLogHtml(p.pa_event) + '</span>' : '') + '</td>' +
            (hasVideo ? _videoCell(p) : '') +
            '</tr>';
    }
    h += '</tbody></table>';
    return h;
}

// 取得或建立快取檔對應的項目物件
function _getPitchLogEntry(src) {
    if (!src) return null;
    if (!pitchLogCache[src]) pitchLogCache[src] = {};
    return pitchLogCache[src];
}

// fetch JSON、產生表格 HTML 並存入快取；已有快取或進行中的請求則直接回傳
function _loadPitchLogData(src) {
    var entry = _getPitchLogEntry(src);
    if (!entry) return Promise.resolve(null);
    if (entry.html) return Promise.resolve(entry);
    if (entry.promise) return entry.promise;

    entry.promise = fetch(src)
        .then(function(resp) {
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            return resp.json();
        })
        .then(function(pitches) {
            var pitchList = Array.isArray(pitches) ? pitches : [];
            entry.html = _buildPitchTable(pitchList);
            return entry;
        })
        .catch(function(err) {
            delete pitchLogCache[src];
            throw err;
        })
        .finally(function() {
            if (pitchLogCache[src]) delete pitchLogCache[src].promise;
        });

    return entry.promise;
}

// 將已載入的快取 HTML 插入容器，並觸發表格欄位對齊
function _renderPitchLog(container, entry) {
    container.innerHTML = entry && entry.html ? entry.html : _buildPitchTable([]);
    container.dataset.rendered = '1';
    if (typeof window.alignNumericTableColumns === 'function') {
        window.alignNumericTableColumns(container);
    }
}

// 預載單一比賽列的 pitch log（不插入 DOM，僅產生並快取表格 HTML）
function prefetchPitchLogRow(row) {
    if (!row || !row.dataset || !row.dataset.src) return Promise.resolve(null);
    return _loadPitchLogData(row.dataset.src).catch(function() {
        return null;
    });
}

// 取得目前年份/職業耳漈筛選後所有可見比賽列的 pitch-log-row
function _getFilteredPitchLogRows() {
    var yearSel = document.getElementById('gamelog-year-select');
    var yr = yearSel ? yearSel.value : '';
    var tbl = yr ? document.getElementById('gamelogs-' + yr) : null;
    var rows = [];
    if (!tbl) return rows;

    tbl.querySelectorAll('tbody tr.game-row-expandable').forEach(function(gameRow) {
        if (gameRow.offsetParent === null || gameRow.style.display === 'none') return;
        var detailRow = gameRow.nextElementSibling;
        if (!detailRow || !detailRow.classList.contains('pitch-log-row') || !detailRow.dataset.src) return;
        rows.push(detailRow);
    });

    return rows;
}

// 批次預載多個比賽列的 pitch log，限制同時進行中的請求數 (concurrency)
function prefetchPitchLogRows(rows, concurrency) {
    var queue = (rows || []).filter(function(row) {
        if (!row || !row.dataset || !row.dataset.src) return false;
        var entry = pitchLogCache[row.dataset.src];
        return !entry || (!entry.html && !entry.promise);
    });
    var maxConcurrent = Math.max(1, concurrency || 6);
    var index = 0;

    if (!queue.length) return Promise.resolve([]);

    function worker() {
        if (index >= queue.length) return Promise.resolve();
        var row = queue[index++];
        return prefetchPitchLogRow(row).then(worker);
    }

    var workers = [];
    var workerCount = Math.min(maxConcurrent, queue.length);
    for (var i = 0; i < workerCount; i++) {
        workers.push(worker());
    }

    return Promise.all(workers);
}

// 預載目前頁面筛選結果中所有可見比賽列的 pitch log（最多 6 個並行）
function prefetchFilteredPitchLogs() {
    return prefetchPitchLogRows(_getFilteredPitchLogRows(), 6);
}

// 展開/收合比賽列的 pitch log 區域；首次展開時做懶性渲染
function togglePitchLog(id) {
    var row = document.getElementById(id);
    if (!row) return;
    var open = row.style.display !== 'none';
    row.style.display = open ? 'none' : '';
    var arrow = document.getElementById('arrow-' + id);
    if (arrow) arrow.style.transform = open ? '' : 'rotate(90deg)';
    // Lazy-render: build table on first open
    if (!open) {
        var container = document.getElementById(id.replace('pitchlog-', 'pitchlog-content-'));
        if (container && !container.dataset.rendered) {
            var src = row.dataset.src;
            if (src && !container.dataset.loading) {
                var cached = pitchLogCache[src];
                if (cached && cached.html) {
                    _renderPitchLog(container, cached);
                    return;
                }
                container.dataset.loading = '1';
                container.innerHTML = '<div class="pitch-log-loading">載入逐球資料中...</div>';
                _loadPitchLogData(src)
                    .then(function(entry) {
                        _renderPitchLog(container, entry);
                    })
                    .catch(function() {
                        container.innerHTML = '<div class="pitch-log-loading">逐球資料載入失敗</div>';
                    })
                    .finally(function() {
                        delete container.dataset.loading;
                    });
            }
        }
    }
}

/* ── 逐球影片 ──
 * Data-layer gating: only MLB game JSON includes play_id/video.
 * Video availability can come from StatsAPI or Baseball Savant, but both
 * render with the Baseball Savant button treatment.
 */
var SAVANT_VIDEO_URL = 'https://baseballsavant.mlb.com/sporty-videos?playId=';
var SAVANT_MP4_RE = /https:\/\/sporty-clips\.mlb\.com\/[^"'<>\\]+?\.mp4/;
var savantVideoCache = Object.create(null);

function _videoCell(p) {
    if (p.video) {
        return '<td class="num"><button type="button" class="pitch-video-btn pitch-video-btn--savant"' +
            ' data-video="' + escapePitchLogHtml(p.video) + '"' +
            ' onclick="openPitchVideo(event, this)" title="播放逐球影片">▶</button></td>';
    }
    if (p.play_id) {
        return '<td class="num"><button type="button" class="pitch-video-btn pitch-video-btn--savant"' +
            ' data-play-id="' + escapePitchLogHtml(p.play_id) + '"' +
            ' onclick="openPitchVideo(event, this)" title="播放逐球影片">▶</button></td>';
    }
    return '<td class="num">-</td>';
}

function closePitchVideo() {
    var overlay = document.getElementById('pitch-video-overlay');
    if (overlay) overlay.remove();
}

function _decodeHtml(text) {
    var textarea = document.createElement('textarea');
    textarea.innerHTML = text || '';
    return textarea.value.replace(/\\\//g, '/');
}

function _extractSavantMp4(html) {
    var match = SAVANT_MP4_RE.exec(_decodeHtml(html));
    return match ? match[0] : '';
}

function _resolveSavantVideo(playId) {
    if (!playId) return Promise.resolve('');
    if (savantVideoCache[playId]) return savantVideoCache[playId];

    savantVideoCache[playId] = fetch(SAVANT_VIDEO_URL + encodeURIComponent(playId))
        .then(function(resp) {
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            return resp.text();
        })
        .then(function(html) {
            var mp4 = _extractSavantMp4(html);
            if (!mp4) throw new Error('No video found');
            return mp4;
        })
        .catch(function(err) {
            delete savantVideoCache[playId];
            throw err;
        });

    return savantVideoCache[playId];
}

function _renderPitchVideoBody(box, mp4) {
    var closeButton = document.createElement('button');
    closeButton.type = 'button';
    closeButton.className = 'pitch-video-close';
    closeButton.setAttribute('aria-label', '關閉');
    closeButton.textContent = '×';
    closeButton.addEventListener('click', closePitchVideo);

    var video = document.createElement('video');
    video.controls = true;
    video.autoplay = true;
    video.playsInline = true;
    video.src = String(mp4 || '');
    box.replaceChildren(closeButton, video);
}

function _renderPitchVideoMessage(box, text) {
    var closeButton = document.createElement('button');
    closeButton.type = 'button';
    closeButton.className = 'pitch-video-close';
    closeButton.setAttribute('aria-label', '關閉');
    closeButton.textContent = '×';
    closeButton.addEventListener('click', closePitchVideo);

    var message = document.createElement('div');
    message.className = 'pitch-video-message';
    message.textContent = String(text == null ? '' : text);
    box.replaceChildren(closeButton, message);
}

function openPitchVideo(evt, btn) {
    evt.stopPropagation();
    closePitchVideo();

    var mp4 = btn.dataset.video;
    var playId = btn.dataset.playId;
    var overlay = document.createElement('div');
    overlay.id = 'pitch-video-overlay';
    overlay.className = 'pitch-video-overlay';

    overlay.innerHTML = '<div class="pitch-video-box"></div>';
    overlay.addEventListener('click', function (e) {
        if (e.target === overlay) closePitchVideo();
    });
    document.body.appendChild(overlay);

    var box = overlay.querySelector('.pitch-video-box');
    if (mp4) {
        _renderPitchVideoBody(box, mp4);
        return;
    }

    _renderPitchVideoMessage(box, '載入影片中...');
    _resolveSavantVideo(playId)
        .then(function(resolvedMp4) {
            _renderPitchVideoBody(box, resolvedMp4);
        })
        .catch(function() {
            _renderPitchVideoMessage(box, '此球目前沒有可播放影片');
        });
}
