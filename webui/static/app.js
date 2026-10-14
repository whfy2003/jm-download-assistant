/* JM 下载助手 —— 前端逻辑 */
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const PATHS = window.JM_PATHS || { pdf: '', fav: '', defaults: {} };

  const STAR_OUT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><path d="M12 3.5l2.6 5.3 5.9.9-4.2 4.1 1 5.8-5.3-2.8-5.3 2.8 1-5.8-4.2-4.1 5.9-.9z"/></svg>';
  const STAR_ON = '<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><path d="M12 3.5l2.6 5.3 5.9.9-4.2 4.1 1 5.8-5.3-2.8-5.3 2.8 1-5.8-4.2-4.1 5.9-.9z"/></svg>';
  const TRASH = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13M10 11v6M14 11v6"/></svg>';

  const POLL_MS = 1500;
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

    return '<article class="record" data-file="' + escapeHtml(r.file) + '" data-id="' + escapeHtml(r.id) + '">' +
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
  async function openRecordFile(file, scope) {
    const data = await postJson('/api/open-file', { file: file, scope: scope });
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
        '\n\n· 将从收藏夹删除该文件' +
        '\n· 并抹去收藏记录（下载目录中的文件不受影响）');
      if (!okConfirm) return;

      const data = await postJson('/api/delete', { file: file, id: jmId, scope: 'fav' });
      if (!data.ok) { toast(data.error || '取消收藏失败', true); return; }
      toast('已取消收藏');
    } else {
      const data = await postJson('/api/favorite', { file: file, id: jmId });
      if (!data.ok) { toast(data.error || '收藏失败', true); return; }
      toast(data.already ? '该文件已在收藏夹中' : '已收藏到 ' + PATHS.fav);
      if (data.warning) toast(data.warning, true);
    }

    loadRecords();
    if (state.view === 'favorites') loadFavorites();
    loadDisk(true);
  }

  function handleListClick(listEl, event) {
    const record = event.target.closest('.record');
    if (!record) return;

    const file = record.getAttribute('data-file');
    const jmId = record.getAttribute('data-id');
    const scope = listEl.getAttribute('data-scope') || 'dl';

    if (event.target.closest('.star')) {
      const starred = event.target.closest('.star').classList.contains('on');
      toggleFavorite(file, jmId, starred);
    } else if (event.target.closest('.trash')) {
      deleteRecord(file, jmId, scope);
    } else if (event.target.closest('.record-main')) {
      openRecordFile(file, scope);
    }
  }

  /* ---------------- 运行状态 ---------------- */
  function applyState(s) {
    const running = !!s.running;
    const elStatusText = $('status-text');

    $('spinner').classList.toggle('hidden', !running);

    if (running) {
      elStatusText.textContent = '程序运行中';
      elStatusText.className = 'badge';
    } else if (s.ok === false) {
      elStatusText.textContent = '上次任务失败';
      elStatusText.className = 'badge badge-danger';
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

  /* ---------------- 下载动作 ---------------- */
  async function doDownload() {
    const el = $('album-id');
    const id = el.value.trim();
    if (!id) { toast('请输入本子编号', true); el.focus(); return; }
    if (!/^\d+$/.test(id)) { toast('编号必须是纯数字', true); el.focus(); return; }

    $('btn-download').disabled = true;
    const data = await postJson('/api/download', { id: id });
    if (!data.ok) {
      toast(data.error || '启动下载失败', true);
      $('btn-download').disabled = false;
    } else {
      toast('已开始下载 ' + id);
      lastLoggedCount = -1;
      setTimeout(pollState, 400);
    }
  }

  /* ---------------- 设置 ---------------- */
  async function loadSettings() {
    try {
      const res = await fetch('/api/settings', { cache: 'no-store' });
      const data = await res.json();
      $('set-pdf').value = data.pdf_dir || '';
      $('set-fav').value = data.fav_dir || '';
      if (data.disk) {
        diskData = data.disk;
        paintSidebarBars();
        renderDiskDetail();
      }
    } catch (e) {
      toast('读取设置失败：' + e.message, true);
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

  $('btn-save-settings').addEventListener('click', saveSettings);
  $('btn-reset-settings').addEventListener('click', resetSettings);
  $('btn-disk-refresh').addEventListener('click', function () { loadDisk(true); toast('已重新统计磁盘占用'); });

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

  syncThemeIcon();
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
