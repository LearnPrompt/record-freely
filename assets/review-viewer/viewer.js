/* Numeric timeline operations also run under Node for portable regression tests. */
'use strict';
const ReviewTimeline = (() => {
  function rate(data) {
    const parts = data.fps.split('/').map(Number);
    return parts[0] / (parts[1] || 1);
  }
  function outputToSource(data, frame) {
    if (data.source_cuts === null) {
      const row = data.intervals.find(r => r.start_frame <= frame && frame < r.end_frame);
      return row ? row.source_start_frame + frame - row.start_frame : null;
    }
    let removed = 0;
    for (const [a, b] of data.source_cuts) {
      if (a - removed <= frame) removed += b - a;
      else break;
    }
    return frame + removed;
  }
  function sourceToOutput(data, frame) {
    if (data.source_cuts === null) {
      const row = data.intervals.find(r => r.source_start_frame <= frame && frame < r.source_end_frame);
      return row ? {frame: row.start_frame + frame - row.source_start_frame, deleted: false} : null;
    }
    let removed = 0;
    for (const [a, b] of data.source_cuts) {
      if (frame < a) break;
      if (frame < b) return {frame: Math.min(data.output_frames - 1, a - removed), deleted: true};
      removed += b - a;
    }
    return {frame: frame - removed, deleted: false};
  }
  function categoryIntervals(data, category = '') {
    if (!category) return data.intervals.map(r => ({...r, key: `all:${r.start_frame}:${r.end_frame}`}));
    let removed = 0;
    const boundaries = (data.source_cuts || []).map(([a, b]) => {
      const boundary = a - removed;
      removed += b - a;
      return boundary;
    });
    const pieces = [];
    for (const e of data.events.filter(e => e.category === category)) {
      const edges = [e.start_frame, ...boundaries.filter(f => e.start_frame < f && f < e.end_frame), e.end_frame];
      for (let i = 0; i < edges.length - 1; i++) pieces.push({start_frame: edges[i], end_frame: edges[i + 1]});
    }
    pieces.sort((a, b) => a.start_frame - b.start_frame || a.end_frame - b.end_frame);
    const rows = [];
    for (const piece of pieces) {
      const last = rows[rows.length - 1];
      if (last && piece.start_frame <= last.end_frame && !(piece.start_frame === last.end_frame && boundaries.includes(piece.start_frame))) {
        last.end_frame = Math.max(last.end_frame, piece.end_frame);
      } else rows.push({...piece});
    }
    return rows.map(r => ({...r, source_start_frame: outputToSource(data, r.start_frame),
      source_end_frame: outputToSource(data, r.end_frame - 1) + 1,
      key: `${category}:${r.start_frame}:${r.end_frame}`}));
  }
  function checkpoints(data, row) {
    const points = new Set([row.start_frame, Math.floor((row.start_frame + row.end_frame - 1) / 2), row.end_frame - 1]);
    const stride = Math.max(1, Math.round(rate(data) * 10));
    for (let f = row.start_frame + stride; f < row.end_frame; f += stride) points.add(f);
    for (const f of data.checkpoints) if (row.start_frame <= f && f < row.end_frame) points.add(f);
    return [...points].sort((a, b) => a - b);
  }
  function loopTarget(data, seconds, row) {
    // Chromium media clocks may truncate a rational frame time to microseconds.
    // Do not repeatedly seek when 56/30 is returned as 1.866666.
    const epsilon = 1e-5, fps = rate(data);
    return seconds >= row.end_frame / fps - epsilon || seconds < row.start_frame / fps - epsilon
      ? row.start_frame : null;
  }
  function intervalAtFrame(rows, frame) {
    return rows.find(row => row.start_frame <= frame && frame < row.end_frame) || null;
  }
  return {rate, outputToSource, sourceToOutput, categoryIntervals, checkpoints, loopTarget, intervalAtFrame};
})();
if (typeof module !== 'undefined') module.exports = ReviewTimeline;
if (typeof document !== 'undefined') startViewer().catch(error => {document.querySelector('#error').textContent = error.message;});

