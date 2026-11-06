/* JM 下载助手 —— 前端逻辑 */
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const PATHS = window.JM_PATHS || { pdf: '', fav: '', defaults: {} };
  const APPMETA = window.JM_APP || { version: '', projectUrl: '', releasesUrl: '' };
  // 手机模板会把它设成 'mobile'，桌面模板没有这个变量
  const IS_MOBILE = window.JM_LAYOUT === 'mobile';
  const MAX_TAGS = IS_MOBILE ? 2 : 4;

  const STAR_OUT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><path d="M12 3.5l2.6 5.3 5.9.9-4.2 4.1 1 5.8-5.3-2.8-5.3 2.8 1-5.8-4.2-4.1 5.9-.9z"/></svg>';
  const STAR_ON = '<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><path d="M12 3.5l2.6 5.3 5.9.9-4.2 4.1 1 5.8-5.3-2.8-5.3 2.8 1-5.8-4.2-4.1 5.9-.9z"/></svg>';
  const TRASH = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13M10 11v6M14 11v6"/></svg>';

  const POLL_MS = 1000;
  const THEME_KEY = 'jm-theme';
  const VIEWS = ['download', 'favorites', 'settings'];

  const state = {
    view: 'download',
    dl: { q: '', scope: 'all', sort: 'time' },
    fav: { q: '', scope: 'all', sort: 'time' },
  };

  const recordIndex = {};
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

    // 文件不在本机就不去请求封面，省一次 404
    const coverAttrs = r.exists === false ? '' :
      ' data-cover="' + escapeHtml(r.file) + '"' +
      ' data-cover-dir="' + escapeHtml(r.dir || '') + '"';

    return '<article class="record" data-file="' + escapeHtml(r.file) + '" data-id="' + escapeHtml(r.id) + '" data-dir="' + escapeHtml(r.dir || '') + '">' +
      '<button class="icon-btn star ' + (starred ? 'on' : '') + '" title="' +
      (starred ? '取消收藏' : '收藏到 ' + escapeHtml(PATHS.fav)) + '">' + (starred ? STAR_ON : STAR_OUT) + '</button>' +
      '<div class="record-cover"><img alt=""' + coverAttrs + '></div>' +
      '<div class="record-main" title="点击用系统默认程序打开">' +
      '<div class="record-id' + (isId ? '' : ' muted') + '">' + escapeHtml(r.id) + '</div>' +
      '<div class="record-name">' + escapeHtml(r.name) + '</div>' +
      (r.author ? '<div class="record-author">作者：' + escapeHtml(r.author) + '</div>' : '') +
      ((r.tags && r.tags.length) ? '<div class="record-tags">' +
        r.tags.slice(0, MAX_TAGS).map(function (tag) { return '<span>' + escapeHtml(tag) + '</span>'; }).join('') +
        (r.tags.length > MAX_TAGS
          ? (IS_MOBILE
              // 手机端不显示「查看更多」，多出来的只报个数，点卡片就能看全部
              ? '<span class="tag-rest">+' + (r.tags.length - MAX_TAGS) + '</span>'
              : '<button class="tag-more" data-key="' + escapeHtml(r.file) + '" data-tags="' + escapeHtml(r.tags.join('|')) + '" title="查看全部标签">查看更多</button>')
          : '') +
        '</div>' : '') +
      '<div class="record-time">' + escapeHtml(r.time) +
        (r.likes ? ' · 赞 ' + escapeHtml(r.likes) : '') + '</div>' +
      (missing ? '<div class="record-meta">' + missing + '</div>' : '') +
      '</div>' +
      '<button class="icon-btn trash" title="删除文件并抹去记录">' + TRASH + '</button>' +
      '</article>';
  }

  /* 封面懒加载：滚到附近才去渲染，70 条记录不会一次拉 70 张图 */
  let coverObserver = null;

  function observeCovers() {
    const imgs = document.querySelectorAll('.record-cover img[data-cover]:not([data-observed])');
    if (!imgs.length) {
      return;
    }

    if (typeof IntersectionObserver !== 'function') {
      // 老浏览器直接全部加载
      imgs.forEach(function (img) {
        img.setAttribute('data-observed', '1');
        loadCover(img);
      });
      return;
    }

    if (!coverObserver) {
      coverObserver = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) {
            return;
          }
          coverObserver.unobserve(entry.target);
          loadCover(entry.target);
        });
      }, { rootMargin: '240px 0px' });
    }

    imgs.forEach(function (img) {
      img.setAttribute('data-observed', '1');
      coverObserver.observe(img);
    });
  }

  function loadCover(img) {
    const file = img.getAttribute('data-cover');
    const dir = img.getAttribute('data-cover-dir') || '';
    if (!file) {
      return;
    }

    img.onload = function () { img.classList.add('loaded'); };
    img.onerror = function () { img.style.visibility = 'hidden'; };
    img.src = '/api/cover?file=' + encodeURIComponent(file)
      + (dir ? '&dir=' + encodeURIComponent(dir) : '');
  }

  function renderInto(listEl, countEl, badgeEl, records, scope) {
    if (badgeEl) {
      badgeEl.textContent = state[scope === 'fav' ? 'fav' : 'dl'].scope === 'recent' ? '最近 500 条' : '全部记录';
    }

    if (!records.length) {
      listEl.innerHTML = '<div class="empty">没有匹配的记录</div>';
      countEl.textContent = '共 0 条记录';
      return;
    }
    listEl.innerHTML = records.map(function (r) { return recordHtml(r, scope); }).join('');
    records.forEach(function (r) { recordIndex[r.file] = r; });
    countEl.textContent = '共 ' + records.length + ' 条记录';
    observeCovers();
  }

  /* ---------------- 随机推荐 ---------------- */
  const RANDOM_COUNT = { dl: 1, fav: 2 };     // 收藏页左列空，一次推两本
  const randomPool = { dl: [], fav: [] };
  const randomPick = { dl: [], fav: [] };
  let randomTimer = null;
  let randomCooldown = 0;                     // 刚换过视图时先别再自动换

  function pickRandomItems(scope, count) {
    const pool = randomPool[scope] || [];
    if (!pool.length) return [];

    const lastFiles = (randomPick[scope] || []).map(function (r) { return r.file; });
    let candidates = pool.filter(function (r) { return lastFiles.indexOf(r.file) < 0; });
    if (candidates.length < count) candidates = pool.slice();

    const out = [];
    const copy = candidates.slice();
    while (out.length < count && copy.length) {
      out.push(copy.splice(Math.floor(Math.random() * copy.length), 1)[0]);
    }
    return out;
  }

  function renderRandom(scope) {
    const slot = $(scope + '-random-slot');
    if (!slot) return;

    const pool = randomPool[scope] || [];
    if (!pool.length) {
      slot.innerHTML = '<div class="random-empty">还没有记录，下载或收藏之后这里会随机推荐一本。</div>';
      randomPick[scope] = [];
      return;
    }

    const count = Math.min(RANDOM_COUNT[scope] || 1, pool.length);
    const picks = pickRandomItems(scope, count);
    randomPick[scope] = picks;

    // 收藏页左列空间大，顺带把下载时间和标签也带上
    const detailed = scope === 'fav';

    slot.innerHTML = picks.map(function (pick) {
      const cover = pick.exists === false ? '' :
        '/api/cover?file=' + encodeURIComponent(pick.file) +
        (pick.dir ? '&dir=' + encodeURIComponent(pick.dir) : '');

      const meta = [
        pick.author ? '作者：' + pick.author : '',
        pick.likes ? '赞 ' + pick.likes : ''
      ].filter(Boolean).join(' · ');

      const timeText = detailed && pick.time ? pick.time : '';
      const tags = detailed ? (pick.tags || []).slice(0, 3) : [];

      return '<div class="random-item" data-file="' + escapeHtml(pick.file) + '" title="点击查看详情">' +
        '<div class="random-cover">' +
          (cover ? '<img src="' + escapeHtml(cover) + '" alt="">' : '') +
        '</div>' +
        '<div class="random-info">' +
          '<div class="random-id">' + escapeHtml(pick.id) + '</div>' +
          '<div class="random-name">' + escapeHtml(pick.name) + '</div>' +
          (meta ? '<div class="random-meta">' + escapeHtml(meta) + '</div>' : '') +
          (timeText ? '<div class="random-time">' + escapeHtml(timeText) + '</div>' : '') +
          (tags.length
            ? '<div class="random-tags">' +
                tags.map(function (t) { return '<span>' + escapeHtml(t) + '</span>'; }).join('') +
              '</div>'
            : '') +
        '</div>' +
      '</div>';
    }).join('');
  }

  function bindRandom() {
    ['dl', 'fav'].forEach(function (scope) {
      const slot = $(scope + '-random-slot');
      if (slot) {
        slot.addEventListener('click', function (e) {
          const item = e.target.closest('.random-item');
          if (!item) return;
          const file = item.getAttribute('data-file');
          const rec = (randomPick[scope] || []).filter(function (r) {
            return r.file === file;
          })[0];
          if (rec) showRecordPreview(rec, scope);
        });
      }
      const btn = $(scope + '-random-next');
      if (btn) btn.addEventListener('click', function () { renderRandom(scope); });
    });
  }

  // 页面上的任何操作都会重抽一次；点空白、点推荐卡片、点弹窗都不算
  function scheduleRandomRefresh(e) {
    if (Date.now() < randomCooldown) return;

    if (e && e.type === 'click') {
      const t = e.target;
      if (!t || t === document.body) return;
      if (t.closest && (t.closest('.stack-grow') || t.closest('.modal'))) return;
      const cls = t.className;
      if (typeof cls === 'string' &&
          /(^|\s)(content|view|grid|stack|records|page-head)(\s|$)/.test(cls)) return;
    }

    if (randomTimer) clearTimeout(randomTimer);
    randomTimer = setTimeout(function () {
      randomTimer = null;
      if (Date.now() < randomCooldown) return;   // 期间切过页，就别再换了
      renderRandom('dl');
      renderRandom('fav');
    }, 1200);
  }

  function bindRandomTriggers() {
    ['click', 'input', 'change', 'keydown'].forEach(function (ev) {
      document.addEventListener(ev, scheduleRandomRefresh, true);
    });
  }

  /* ---------------- 数据加载 ---------------- */
  async function loadRecords() {
    const st = state.dl;
    const params = new URLSearchParams({ scope: st.scope });
    if (st.q) params.set('q', st.q);
    if (st.sort) params.set('sort', st.sort);

    try {
      const res = await fetch('/api/records?' + params.toString(), { cache: 'no-store' });
      const data = await res.json();
      renderInto($('dl-records'), $('dl-count'), $('dl-badge'), data.records || [], 'dl');

      // 随机推荐用全量记录；搜索时保留上次那份全量
      if (!st.q && st.scope === 'all') randomPool.dl = data.records || [];
      else if (!randomPool.dl.length) randomPool.dl = data.records || [];
      renderRandom('dl');
      randomCooldown = Date.now() + 8000;
    } catch (e) {
      $('dl-records').innerHTML = '<div class="empty">读取记录失败：' + escapeHtml(e.message) + '</div>';
    }
  }

  async function loadFavorites() {
    const st = state.fav;
    const params = new URLSearchParams({ scope: st.scope });
    if (st.q) params.set('q', st.q);
    if (st.sort) params.set('sort', st.sort);

    try {
      const res = await fetch('/api/favorites?' + params.toString(), { cache: 'no-store' });
      const data = await res.json();
      renderInto($('fav-records'), $('fav-count'), $('fav-badge'), data.records || [], 'fav');

      if (!st.q && st.scope === 'all') randomPool.fav = data.records || [];
      else if (!randomPool.fav.length) randomPool.fav = data.records || [];
      renderRandom('fav');
      randomCooldown = Date.now() + 8000;

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

    if (event.target.closest('.tag-more')) {
      const btn = event.target.closest('.tag-more');
      hideTagTip();
      const record = recordIndex[btn.getAttribute('data-key')];
      if (record) {
        showRecordPreview(record);
      } else {
        showAllTags((btn.getAttribute('data-tags') || '').split('|').filter(Boolean));
      }
      return;
    }

    if (event.target.closest('.star')) {
      const starred = event.target.closest('.star').classList.contains('on');
      toggleFavorite(file, jmId, starred);
    } else if (event.target.closest('.trash')) {
      deleteRecord(file, jmId, scope);
    } else if (IS_MOBILE) {
      // 手机上点卡片任意位置都弹详情，不直接打开 PDF
      const rec = recordIndex[file];
      if (rec) showRecordPreview(rec, scope);
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

    // 每次重新渲染都要换 URL：同一个 src 重复赋值浏览器不会再触发 onload，
    // 结果就是第二次输入同一编号时封面停在占位图上。
    const coverUrl = '/api/cover?file=' + encodeURIComponent(record.file)
      + '&v=' + Date.now();

    img.classList.add('hidden');
    img.removeAttribute('src');
    fallback.classList.remove('hidden');
    fallback.textContent = '载入中…';

    img.onload = function () {
      img.classList.remove('hidden');
      fallback.classList.add('hidden');
    };
    img.onerror = function () {
      img.classList.add('hidden');
      fallback.classList.remove('hidden');
      fallback.textContent = 'JM';
    };
    img.src = coverUrl;

    box.classList.remove('hidden');
    if (!state.running) { setStatusBadge('已下载', 'badge badge-success'); }
  }

  function setStatusBadge(text, className) {
    const el = $('status-text');
    if (!el) return;
    el.textContent = text;
    el.className = className;
  }


  /* ---------------- 预览封面 ---------------- */
  async function doPreview() {
    const el = $('album-id');
    const id = el.value.trim();
    if (!id) { toast('请输入本子编号', true); el.focus(); return; }
    if (!/^\d+$/.test(id)) { toast('编号必须是纯数字', true); el.focus(); return; }

    toast('正在获取封面…');
    try {
      const res = await fetch('/api/preview?id=' + encodeURIComponent(id), { cache: 'no-store' });
      const data = await res.json();
      if (!data.ok) { toast(data.error || '预览失败', true); return; }
      showPreview(data.album);
    } catch (e) {
      toast('预览失败：' + e.message, true);
    }
  }

  function showPreview(album, coverSrc, options) {
    options = options || {};
    const box = $('preview-modal');
    $('pv-id').textContent = album.id || '';
    $('pv-name').textContent = album.title || '';
    $('pv-meta').textContent = [
      album.author ? '作者：' + album.author : '',
      album.page_count ? album.page_count + ' 页' : '',
      album.episodes ? album.episodes + ' 章' : '',
      album.likes ? '赞 ' + album.likes : '',
      album.views ? '看 ' + album.views : ''
    ].filter(Boolean).join(' · ');

    $('pv-tags').innerHTML = (album.tags || [])
      .map(function (x) { return '<span>' + escapeHtml(x) + '</span>'; }).join('');
    $('pv-desc').textContent = album.description || '';

    const img = $('pv-cover');
    const fallback = $('pv-cover-fallback');
    img.classList.add('hidden');
    fallback.classList.remove('hidden');
    fallback.textContent = album.cover_error ? '封面获取失败' : '载入中…';

    const src = coverSrc || (album.cover_base64
      ? 'data:image/jpeg;base64,' + album.cover_base64 : '');
    if (src) {
      img.onload = function () {
        img.classList.remove('hidden');
        fallback.classList.add('hidden');
      };
      img.onerror = function () {
        fallback.textContent = '封面加载失败';
      };
      img.src = src;
    } else {
      fallback.textContent = '暂无封面';
    }

    const cancelBtn = $('pv-cancel');
    const mainBtn = $('pv-download');
    const favBtn = $('pv-fav');
    const delBtn = $('pv-delete');
    const rec = options.record || null;

    if (options.openFile) {
      if (cancelBtn) cancelBtn.textContent = '关闭';
      mainBtn.textContent = '打开';
      mainBtn.onclick = function () {
        box.classList.add('hidden');
        if (IS_MOBILE && options.record) {
          openReader(options.record);        // 手机上「打开」= 在线左右翻页看
        } else {
          openRecordFile(options.file, options.scope || 'dl', options.dir || '');
        }
      };
    } else {
      if (cancelBtn) cancelBtn.textContent = '取消';
      mainBtn.textContent = '开始下载';
      mainBtn.onclick = function () {
        box.classList.add('hidden');
        $('album-id').value = album.id || '';
        doDownload();
      };
    }

    // 收藏 / 删除只在手机模板里有（桌面模板没有这两个按钮）
    if (favBtn) {
      if (rec) {
        const starred = options.scope === 'fav' ? true : !!rec.fav;
        favBtn.classList.remove('hidden');
        favBtn.textContent = starred ? '取消收藏' : '收藏';
        favBtn.onclick = function () {
          box.classList.add('hidden');
          toggleFavorite(rec.file, rec.id, starred);
        };
      } else {
        favBtn.classList.add('hidden');
      }
    }

    if (delBtn) {
      if (rec) {
        delBtn.classList.remove('hidden');
        delBtn.onclick = function () {
          box.classList.add('hidden');
          deleteRecord(rec.file, rec.id, options.scope || 'dl');
        };
      } else {
        delBtn.classList.add('hidden');
      }
    }

    box.classList.remove('hidden');
  }


  /* ---------------- 在线阅读：左右翻页 ---------------- */
  const RD_DIR_KEY = 'jm-read-dir';

  const readerState = {
    rec: null, pages: [], index: 0, total: 0,
    dir: 'left', pushed: false, touch: null,
  };

  function readerUrl(rec, n) {
    return '/api/page?file=' + encodeURIComponent(rec.file) +
      (rec.dir ? '&dir=' + encodeURIComponent(rec.dir) : '') +
      '&n=' + n;
  }

  function updateReaderCount() {
    const label = $('rd-count');
    if (!label) return;
    if (!readerState.total) { label.textContent = '—'; return; }
    label.textContent = (readerState.index + 1) + ' / ' + readerState.total;
  }

  function paintReaderDir() {
    const btn = $('rd-dir');
    // 按钮显示的是「点了会变成什么」，不是当前状态
    if (btn) btn.textContent = readerState.dir === 'left' ? '切换右滑翻页' : '切换左滑翻页';

    // 日漫方向：用 flex order 把页码倒过来排，下一页就落在上一页左边
    const total = readerState.total;
    readerState.pages.forEach(function (img, i) {
      const page = img.parentNode;
      if (!page) return;
      page.style.order = String(readerState.dir === 'left' ? (total - 1 - i) : i);
    });
  }

  // 第 n 页在横向排列里的位置：日漫方向要倒过来数
  function pageSlot(n) {
    return readerState.dir === 'left'
      ? (readerState.total - 1 - n)
      : n;
  }

  // 直接用元素自身的 offsetLeft，避免「页宽 × 页数」累加出来的亚像素误差
  function pageOffset(n) {
    const img = readerState.pages[n];
    const page = img && img.parentNode;
    if (page && typeof page.offsetLeft === 'number') return page.offsetLeft;
    const stage = $('rd-stage');
    return pageSlot(n) * (stage ? stage.clientWidth : 0);
  }

  function loadPage(img) {
    if (!img || img.dataset.src) return;
    img.dataset.src = '1';
    img.onerror = function () { img.setAttribute('data-failed', '1'); };
    img.src = readerUrl(readerState.rec, Number(img.dataset.page));
  }

  function ensureLoaded(n) {
    for (let i = n - 1; i <= n + 1; i++) {
      if (readerState.pages[i]) loadPage(readerState.pages[i]);
    }
  }

  function moveTrack(px, animate) {
    const track = $('rd-body');
    if (!track) return;
    track.style.transition = animate
      ? 'transform .28s cubic-bezier(.32,.72,0,1)'
      : 'none';
    track.style.transform = 'translate3d(' + px + 'px,0,0)';
  }

  function goToPage(n, animate) {
    if (!readerState.total) return;
    n = Math.max(0, Math.min(n, readerState.total - 1));
    readerState.index = n;

    moveTrack(-pageOffset(n), animate !== false);
    updateReaderCount();
    ensureLoaded(n);
  }

  function closeReader() {
    const box = $('reader');
    if (!box) return;
    box.classList.add('hidden');

    readerState.rec = null;
    readerState.pages = [];
    readerState.total = 0;
    readerState.index = 0;
    readerState.touch = null;

    const track = $('rd-body');
    if (track) { track.innerHTML = ''; track.style.transform = ''; }
  }

  function exitReader() {
    if (readerState.pushed) {
      readerState.pushed = false;
      history.back();        // 让 popstate 收尾，历史里那条也一并弹掉
    } else {
      closeReader();
    }
  }

  async function openReader(rec) {
    const box = $('reader');
    const track = $('rd-body');
    if (!box || !track) { toast('当前页面不支持在线阅读', true); return; }

    $('rd-title').textContent = rec.name || rec.file;
    $('rd-count').textContent = '载入中…';
    track.innerHTML = '';
    track.style.transform = '';
    box.classList.remove('hidden');

    let info;
    try {
      const res = await fetch('/api/pdf-info?file=' + encodeURIComponent(rec.file) +
        (rec.dir ? '&dir=' + encodeURIComponent(rec.dir) : ''), { cache: 'no-store' });
      info = await res.json();
    } catch (e) {
      info = { ok: false, error: e.message };
    }

    if (!info.ok) {
      box.classList.add('hidden');
      // 在线渲染不可用就退回原来的打开方式，功能不丢
      toast(info.error || '无法在线阅读，改用电脑上的程序打开', true);
      openRecordFile(rec.file, 'dl', rec.dir || '');
      return;
    }

    readerState.rec = rec;
    readerState.total = info.pages;
    readerState.index = 0;
    readerState.pages = [];

    const frag = document.createDocumentFragment();
    for (let i = 0; i < info.pages; i++) {
      const page = document.createElement('div');
      page.className = 'rd-page';
      const img = document.createElement('img');
      img.dataset.page = String(i);
      img.alt = '';
      page.appendChild(img);
      readerState.pages.push(img);
      frag.appendChild(page);
    }
    track.appendChild(frag);

    paintReaderDir();
    updateReaderCount();
    goToPage(0, false);

    // 单独记一条历史：浏览器返回键只关阅读器，不会把主页一起退掉
    history.pushState({ jmReader: 1 }, '');
    readerState.pushed = true;
  }

  function bindReaderTouch() {
    const stage = $('rd-stage');
    const track = $('rd-body');
    if (!stage || !track) return;

    stage.addEventListener('touchstart', function (e) {
      if (e.touches.length !== 1) return;
      readerState.touch = {
        x: e.touches[0].clientX,
        y: e.touches[0].clientY,
        moved: false,
      };
      track.style.transition = 'none';
    }, { passive: true });

    stage.addEventListener('touchmove', function (e) {
      const t = readerState.touch;
      if (!t) return;
      const dx = e.touches[0].clientX - t.x;
      const dy = e.touches[0].clientY - t.y;
      if (!t.moved && Math.abs(dx) < Math.abs(dy)) return;   // 竖向手势不拦
      t.moved = true;
      moveTrack(-pageOffset(readerState.index) + dx, false);
    }, { passive: true });

    const finish = function (e) {
      const t = readerState.touch;
      readerState.touch = null;
      if (!t) return;

      const touch = e.changedTouches && e.changedTouches[0];
      const dx = (touch ? touch.clientX : t.x) - t.x;
      const dy = (touch ? touch.clientY : t.y) - t.y;

      if (!t.moved || Math.abs(dx) < 40 || Math.abs(dx) < Math.abs(dy)) {
        goToPage(readerState.index, true);
        return;
      }

      // 日漫方向下一页在左边，所以要往回滑；常规方向正好相反
      const toNext = readerState.dir === 'left' ? dx > 0 : dx < 0;
      goToPage(readerState.index + (toNext ? 1 : -1), true);
    };

    stage.addEventListener('touchend', finish, { passive: true });
    stage.addEventListener('touchcancel', finish, { passive: true });
  }

  /* ---------------- 排序切换 ---------------- */
  // 按钮显示的是「点击后会切换成什么」，当前状态不会造成歧义
  function sortLabel(current) {
    if (IS_MOBILE) {
      return current === 'likes' ? '按时间' : '按点赞';
    }
    return current === 'likes' ? '切换为按时间排序' : '切换为按点赞排序';
  }

  function bindSort() {
    $('dl-sort').addEventListener('click', function () {
      state.dl.sort = state.dl.sort === 'likes' ? 'time' : 'likes';
      $('dl-sort').textContent = sortLabel(state.dl.sort);
      loadRecords();
    });
    $('fav-sort').addEventListener('click', function () {
      state.fav.sort = state.fav.sort === 'likes' ? 'time' : 'likes';
      $('fav-sort').textContent = sortLabel(state.fav.sort);
      loadFavorites();
    });
  }

  /* ---------------- 详情刷新 ---------------- */
  let detailTimer = null;

  async function refreshDetails() {
    const data = await postJson('/api/refresh-details', {});
    if (!data.ok) { toast(data.error || '无法开始详情刷新', true); return; }
    toast('开始刷新详情…');
    pollDetailProgress();
  }

  async function pollDetailProgress() {
    try {
      const res = await fetch('/api/refresh-details/status', { cache: 'no-store' });
      const st = await res.json();
      if (!st.running) {
        if (detailTimer) { clearTimeout(detailTimer); detailTimer = null; }
        const ends = st.done > 0;
        if (ends) {
          detailCacheReset();
          toast(st.error ? ('详情刷新结束，最后一条出错：' + st.error)
                         : ('详情刷新完成，共更新 ' + st.done + ' 部'));
          loadRecords();
          loadFavorites();
        }
        return;
      }
      toast('详情刷新中：' + st.done + ' / ' + st.total + (st.current ? '（' + st.current + '）' : ''));
      detailTimer = setTimeout(pollDetailProgress, 1200);
    } catch (e) {
      detailTimer = setTimeout(pollDetailProgress, 2000);
    }
  }

  function detailCacheReset() {
    loadRecords();
    if (state.view === 'favorites') loadFavorites();
  }



  /* ---------------- 记录项：漫画详情弹窗 ---------------- */
  function showRecordPreview(r, scope) {
    const coverSrc = r.exists === false ? '' :
      '/api/cover?file=' + encodeURIComponent(r.file) +
      (r.dir ? '&dir=' + encodeURIComponent(r.dir) : '');

    showPreview({
      id: r.id,
      title: r.name,
      author: r.author || '',
      page_count: r.pages || '',
      likes: r.likes || '',
      views: r.views || '',
      tags: r.tags || [],
      description: '',
    }, coverSrc, {
      openFile: true,
      file: r.file,
      dir: r.dir || '',
      scope: scope || 'dl',
      record: r,
    });
  }

  let tagTip = null;


  // 浮层定位：默认在鼠标正上方（水平居中、垂直间隔 12px），两侧/顶部越界时自动挪回
  function tipLeft(clientX) {
    if (!tagTip) return 8;
    const rect = tagTip.getBoundingClientRect();
    const left = clientX - rect.width / 2;
    return Math.max(8, Math.min(left, window.innerWidth - rect.width - 8));
  }

  function tipTop(clientY) {
    if (!tagTip) return 8;
    const rect = tagTip.getBoundingClientRect();
    let top = clientY - rect.height - 12;
    if (top < 8) {
      top = clientY + 18;               // 上方放不下就翻到下方
    }
    return Math.max(8, Math.min(top, window.innerHeight - rect.height - 8));
  }

  function showTagTip(tags, x, y) {
    hideTagTip();
    tagTip = document.createElement('div');
    tagTip.className = 'tag-tip';
    tagTip.innerHTML = tags.map(function (tag) {
      return '<span>' + escapeHtml(tag) + '</span>';
    }).join('');
    document.body.appendChild(tagTip);

    tagTip.style.left = tipLeft(x) + 'px';
    tagTip.style.top = tipTop(y) + 'px';
  }

  function hideTagTip() {
    if (tagTip) {
      tagTip.remove();
      tagTip = null;
    }
  }

  function bindTagTip() {
    ['dl-records', 'fav-records'].forEach(function (id) {
      const list = $(id);
      if (!list) return;
      list.addEventListener('mouseover', function (e) {
        const btn = e.target.closest('.tag-more');
        if (!btn) return;
        const tags = (btn.getAttribute('data-tags') || '').split('|').filter(Boolean);
        showTagTip(tags, e.clientX, e.clientY);
      });
      list.addEventListener('mousemove', function (e) {
        if (!tagTip) return;
        tagTip.style.left = tipLeft(e.clientX) + 'px';
        tagTip.style.top = tipTop(e.clientY) + 'px';
      });
      list.addEventListener('mouseout', function (e) {
        if (!e.relatedTarget || !e.relatedTarget.closest || !e.relatedTarget.closest('.tag-more')) {
          hideTagTip();
        }
      });
      list.addEventListener('scroll', hideTagTip, true);
    });
  }

  function showAllTags(tags) {
    const list = $('tag-all-list');
    list.innerHTML = tags.map(function (tag) {
      return '<span>' + escapeHtml(tag) + '</span>';
    }).join('');
    $('tag-modal').classList.remove('hidden');
  }

  function bindTagModal() {
    $('tag-close').addEventListener('click', function () { $('tag-modal').classList.add('hidden'); });
    $('tag-ok').addEventListener('click', function () { $('tag-modal').classList.add('hidden'); });
    $('tag-modal').addEventListener('click', function (e) {
      if (e.target === $('tag-modal')) { $('tag-modal').classList.add('hidden'); }
    });
  }

  function bindPreview() {
    $('btn-preview').addEventListener('click', doPreview);
    $('pv-close').addEventListener('click', function () { $('preview-modal').classList.add('hidden'); });
    // 手机模板用右上角 ✕ 关闭，没有独立的「关闭」按钮
    const cancelBtn = $('pv-cancel');
    if (cancelBtn) {
      cancelBtn.addEventListener('click', function () { $('preview-modal').classList.add('hidden'); });
    }
    $('preview-modal').addEventListener('click', function (e) {
      if (e.target === $('preview-modal')) { $('preview-modal').classList.add('hidden'); }
    });
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

  /* ---------------- 局域网访问 ---------------- */
  let lanState = null;

  function paintLan(data) {
    lanState = data;

    const on = !!data.enabled;
    const def = !!data.default;

    const ips = data.ips || [];
    const urlEl = $('lan-url');
    if (ips.length) {
      urlEl.textContent = 'http://' + ips[0] + ':' + data.port;
      urlEl.classList.toggle('off', !on);
    } else {
      urlEl.textContent = '未检测到局域网地址';
      urlEl.classList.add('off');
    }
    $('lan-token').textContent = data.token || '—';

    const sw = $('btn-lan-toggle');
    if (sw) {
      sw.classList.toggle('on', on);
      sw.setAttribute('aria-checked', on ? 'true' : 'false');
      sw.title = on ? '局域网访问已开启，点击关闭' : '局域网访问已关闭，点击开启';
    }

    const defSw = $('btn-lan-default');
    if (defSw) {
      defSw.classList.toggle('on', def);
      defSw.setAttribute('aria-checked', def ? 'true' : 'false');
      defSw.title = def ? '每次启动都会自动开启局域网访问' : '启动时沿用上次的开关状态';
    }

    const writeSw = $('btn-lan-write');
    if (writeSw) {
      const allow = !!data.allow_write;
      writeSw.classList.toggle('on', allow);
      writeSw.setAttribute('aria-checked', allow ? 'true' : 'false');
      writeSw.title = allow
        ? '手机可以删除漫画、增删收藏，点击收回权限'
        : '手机只能浏览，点击允许删除和收藏';
    }
  }

  async function loadLan() {
    try {
      const res = await fetch('/api/lan', { cache: 'no-store' });
      const data = await res.json();
      if (!data.ok) {
        if (data.local_only || data.need_login) {
          $('card-lan').classList.add('hidden');
        }
        return;
      }
      $('card-lan').classList.remove('hidden');
      paintLan(data);
    } catch (e) {
      $('card-lan').classList.add('hidden');
    }
  }

  async function toggleLan() {
    const willOpen = !(lanState && lanState.enabled);
    const data = await postJson('/api/lan', { enabled: willOpen });
    if (!data.ok) { toast(data.error || '操作失败', true); return; }

    paintLan(data);
    toast(willOpen ? '已开启，手机连同一 Wi-Fi 打开上面的地址' : '局域网访问已关闭');
  }

  async function toggleLanDefault() {
    const willOn = !(lanState && lanState.default);
    const data = await postJson('/api/lan', { default: willOn });
    if (!data.ok) { toast(data.error || '设置失败', true); return; }

    paintLan(data);
    toast(willOn ? '已设置：下次启动自动开启局域网访问' : '已设置：下次启动沿用上次的开关状态');
  }

  async function toggleLanWrite() {
    const willOn = !(lanState && lanState.allow_write);
    if (willOn && !confirm(
      '允许手机删除和收藏？\n\n' +
      '打开后，局域网里知道口令的设备可以：\n' +
      '· 删除电脑上的漫画文件和记录\n' +
      '· 增加或取消收藏\n\n' +
      '「清除所有下载数据」仍然只能在电脑本机执行。')) return;

    const data = await postJson('/api/lan', { allow_write: willOn });
    if (!data.ok) { toast(data.error || '设置失败', true); return; }

    paintLan(data);
    toast(willOn ? '手机现在可以删除和收藏了' : '手机已恢复为只能浏览');
  }

  async function resetLanToken() {
    if (!confirm('重新生成访问口令？\n\n已经在手机上登录过的设备，需要重新输入新口令。')) return;

    const data = await postJson('/api/lan', { reset_token: true });
    if (!data.ok) { toast(data.error || '生成失败', true); return; }
    paintLan(data);
    toast('新口令：' + (data.token || ''));
  }

  async function copyLanUrl() {
    if (!lanState || !lanState.enabled) { toast('先开启局域网访问', true); return; }
    const urls = lanState.urls || [];
    if (!urls.length) { toast('没检测到局域网地址，检查网络连接', true); return; }

    const text = urls[0];
    try {
      await navigator.clipboard.writeText(text);
      toast('已复制：' + text);
    } catch (e) {
      toast(text);
    }
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
      loadLan();
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
  bindPreview();
  bindTagModal();
  bindTagTip();
  bindSort();
  $('dl-detail-refresh').addEventListener('click', refreshDetails);
  $('fav-detail-refresh').addEventListener('click', refreshDetails);
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

  $('btn-lan-token').addEventListener('click', resetLanToken);
  $('btn-lan-copy').addEventListener('click', copyLanUrl);

  // 手机模板里主开关放在 <summary> 里，点它别让折叠面板跟着展开
  $('btn-lan-toggle').addEventListener('click', function (e) {
    e.stopPropagation();
    toggleLan();
  });

  const lanDefSw = $('btn-lan-default');
  if (lanDefSw) lanDefSw.addEventListener('click', toggleLanDefault);

  const lanWriteSw = $('btn-lan-write');
  if (lanWriteSw) lanWriteSw.addEventListener('click', toggleLanWrite);

  const rdBack = $('rd-back');
  if (rdBack) rdBack.addEventListener('click', exitReader);

  const rdDirBtn = $('rd-dir');
  if (rdDirBtn) {
    try {
      const saved = localStorage.getItem(RD_DIR_KEY);
      if (saved === 'left' || saved === 'right') readerState.dir = saved;
    } catch (e) { }
    rdDirBtn.addEventListener('click', function () {
      readerState.dir = readerState.dir === 'left' ? 'right' : 'left';
      try { localStorage.setItem(RD_DIR_KEY, readerState.dir); } catch (e) { }
      paintReaderDir();
      goToPage(readerState.index, false);
      toast(readerState.dir === 'left' ? '日漫方向：下一页在左边' : '常规方向：下一页在右边');
    });
  }

  // 浏览器 / 手机返回键：只关阅读器，不把主页一起退掉
  window.addEventListener('popstate', function () {
    const box = $('reader');
    if (box && !box.classList.contains('hidden')) {
      readerState.pushed = false;
      closeReader();
    }
  });

  bindReaderTouch();

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

  const addrPill = $('addr-pill');
  if (addrPill) {
    addrPill.addEventListener('click', async function () {
      const text = $('addr-text').textContent.trim();
      try {
        await navigator.clipboard.writeText(text);
        toast('已复制：' + text);
      } catch (e) {
        toast(text);
      }
    });
  }

  window.addEventListener('resize', function () {
    $('disk-pop').classList.add('hidden');
    const box = $('reader');
    if (box && !box.classList.contains('hidden')) goToPage(readerState.index, false);
  });

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

  bindRandom();
  bindRandomTriggers();
  bindAlbumHit();
  syncThemeIcon();

  // 支持 /?q=少女&sort=likes 直接带搜索/排序进来
  try {
    const params = new URLSearchParams(location.search);
    const initialQuery = params.get('q');
    const initialSort = params.get('sort');
    if (initialQuery) { state.dl.q = initialQuery; $('dl-search-id').value = initialQuery; }
    if (initialSort === 'likes') {
      state.dl.sort = 'likes';
      $('dl-sort').textContent = sortLabel('likes');
    }
    if (initialQuery || initialSort) { loadRecords(); }
  } catch (e) { }

  // 支持用 /?preview=422869 直接打开预览（调试用）
  try {
    const previewId = new URLSearchParams(location.search).get('preview');
    if (previewId && /^\d+$/.test(previewId)) {
      $('album-id').value = previewId;
      doPreview();
    }
  } catch (e) { }

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
