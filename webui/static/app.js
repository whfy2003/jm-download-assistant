/* JM 下载助手 —— 前端逻辑 */
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const PATHS = window.JM_PATHS || { pdf: '', fav: '', defaults: {} };
  const APPMETA = window.JM_APP || { version: '', projectUrl: '', releasesUrl: '' };

  const STAR_OUT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><path d="M12 3.5l2.6 5.3 5.9.9-4.2 4.1 1 5.8-5.3-2.8-5.3 2.8 1-5.8-4.2-4.1 5.9-.9z"/></svg>';
  const STAR_ON = '<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><path d="M12 3.5l2.6 5.3 5.9.9-4.2 4.1 1 5.8-5.3-2.8-5.3 2.8 1-5.8-4.2-4.1 5.9-.9z"/></svg>';
  const TRASH = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13M10 11v6M14 11v6"/></svg>';

  const POLL_MS = 1000;
  const THEME_KEY = 'jm-theme';
  const VIEWS = ['download', 'favorites', 'settings'];

  const state = {
    view: 'download',
    dl: { q: '', scope: 'all' },
    fav: { q: '', scope: 'all' },
  };

  let toastTimer = null;
  let lastFinishedAt = '';
  let lastLoggedCount = -1;
  let diskData = null;

  /* ---------------- 工具 ---------------- */
  function toast(message, isError) {
    const el = $('toast');
    el.textContent = message;
    el.classList.toggle('error', !!isError);
    el.classList.remove('hidden');
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.add('hidden'), 4200);
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  async function postJson(url, body) {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    });
    try { return await res.json(); } catch (e) { return { ok: false, error: '服务返回异常' }; }
  }

  function fmtSize(bytes) {
    if (bytes === null || bytes === undefined || isNaN(bytes)) return '—';
    const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
    let v = Number(bytes), i = 0;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
    return (i === 0 ? Math.round(v) : v.toFixed(v < 10 ? 2 : 1)) + ' ' + units[i];
  }

  /* ---------------- 主题 ---------------- */
  const ICON_MOON = '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>';
  const ICON_SUN = '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>';

  function syncThemeIcon() {
    const dark = document.documentElement.getAttribute('data-theme') === 'dark';
    const ico = $('theme-ico');
    if (ico) ico.innerHTML = dark ? ICON_SUN : ICON_MOON;
  }

  function toggleTheme() {
    const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem(THEME_KEY, next); } catch (e) { }
    syncThemeIcon();
  }

  /* ---------------- 磁盘占用 ---------------- */
  function paintBar(bar, info) {
    if (!bar || !info) return;
    const total = info.total || 1;
    const segs = bar.querySelectorAll('.seg');
    if (segs.length < 3) return;
    segs[0].style.width = ((info.dir_size || 0) / total * 100) + '%';
    segs[1].style.width = ((info.other_used || 0) / total * 100) + '%';
    segs[2].style.width = ((info.free || 0) / total * 100) + '%';
  }

  function paintSidebarBars() {
    if (!diskData) return;
    [['disk-pdf', 'pdf'], ['disk-fav', 'fav']].forEach(function (pair) {
      const el = $(pair[0]);
      if (el && diskData[pair[1]]) paintBar(el, diskData[pair[1]]);
    });
  }

  async function loadDisk(force) {
    try {
      const res = await fetch('/api/disk' + (force ? '?force=1' : ''), { cache: 'no-store' });
      const data = await res.json();
      diskData = data.disk || null;
      paintSidebarBars();
      renderDiskDetail();
    } catch (e) { /* 静默 */ }
  }

  function renderDiskDetail() {
    const box = $('disk-detail');
    if (!box) return;

    if (!diskData) {
      box.innerHTML = '<div class="empty">统计中…</div>';
      return;
    }

    const items = [['pdf', '下载目录'], ['fav', '收藏目录']];
    let html = '';

    items.forEach(function (pair) {
      const info = diskData[pair[0]] || {};
      html += '<div class="disk-item">' +
        '<div class="disk-item-head"><b>' + pair[1] + '</b><span>' + fmtSize(info.dir_size) + '</span></div>' +
        '<div class="disk-item-path">' + escapeHtml(info.path || '') + '</div>' +
        '<div class="disk-bar big" data-key="' + pair[0] + '">' +
        '<span class="seg seg-dir"></span><span class="seg seg-other"></span><span class="seg seg-free"></span>' +
        '</div></div>';
    });

    const info0 = diskData.pdf || diskData.fav || {};
    html += '<div class="disk-total">' +
      '<div class="disk-total-row"><span>所在磁盘</span><b>' + escapeHtml(info0.drive || '—') + '</b></div>' +
      '<div class="disk-total-row"><span>总容量</span><b>' + fmtSize(info0.total) + '</b></div>' +
      '<div class="disk-total-row"><span>已用</span><b>' + fmtSize(info0.used) + '</b></div>' +
      '<div class="disk-total-row"><span>可用</span><b>' + fmtSize(info0.free) + '</b></div>' +
      '</div>';

    box.innerHTML = html;

    box.querySelectorAll('.disk-bar.big').forEach(function (bar) {
      const key = bar.getAttribute('data-key');
      if (diskData[key]) paintBar(bar, diskData[key]);
    });

    const drive = $('disk-drive');
    if (drive) drive.textContent = info0.drive || '—';
  }

  function showDiskPop(barId, key, label) {
    const bar = $(barId);
    const info = diskData && diskData[key];
    if (!bar || !info) return;

    const pop = $('disk-pop');
    const rect = bar.getBoundingClientRect();
    const width = Math.max(520, Math.round(rect.width * 2));   // 不少于两倍侧栏宽度

    pop.classList.remove('hidden');
    pop.style.width = width + 'px';
    const popH = pop.offsetHeight || 78;

    let left = rect.left;
    if (left + width > window.innerWidth - 12) {
      left = Math.max(12, window.innerWidth - width - 12);
    }
    pop.style.left = left + 'px';

    const top = rect.top - popH - 10;
    pop.style.top = (top < 8 ? rect.bottom + 10 : top) + 'px';

    paintBar(pop.querySelector('.disk-bar-fill'), info);
    $('disk-pop-title').textContent = label + (info.drive ? ' · ' + info.drive : '');
    $('disk-pop-nums').textContent =
      '占用 ' + fmtSize(info.dir_size) +
      ' · 其它 ' + fmtSize(info.other_used) +
      ' · 可用 ' + fmtSize(info.free) +
      ' / 共 ' + fmtSize(info.total);
  }

  function bindDiskHover(barId, key, label) {
    const bar = $(barId);
    if (!bar) return;

    bar.addEventListener('mouseenter', function () { showDiskPop(barId, key, label); });
    bar.addEventListener('mouseleave', function () { $('disk-pop').classList.add('hidden'); });
  }

  /* ---------------- 路径显示 ---------------- */
  function updatePaths() {
    const set = function (id, text) {
      const el = $(id);
      if (el) el.textContent = text;
    };
    set('sb-pdf-path', PATHS.pdf);
    set('sb-fav-path', PATHS.fav);
    set('head-pdf-dir', PATHS.pdf);
    set('head-fav-dir', PATHS.fav);
    set('fav-dir-text', PATHS.fav);
    set('fav-log-text', PATHS.fav + '\\jm_fav_log.txt');
    set('crumb-path', state.view === 'favorites' ? PATHS.fav
      : state.view === 'settings' ? '设置' : PATHS.pdf);
  }

  /* ---------------- 记录渲染 ---------------- */
  function recordHtml(r, scope) {
    const starred = scope === 'fav' ? true : !!r.fav;
    const isId = /^\d+$/.test(r.id);
    const missing = r.exists ? '' : '<span class="badge badge-warn">文件缺失</span>';

    return '<article class="record" data-file="' + escapeHtml(r.file) + '" data-id="' + escapeHtml(r.id) + '" data-dir="' + escapeHtml(r.dir || '') + '">' +
      '<button class="icon-btn star ' + (starred ? 'on' : '') + '" title="' +
      (starred ? '取消收藏' : '收藏到 ' + escapeHtml(PATHS.fav)) + '">' + (starred ? STAR_ON : STAR_OUT) + '</button>' +
      '<div class="record-main" title="点击用系统默认程序打开">' +
      '<div class="record-id' + (isId ? '' : ' muted') + '">' + escapeHtml(r.id) + '</div>' +
      '<div class="record-name">' + escapeHtml(r.name) + '</div>' +
      '<div class="record-time">' + escapeHtml(r.time) + '</div>' +
      (missing ? '<div class="record-meta">' + missing + '</div>' : '') +
      '</div>' +
      '<button class="icon-btn trash" title="删除文件并抹去记录">' + TRASH + '</button>' +
      '</article>';
  }

  function renderInto(listEl, countEl, badgeEl, records, scope) {
    badgeEl.textContent = state[scope === 'fav' ? 'fav' : 'dl'].scope === 'recent' ? '最近 500 条' : '全部记录';

    if (!records.length) {
      listEl.innerHTML = '<div class="empty">没有匹配的记录</div>';
      countEl.textContent = '共 0 条记录';
      return;
    }
    listEl.innerHTML = records.map(function (r) { return recordHtml(r, scope); }).join('');
    countEl.textContent = '共 ' + records.length + ' 条记录';
  }

  /* ---------------- 数据加载 ---------------- */
  async function loadRecords() {
    const st = state.dl;
    const params = new URLSearchParams({ scope: st.scope });
    if (st.q) params.set('q', st.q);

    try {
      const res = await fetch('/api/records?' + params.toString(), { cache: 'no-store' });
      const data = await res.json();
      renderInto($('dl-records'), $('dl-count'), $('dl-badge'), data.records || [], 'dl');
    } catch (e) {
      $('dl-records').innerHTML = '<div class="empty">读取记录失败：' + escapeHtml(e.message) + '</div>';
    }
  }

  async function loadFavorites() {
    const st = state.fav;
    const params = new URLSearchParams({ scope: st.scope });
    if (st.q) params.set('q', st.q);

    try {
      const res = await fetch('/api/favorites?' + params.toString(), { cache: 'no-store' });
      const data = await res.json();
      renderInto($('fav-records'), $('fav-count'), $('fav-badge'), data.records || [], 'fav');

      const banner = $('fav-warning');
      if (data.warning) {
        banner.textContent = data.warning;
        banner.classList.remove('hidden');
      } else {
        banner.classList.add('hidden');
      }
    } catch (e) {
      $('fav-records').innerHTML = '<div class="empty">读取记录失败：' + escapeHtml(e.message) + '</div>';
    }
  }

  function refreshCurrent() {
    if (state.view === 'favorites') loadFavorites();
    else if (state.view === 'download') loadRecords();
  }

  /* ---------------- 记录操作 ---------------- */
  async function openRecordFile(file, scope, dir) {
    const data = await postJson('/api/open-file', { file: file, scope: scope, dir: dir || '' });
    if (!data.ok) toast(data.error || '打开失败', true);
  }

  async function deleteRecord(file, jmId, scope) {
    const where = scope === 'fav' ? '收藏夹' : '下载目录';
    const okConfirm = confirm(
      '确定删除这个文件吗？\n\n' + file +
      '\n\n· 文件将从「' + where + '」中删除' +
      '\n· 对应的日志记录也会被抹去' +
      '\n\n此操作不可撤销。');
    if (!okConfirm) return;

    const data = await postJson('/api/delete', { file: file, id: jmId, scope: scope });
    if (!data.ok) { toast(data.error || '删除失败', true); return; }

    toast('已删除' + (data.file_removed ? '文件' : '记录') + '（日志清理 ' + data.lines_removed + ' 行）');
    if (scope === 'fav') loadFavorites();
    loadRecords();
    loadDisk(true);
  }

  async function toggleFavorite(file, jmId, starred) {
    if (starred) {
      const okConfirm = confirm(
        '取消收藏？\n\n' + file +
        '\n\n· 只从收藏列表移除' +
        '\n· 下载目录里的 PDF 不受影响' +
        '\n· 旧版本复制到收藏目录里的副本不会被删除');
      if (!okConfirm) return;

      const data = await postJson('/api/delete', { file: file, id: jmId, scope: 'fav' });
      if (!data.ok) { toast(data.error || '取消收藏失败', true); return; }
      toast('已取消收藏');
    } else {
      const data = await postJson('/api/favorite', { file: file, id: jmId });
      if (!data.ok) { toast(data.error || '收藏失败', true); return; }
      toast(data.already ? '该文件已在收藏中' : '已收藏（仅记录文件名，不复制文件）');
    }

    loadRecords();
    if (state.view === 'favorites') loadFavorites();
    loadDisk(true);
  }

  /* ---------------- 清除所有下载数据 ---------------- */
  async function wipeAll() {
    const first = confirm(
      '清除所有下载数据\n\n' +
      '将会删除：\n' +
      '· 下载目录里的全部漫画 PDF\n' +
      '· 下载记录 jm_log.txt\n' +
      '· 收藏记录（收藏目录里的 jm_fav_log.txt）\n' +
      '· 图片工作区里的临时文件\n\n' +
      '⚠ 删除后无法找回，也不会进回收站。\n\n确定继续吗？');
    if (!first) return;

    const second = confirm('再次确认\n\n确定删除所有已下载的内容吗？\n这一步执行完就再也恢复不了了。');
    if (!second) return;

    const data = await postJson('/api/wipe', {});
    if (!data.ok) { toast(data.error || '清除失败', true); return; }

    const files = (data.pdf_files || 0) + (data.fav_files || 0);
    toast('已清除：PDF ' + files + ' 个、日志 ' + (data.logs || 0) + ' 个');

    $('album-id').value = '';
    renderAlbumHit(null);
    loadRecords();
    loadFavorites();
    loadDisk(true);
  }

  function handleListClick(listEl, event) {
    const record = event.target.closest('.record');
    if (!record) return;

    const file = record.getAttribute('data-file');
    const jmId = record.getAttribute('data-id');
    const scope = listEl.getAttribute('data-scope') || 'dl';

    const dir = record.getAttribute('data-dir') || '';

    if (event.target.closest('.star')) {
      const starred = event.target.closest('.star').classList.contains('on');
      toggleFavorite(file, jmId, starred);
    } else if (event.target.closest('.trash')) {
      deleteRecord(file, jmId, scope);
    } else if (event.target.closest('.record-main')) {
      openRecordFile(file, scope, dir);
    }
  }

  /* ---------------- 运行状态 ---------------- */
  function renderProgress(s) {
    const box = $('progress-box');
    if (!box) return;

    const p = s.progress || {};
    let phase = p.phase || 'idle';
    if (!s.running) {
      if (s.ok === true) phase = 'done';
      else if (s.ok === false) phase = 'error';
      else phase = 'idle';
    }

    const total = Number(p.total) || 0;
    const done = Number(p.done) || 0;
    const pct = phase === 'done' ? 100 : Math.max(0, Math.min(100, Number(p.percent) || 0));

    const head = $('progress-phase');
    if (phase === 'meta') head.textContent = p.note || '正在获取本子信息…';
    else if (phase === 'download') head.textContent = '正在下载' + (p.title ? ' · ' + p.title : '');
    else if (phase === 'pdf') head.textContent = p.note || '正在合并为 PDF…';
    else if (phase === 'done') head.textContent = '已完成';
    else if (phase === 'error') head.textContent = p.note || '下载中断';
    else head.textContent = '准备就绪';

    $('progress-pct').textContent = phase === 'meta' ? '…' : pct + '%';

    if (phase === 'meta') {
      $('progress-fill').style.width = '35%';
    } else {
      $('progress-fill').style.width = pct + '%';
    }

    const countEl = $('progress-count');
    if (phase === 'idle') countEl.textContent = '0 / 0 张';
    else if (total > 0) countEl.textContent = done + ' / ' + total + ' 张';
    else countEl.textContent = done + ' 张已处理';

    let chapter = '';
    if (p.photo_index && p.photo_total) chapter = '第 ' + p.photo_index + '/' + p.photo_total + ' 章';
    if (p.current) chapter += (chapter ? ' · ' : '') + p.current;
    $('progress-chapter').textContent =
      (phase === 'download' || phase === 'pdf') ? chapter : '';

    box.className = 'progress-box' +
      (phase === 'meta' ? ' is-meta' : '') +
      (phase === 'pdf' ? ' is-pdf' : '') +
      (phase === 'done' ? ' is-done' : '') +
      (phase === 'error' ? ' is-error' : '');
  }

  function applyState(s) {
    const running = !!s.running;
    const elStatusText = $('status-text');

    renderProgress(s);
    $('spinner').classList.toggle('hidden', !running);

    if (running) {
      elStatusText.textContent = '程序运行中';
      elStatusText.className = 'badge';
    } else if (s.ok === false) {
      elStatusText.textContent = '上次任务失败';
      elStatusText.className = 'badge badge-danger';
    } else if (hitRecord) {
      elStatusText.textContent = '已下载';
      elStatusText.className = 'badge badge-success';
    } else if (s.ok === true) {
      elStatusText.textContent = '已完成';
      elStatusText.className = 'badge badge-success';
    } else {
      elStatusText.textContent = '空闲';
      elStatusText.className = 'badge';
    }

    $('btn-download').disabled = running;
    $('album-id').disabled = running;

    if (s.logs && s.logs.length !== lastLoggedCount) {
      lastLoggedCount = s.logs.length;
      const el = $('runtime-logs');
      el.textContent = s.logs.slice(-60).join('\n') || '（暂无）';
      el.scrollTop = el.scrollHeight;
    }

    if (!running && s.finished_at && s.finished_at !== lastFinishedAt) {
      lastFinishedAt = s.finished_at;
      if (s.ok === true) {
        toast('下载完成：' + (s.title || s.album_id));
        // 刚下完这一本就不再显示「已下载」卡片，改显示「已完成 + 标题」
        if (hitRecord && hitRecord.id === s.album_id) { renderAlbumHit(null); }
        loadRecords();
        loadDisk(true);
      } else if (s.ok === false) {
        toast('下载失败：' + (s.message || '未知错误'), true);
      }
    }
  }

  async function pollState() {
    try {
      const res = await fetch('/api/state', { cache: 'no-store' });
      applyState(await res.json());
    } catch (e) {
      const elStatusText = $('status-text');
      elStatusText.textContent = '服务未连接';
      elStatusText.className = 'badge badge-danger';
    }
  }

  /* ---------------- 已下载识别 ---------------- */
  let lookupTimer = null;
  let lastLookupId = '';
  let hitRecord = null;

  function scheduleLookup(rawId) {
    const id = (rawId || '').trim();
    if (lookupTimer) clearTimeout(lookupTimer);

    if (!id || !/^\d+$/.test(id)) {
      renderAlbumHit(null);
      return;
    }
    lookupTimer = setTimeout(function () { lookupAlbum(id); }, 380);
  }

  async function lookupAlbum(id) {
    try {
      const res = await fetch('/api/lookup?id=' + encodeURIComponent(id), { cache: 'no-store' });
      const data = await res.json();
      if (!data.ok) { return; }
      // 请求返回前用户可能已经改了输入
      if ($('album-id').value.trim() !== id) { return; }
      lastLookupId = id;
      renderAlbumHit(data.found ? data.record : null);
    } catch (e) { /* 静默 */ }
  }

  function renderAlbumHit(record) {
    const box = $('album-hit');
    hitRecord = record || null;

    if (!record) {
      box.classList.add('hidden');
      if (!state.running) { setStatusBadge('空闲', 'badge'); }
      return;
    }

    $('album-hit-id').textContent = record.id || '—';
    $('album-hit-name').textContent = record.name || record.file;
    $('album-hit-time').textContent = record.time ? '下载于 ' + record.time : '';

    const img = $('album-hit-cover');
    const fallback = $('album-hit-cover-fallback');
    img.classList.add('hidden');
    fallback.classList.remove('hidden');
    img.onload = function () {
      img.classList.remove('hidden');
      fallback.classList.add('hidden');
    };
    img.onerror = function () {
      img.classList.add('hidden');
      fallback.classList.remove('hidden');
    };
    img.src = '/api/cover?file=' + encodeURIComponent(record.file);

    box.classList.remove('hidden');
    if (!state.running) { setStatusBadge('已下载', 'badge badge-success'); }
  }

  function setStatusBadge(text, className) {
    const el = $('status-text');
    if (!el) return;
    el.textContent = text;
    el.className = className;
  }

  /* ---------------- 下载动作 ---------------- */
  async function doDownload(force) {
    const el = $('album-id');
    const id = el.value.trim();
    if (!id) { toast('请输入本子编号', true); el.focus(); return; }
    if (!/^\d+$/.test(id)) { toast('编号必须是纯数字', true); el.focus(); return; }

    $('btn-download').disabled = true;
    const data = await postJson('/api/download', { id: id, force: !!force });

    if (!data.ok) {
      if (data.need_confirm && data.record) {
        renderAlbumHit(data.record);
        $('btn-download').disabled = false;
        const ok = confirm(
          '该本子已经下载过：\n\n' + (data.record.name || data.record.file) +
          '\n\n重新下载会覆盖同名 PDF，确定吗？');
        if (ok) { doDownload(true); }
        return;
      }
      toast(data.error || '启动下载失败', true);
      $('btn-download').disabled = false;
      return;
    }

    toast('已开始下载 ' + id);
    lastLoggedCount = -1;
    renderAlbumHit(null);
    setTimeout(pollState, 400);
  }

  function bindAlbumHit() {
    $('album-id').addEventListener('input', function (e) {
      scheduleLookup(e.target.value);
    });

    $('btn-open-album').addEventListener('click', function () {
      if (!hitRecord) return;
      openRecordFile(hitRecord.file, 'dl');
    });

    $('btn-redownload').addEventListener('click', function () {
      if (!hitRecord) return;
      if (confirm('重新下载会覆盖同名 PDF，确定吗？')) { doDownload(true); }
    });
  }

  /* ---------------- 设置 ---------------- */
  function paintAvsState(avs) {
    const badge = $('avs-state');
    if (!badge) return;
    if (avs) {
      badge.textContent = '已配置';
      badge.className = 'badge badge-success';
    } else {
      badge.textContent = '未配置';
      badge.className = 'badge';
    }
  }

  async function loadSettings() {
    try {
      const res = await fetch('/api/settings', { cache: 'no-store' });
      const data = await res.json();
      $('set-pdf').value = data.pdf_dir || '';
      $('set-fav').value = data.fav_dir || '';
      $('set-avs').value = data.avs || '';
      paintAvsState(data.avs);
      if (data.disk) {
        diskData = data.disk;
        paintSidebarBars();
        renderDiskDetail();
      }
    } catch (e) {
      toast('读取设置失败：' + e.message, true);
    }
  }

  async function saveAvs() {
    const input = $('set-avs');
    const avs = input.value.trim();
    if (!avs) { toast('请先粘贴 AVS 值，或点「清空」', true); input.focus(); return; }

    const data = await postJson('/api/settings', { avs: avs });
    if (!data.ok) { toast(data.error || '保存失败', true); return; }

    input.value = data.avs || '';
    paintAvsState(data.avs);
    toast(data.avs ? 'AVS 已保存，下次下载会带上登录凭证' : 'AVS 已清空');
  }

  async function clearAvs() {
    if (!confirm('清空 AVS？\n\n之后只能下载公开内容，已下载的文件不受影响。')) return;

    const data = await postJson('/api/settings', { avs: '' });
    if (!data.ok) { toast(data.error || '清空失败', true); return; }

    $('set-avs').value = '';
    paintAvsState('');
    toast('AVS 已清空');
  }

  /* ---------------- 关于与更新 ---------------- */
  async function openUrl(url) {
    if (!url) return;
    const data = await postJson('/api/open-url', { url: url });
    if (!data.ok) toast(data.error || '打开链接失败', true);
  }

  function fmtDate(text) {
    if (!text) return '';
    try {
      const d = new Date(text);
      if (isNaN(d.getTime())) return text;
      const pad = (n) => (n < 10 ? '0' + n : '' + n);
      return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
    } catch (e) { return text; }
  }

  function renderUpdate(data) {
    const box = $('update-result');
    box.classList.remove('hidden');

    const current = escapeHtml(data.current || APPMETA.version || '');
    const latest = escapeHtml(data.latest || '');

    if (data.has_update) {
      const assets = data.assets || [];
      const exe = assets.find((a) => /\.exe$/i.test(a.name));
      const zip = assets.find((a) => /\.zip$/i.test(a.name));

      let actions = '<div class="update-actions">' +
        '<button class="btn btn-primary btn-sm" data-url="' +
        escapeHtml(data.url || APPMETA.releasesUrl) + '">前往发布页</button>' +
        '<button class="btn btn-outline btn-sm" data-url="' +
        escapeHtml(APPMETA.projectUrl) + '">项目主页</button>';
      if (exe && exe.url) {
        actions += '<button class="btn btn-outline btn-sm" data-url="' +
          escapeHtml(exe.url) + '">下载安装程序</button>';
      }
      if (zip && zip.url) {
        actions += '<button class="btn btn-outline btn-sm" data-url="' +
          escapeHtml(zip.url) + '">下载绿色版</button>';
      }
      actions += '</div>';

      box.className = 'update-result is-new';
      box.innerHTML =
        '<div>发现新版本：<b>' + latest + '</b>（当前 <b>v' + current + '</b>）</div>' +
        (data.latest_name ? '<div>名称：' + escapeHtml(data.latest_name) + '</div>' : '') +
        (data.published_at ? '<div>发布时间：' + escapeHtml(fmtDate(data.published_at)) + '</div>' : '') +
        (data.notes ? '<div class="update-notes">' + escapeHtml(data.notes) + '</div>' : '') +
        '<div style="margin-top:8px">下载新版安装程序后直接运行即可，安装向导会只替换程序文件，' +
        '<b>漫画与设置全部保留</b>。</div>' +
        actions;
    } else {
      box.className = 'update-result is-ok';
      box.innerHTML =
        '<div>已是最新版本：<b>v' + current + '</b></div>' +
        (latest ? '<div>GitHub 上最新版：' + latest + '</div>' : '') +
        '<div class="update-actions">' +
        '<button class="btn btn-outline btn-sm" data-url="' +
        escapeHtml(APPMETA.projectUrl) + '">项目主页</button></div>';
    }
  }

  async function checkUpdate() {
    const btn = $('btn-check-update');
    const box = $('update-result');
    const oldText = btn.textContent;

    btn.disabled = true;
    btn.textContent = '检查中…';
    box.classList.remove('hidden');
    box.className = 'update-result';
    box.innerHTML = '正在读取 GitHub 上的最新版本…';

    try {
      const res = await fetch('/api/check-update', { cache: 'no-store' });
      const data = await res.json();
      if (!data.ok) {
        box.className = 'update-result is-err';
        box.innerHTML = escapeHtml(data.error || '检查更新失败') +
          '<div class="update-actions">' +
          '<button class="btn btn-outline btn-sm" data-url="' +
          escapeHtml(APPMETA.projectUrl) + '">打开项目主页</button></div>';
        return;
      }
      renderUpdate(data);
    } catch (e) {
      box.className = 'update-result is-err';
      box.innerHTML = '检查更新失败：' + escapeHtml(e.message);
    } finally {
      btn.disabled = false;
      btn.textContent = oldText;
    }
  }

  async function saveSettings() {
    const pdf = $('set-pdf').value.trim();
    const fav = $('set-fav').value.trim();

    if (!pdf || !fav) { toast('两个目录都不能为空', true); return; }
    if (!/^[A-Za-z]:[\\/]/.test(pdf) || !/^[A-Za-z]:[\\/]/.test(fav)) {
      toast('请填写绝对路径，例如 E:\\漫画\\JM', true);
      return;
    }

    const okConfirm = confirm(
      '确定保存并迁移吗？\n\n' +
      '下载目录 → ' + pdf + '\n' +
      '收藏目录 → ' + fav + '\n\n' +
      '原目录里的所有文件与子文件夹都会被移动到新位置，' +
      '过程中请不要关闭页面。');
    if (!okConfirm) return;

    const btn = $('btn-save-settings');
    const oldText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '正在迁移…';

    try {
      const data = await postJson('/api/settings', { pdf_dir: pdf, fav_dir: fav });
      if (!data.ok) { toast(data.error || '保存失败', true); return; }

      PATHS.pdf = data.pdf_dir;
      PATHS.fav = data.fav_dir;
      diskData = data.disk || null;
      updatePaths();
      paintSidebarBars();
      renderDiskDetail();

      const parts = [];
      Object.keys(data.moves || {}).forEach(function (k) {
        const m = data.moves[k];
        parts.push((k === 'pdf' ? '下载目录' : '收藏目录') +
          ' 移动 ' + m.moved + ' 项' + (m.skipped ? '，跳过 ' + m.skipped : ''));
      });
      toast(parts.length ? '已保存：' + parts.join('；') : '已保存（路径未变化）');

      loadRecords();
      if (state.view === 'favorites') loadFavorites();
    } finally {
      btn.disabled = false;
      btn.textContent = oldText;
    }
  }

  function resetSettings() {
    const d = PATHS.defaults || {};
    $('set-pdf').value = d.pdf || '';
    $('set-fav').value = d.fav || '';
    toast('已填入默认路径，需点「保存并迁移内容」才会生效');
  }

  /* ---------------- 视图切换 ---------------- */
  function switchView(view) {
    state.view = view;

    document.querySelectorAll('.nav-item').forEach(function (n) {
      n.classList.toggle('active', n.getAttribute('data-view') === view);
    });
    VIEWS.forEach(function (v) {
      const el = $('view-' + v);
      if (el) el.classList.toggle('hidden', v !== view);
    });
    updatePaths();

    if (view === 'settings') {
      loadSettings();
      loadDisk(true);
    } else {
      refreshCurrent();
    }
  }

  /* ---------------- 事件绑定 ---------------- */
  $('dl-records').setAttribute('data-scope', 'dl');
  $('fav-records').setAttribute('data-scope', 'fav');
  $('dl-records').addEventListener('click', function (e) { handleListClick($('dl-records'), e); });
  $('fav-records').addEventListener('click', function (e) { handleListClick($('fav-records'), e); });

  document.querySelectorAll('.nav-item').forEach(function (n) {
    n.addEventListener('click', function () { switchView(n.getAttribute('data-view')); });
  });

  $('btn-download').addEventListener('click', doDownload);
  $('album-id').addEventListener('keydown', function (e) { if (e.key === 'Enter') doDownload(); });

  $('dl-btn-search').addEventListener('click', function () {
    state.dl.q = $('dl-search-id').value.trim(); state.dl.scope = 'recent'; loadRecords();
  });
  $('dl-btn-search-all').addEventListener('click', function () {
    state.dl.q = $('dl-search-id').value.trim(); state.dl.scope = 'all'; loadRecords();
  });
  $('dl-btn-show-all').addEventListener('click', function () {
    state.dl.q = ''; state.dl.scope = 'all'; $('dl-search-id').value = ''; loadRecords();
  });
  $('dl-search-id').addEventListener('keydown', function (e) { if (e.key === 'Enter') $('dl-btn-search').click(); });
  $('dl-refresh').addEventListener('click', function () { loadRecords(); loadDisk(true); toast('已刷新下载记录'); });

  $('fav-btn-search').addEventListener('click', function () {
    state.fav.q = $('fav-search-id').value.trim(); state.fav.scope = 'recent'; loadFavorites();
  });
  $('fav-btn-search-all').addEventListener('click', function () {
    state.fav.q = $('fav-search-id').value.trim(); state.fav.scope = 'all'; loadFavorites();
  });
  $('fav-btn-show-all').addEventListener('click', function () {
    state.fav.q = ''; state.fav.scope = 'all'; $('fav-search-id').value = ''; loadFavorites();
  });
  $('fav-search-id').addEventListener('keydown', function (e) { if (e.key === 'Enter') $('fav-btn-search').click(); });
  $('fav-refresh').addEventListener('click', function () { loadFavorites(); loadDisk(true); toast('已刷新收藏记录'); });

  $('btn-wipe').addEventListener('click', wipeAll);
  $('btn-save-settings').addEventListener('click', saveSettings);
  $('btn-reset-settings').addEventListener('click', resetSettings);
  $('btn-disk-refresh').addEventListener('click', function () { loadDisk(true); toast('已重新统计磁盘占用'); });

  $('btn-save-avs').addEventListener('click', saveAvs);
  $('btn-clear-avs').addEventListener('click', clearAvs);
  $('set-avs').addEventListener('keydown', function (e) { if (e.key === 'Enter') saveAvs(); });

  $('btn-check-update').addEventListener('click', checkUpdate);
  $('btn-open-project').addEventListener('click', function () { openUrl(APPMETA.projectUrl); });
  $('update-result').addEventListener('click', function (e) {
    const btn = e.target.closest('[data-url]');
    if (btn) openUrl(btn.getAttribute('data-url'));
  });

  function bindOpenFolder(btnId, scope) {
    const btn = $(btnId);
    if (!btn) return;
    btn.addEventListener('click', async function () {
      const data = await postJson('/api/open-folder', { scope: scope });
      if (!data.ok) toast(data.error || '打开文件夹失败', true);
    });
  }
  bindOpenFolder('btn-open-folder', 'dl');
  bindOpenFolder('btn-open-fav', 'fav');

  bindDiskHover('disk-pdf', 'pdf', '下载目录');
  bindDiskHover('disk-fav', 'fav', '收藏目录');

  $('btn-theme').addEventListener('click', toggleTheme);

  $('addr-pill').addEventListener('click', async function () {
    const text = $('addr-text').textContent.trim();
    try {
      await navigator.clipboard.writeText(text);
      toast('已复制：' + text);
    } catch (e) {
      toast(text);
    }
  });

  window.addEventListener('resize', function () { $('disk-pop').classList.add('hidden'); });

  /* ---------------- 启动 ---------------- */
  function maybeShowDiskHover() {
    try {
      const dh = new URLSearchParams(location.search).get('diskhover');
      if (dh === 'pdf' || dh === 'fav') {
        showDiskPop(dh === 'pdf' ? 'disk-pdf' : 'disk-fav', dh,
          dh === 'pdf' ? '下载目录' : '收藏目录');
      }
    } catch (e) { }
  }

  bindAlbumHit();
  syncThemeIcon();

  // 支持用 /?id=422869 直接带编号进来（方便分享/调试）
  try {
    const initialId = new URLSearchParams(location.search).get('id');
    if (initialId && /^\d+$/.test(initialId)) {
      $('album-id').value = initialId;
      scheduleLookup(initialId);
    }
  } catch (e) { }
  updatePaths();
  loadRecords();
  loadDisk().then(maybeShowDiskHover);
  pollState();
  setInterval(pollState, POLL_MS);

  try {
    const v = new URLSearchParams(location.search).get('view');
    if (v === 'favorites' || v === 'settings') switchView(v);
  } catch (e) { }
})();