async function startViewer() {
  const response = await fetch('/timeline.json');
  if (!response.ok) throw new Error('时间轴加载失败');
  const data = await response.json(), fps = ReviewTimeline.rate(data);
  const $ = id => document.querySelector(id), video = $('#video'), pageSize = 60;
  const storageKey = 'record-freely-review-' + data.encoded_sha256;
  let notes = Object.create(null), selected = null, filtered = [], page = 0;
  try {
    const stored = JSON.parse(localStorage.getItem(storageKey) || '{}');
    for (const [key, value] of Object.entries(stored)) {
      if (/^[a-z0-9_-]+:\d+:\d+$/.test(key) && value && typeof value === 'object') {
        notes[key] = {text: typeof value.text === 'string' ? value.text.slice(0, 20000) : '', checked: value.checked === true};
      }
    }
  } catch (_) { /* Storage disabled or old malformed notes; export remains usable. */ }
  function time(frame) {
    if (frame === null) return '未提供映射';
    const milliseconds = Math.round(frame * 1000 / fps);
    return String(Math.floor(milliseconds / 60000)).padStart(2, '0') + ':' +
      String(Math.floor(milliseconds / 1000) % 60).padStart(2, '0') + '.' + String(milliseconds % 1000).padStart(3, '0');
  }
  const categoryNames = {url:'网址', path:'文件路径', parent_path:'父路径',
    email:'邮箱', phone:'电话号码', qr:'二维码', contact:'联系方式',
    engine_mask:'局部遮罩', ordered_overlay:'补充遮罩', r2_opaque_closure:'边缘补码', local:'局部打码'};
  const categoryName = value => categoryNames[value] || value || '局部打码';
  const categories = [...new Set(data.events.map(e => e.category))].sort();
  for (const category of categories) {
    const option = document.createElement('option');
    option.value = category; option.textContent = categoryName(category); $('#category').append(option);
  }
  $('#category').disabled = categories.length === 0;
  $('#scrubber').max = data.output_frames - 1;
  $('#version').textContent = `SHA256: ${data.encoded_sha256} · ${data.fps} fps · ${data.output_frames} 帧。` +
    (data.source_cuts === null ? ' 未提供原清单，原片时间仅在登记区间内可换算。类别筛选不可用。' : ' 原片删减已按清单换算。');
  function currentFrame() {return Math.min(data.output_frames - 1, Math.max(0, Math.round(video.currentTime * fps)));}
  function updateClock() {
    const frame = currentFrame();
    $('#clock').textContent = `${time(frame)} / ${time(data.output_frames)}`;
    $('#sourceClock').textContent = '原片 ' + time(ReviewTimeline.outputToSource(data, frame));
    $('#scrubber').value = frame;
  }
  function seek(frame) {
    video.currentTime = Math.max(0, Math.min(data.output_frames - 1, frame)) / fps;
    updateClock();
  }
  function save(show = true) {
    if (!selected) return;
    notes[selected.key] = {...(notes[selected.key] || {}), text: $('#note').value};
    if (!notes[selected.key].text && !notes[selected.key].checked) delete notes[selected.key];
    try {
      localStorage.setItem(storageKey, JSON.stringify(notes));
      if (show) $('#saved').textContent = '已保存到当前浏览器';
    } catch (_) {$('#saved').textContent = '浏览器存储不可用，请导出 JSON';}
  }
  function render() {
    const query = $('#search').value.trim().toLowerCase();
    filtered = ReviewTimeline.categoryIntervals(data, $('#category').value).filter(r =>
      [time(r.start_frame), time(r.end_frame), time(r.source_start_frame), notes[r.key]?.text || ''].join(' ').toLowerCase().includes(query));
    page = Math.max(0, Math.min(page, Math.ceil(filtered.length / pageSize) - 1));
    $('#list').replaceChildren();
    filtered.slice(page * pageSize, (page + 1) * pageSize).forEach((row, index) => {
      const button = document.createElement('button'); button.className = 'row';
      button.classList.toggle('active', selected?.key === row.key);
      const heading = document.createElement('strong');
      heading.textContent = `${time(row.start_frame)} → ${time(row.end_frame)}`;
      const meta = document.createElement('small');
      meta.textContent = `第 ${page * pageSize + index + 1} 处 · 原片 ${time(row.source_start_frame)}–${time(row.source_end_frame)}` +
        (notes[row.key]?.checked ? ' · 已检查 ✓' : '') + (notes[row.key]?.text ? ' · 有备注' : '');
      button.append(heading, meta); button.onclick = () => select(row); $('#list').append(button);
    });
    $('#count').textContent = `${filtered.length} 个连续局部打码区间 · 不跨无遮挡间隙或原片剪切接缝`;
    $('#page').textContent = `${page + 1} / ${Math.max(1, Math.ceil(filtered.length / pageSize))}`;
    $('#pagePrev').disabled = page === 0;
    $('#pageNext').disabled = (page + 1) * pageSize >= filtered.length;
    $('#prev').disabled = $('#next').disabled = filtered.length === 0;
  }
  function select(row, doSeek = true) {
    save(false); selected = row;
    $('#selection').textContent = `${time(row.start_frame)}–${time(row.end_frame)} · ${categoryName($('#category').value)}`;
    $('#selectionMeta').textContent = `原片 ${time(row.source_start_frame)}–${time(row.source_end_frame)}`;
    $('#note').value = notes[row.key]?.text || '';
    $('#mark').textContent = notes[row.key]?.checked ? '取消已检查 ✓' : '标记已检查';
    $('#checkpoints').replaceChildren();
    for (const frame of ReviewTimeline.checkpoints(data, row)) {
      const button = document.createElement('button'); button.textContent = time(frame);
      button.onclick = () => seek(frame); $('#checkpoints').append(button);
    }
    if (doSeek) seek(row.start_frame);
    render();
  }
  function move(direction) {
    if (!filtered.length) return;
    const index = filtered.findIndex(r => r.key === selected?.key), frame = currentFrame();
    let target;
    if (index >= 0) target = Math.max(0, Math.min(filtered.length - 1, index + direction));
    else if (direction > 0) {target = filtered.findIndex(r => r.start_frame > frame); if (target < 0) target = filtered.length - 1;}
    else {target = 0; filtered.forEach((r, i) => {if (r.start_frame < frame) target = i;});}
    page = Math.floor(target / pageSize); select(filtered[target]); $('#list').scrollTop = 0;
  }
  function jump() {
    const value = $('#jump').value.trim(), match = value.match(/^(?:(\d+):)?(\d+)(?:\.(\d+))?$/);
    if (!match || (match[1] !== undefined && Number(match[2]) >= 60)) {$('#error').textContent = '请输入有效的分:秒或秒数'; return;}
    const seconds = Number(match[1] || 0) * 60 + Number(match[2]) + Number('0.' + (match[3] || '0'));
    let frame = Math.round(seconds * fps), deleted = false;
    if ($('#basis').value === 'source') {
      const mapped = ReviewTimeline.sourceToOutput(data, frame);
      if (!mapped) {$('#error').textContent = '该时间未提供原片到成片映射'; return;}
      frame = mapped.frame; deleted = mapped.deleted;
    }
    if (frame < 0 || frame >= data.output_frames) {$('#error').textContent = '时间超出视频范围'; return;}
    $('#error').textContent = deleted ? '该原片时间已剪掉，定位到最近剪切接缝' : '';
    seekReviewFrame(frame);
  }
  function seekReviewFrame(frame) {
    frame = Math.max(0, Math.min(data.output_frames - 1, frame));
    seek(frame);
    syncSelection(frame);
  }
  function syncSelection(frame) {
    const row = ReviewTimeline.intervalAtFrame(filtered, frame);
    if (row) {
      page = Math.floor(filtered.indexOf(row) / pageSize);
      select(row, false);
    } else {
      save(false); selected = null;
      $('#selection').textContent = '当前筛选未包含此时间';
      $('#selectionMeta').textContent = '';
      $('#note').value = ''; $('#mark').textContent = '标记已检查';
      $('#checkpoints').replaceChildren(); render();
    }
  }
  $('#search').oninput = () => {page = 0; render();};
  $('#category').onchange = () => {save(false); selected = null; $('#note').value = ''; $('#selection').textContent = '请选择打码区间'; $('#selectionMeta').textContent = ''; $('#checkpoints').replaceChildren(); page = 0; render();};
  $('#pagePrev').onclick = () => {page--; render(); $('#list').scrollTop = 0;};
  $('#pageNext').onclick = () => {page++; render(); $('#list').scrollTop = 0;};
  $('#prev').onclick = () => move(-1); $('#next').onclick = () => move(1);
  $('#play').onclick = () => video.paused ? video.play().catch(e => {$('#error').textContent = e.message;}) : video.pause();
  document.querySelectorAll('[data-frame]').forEach(button => {button.onclick = () => {video.pause(); seekReviewFrame(currentFrame() + Number(button.dataset.frame));};});
  $('#speed').onchange = () => {video.playbackRate = Number($('#speed').value);};
  $('#scrubber').oninput = () => seekReviewFrame(Number($('#scrubber').value));
  $('#first').onclick = () => seekReviewFrame(0); $('#middle').onclick = () => seekReviewFrame(Math.floor(data.output_frames / 2)); $('#last').onclick = () => seekReviewFrame(data.output_frames - 1);
  $('#jumpBtn').onclick = jump; $('#jump').onkeydown = e => {if (e.key === 'Enter') jump();};
  $('#save').onclick = () => {save(); render();}; $('#note').onblur = () => save(false);
  $('#mark').onclick = () => {if (!selected) return; save(false); notes[selected.key] = {...(notes[selected.key] || {}), checked: !notes[selected.key]?.checked}; save(); select(selected, false);};
  $('#export').onclick = () => {
    save(false);
    const rows = [...ReviewTimeline.categoryIntervals(data), ...categories.flatMap(c => ReviewTimeline.categoryIntervals(data, c))];
    const records = rows.filter(r => notes[r.key]).map(r => ({...r, ...notes[r.key]}));
    const blob = new Blob([JSON.stringify({schema_version: 1, encoded_sha256: data.encoded_sha256,
      fps: data.fps, exported_at: new Date().toISOString(), records}, null, 2)], {type: 'application/json'});
    const anchor = document.createElement('a'); anchor.href = URL.createObjectURL(blob); anchor.download = 'record-freely-review.json'; anchor.click();
    setTimeout(() => URL.revokeObjectURL(anchor.href), 2000);
  };
  function enforceLoop() {
    if ($('#loop').checked && selected && !video.paused && !video.seeking) {
      const target = ReviewTimeline.loopTarget(data, video.currentTime, selected);
      if (target !== null) seek(target);
    }
  }
  video.addEventListener('timeupdate', () => {enforceLoop(); updateClock();});
  video.addEventListener('ended', () => {
    // At EOF Chromium pauses before timeupdate, so the live-clock guard cannot wrap.
    if ($('#loop').checked && selected) {
      seek(selected.start_frame);
      video.play().catch(error => {$('#error').textContent = error.message;});
    }
  });
  if (video.requestVideoFrameCallback) {
    const callback = () => {enforceLoop(); updateClock(); video.requestVideoFrameCallback(callback);};
    video.requestVideoFrameCallback(callback);
  }
  function verifyMetadata() {
    if (Number.isFinite(video.duration) && Math.abs(video.duration - data.output_frames / fps) > Math.max(0.1, 2 / fps)) $('#error').textContent = '视频时长与时间轴不同，请核对 CFR 帧数及版本';
    updateClock();
  }
  video.addEventListener('loadedmetadata', verifyMetadata); video.addEventListener('seeked', () => {updateClock(); syncSelection(currentFrame());});
  video.onerror = () => {$('#error').textContent = '视频加载失败。请检查浏览器是否支持此编码以及查看器进程是否仍在运行。';};
  if (video.readyState >= 1) verifyMetadata();
  window.addEventListener('keydown', e => {
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) return;
    const actions = {' ': () => $('#play').click(), ArrowUp: () => move(-1), ArrowDown: () => move(1),
      ArrowLeft: () => seekReviewFrame(currentFrame() - Math.round(fps * 5)), ArrowRight: () => seekReviewFrame(currentFrame() + Math.round(fps * 5)),
      ',': () => {video.pause(); seekReviewFrame(currentFrame() - 1);}, '.': () => {video.pause(); seekReviewFrame(currentFrame() + 1);}};
    if (actions[e.key]) {e.preventDefault(); actions[e.key]();}
  });
  window.addEventListener('beforeunload', () => save(false));
  render(); if (filtered.length) select(filtered[0], false);
}
