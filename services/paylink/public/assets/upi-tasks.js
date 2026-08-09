const $ = (id) => document.getElementById(id);
let currentJobId = '';
let pollTimer = 0;
let autoScroll = true;

function isFailed(item) {
  return String(item.status || '').toLowerCase() === 'failed' || Boolean(item.error);
}

function formatTime(value) {
  const n = Number(value || 0);
  if (!Number.isFinite(n) || n <= 0) return '-';
  return new Date(n * 1000).toLocaleString();
}

function renderSummary(summary) {
  $("sumRunning").textContent = String(summary.running || 0);
  $("sumDone").textContent = String(summary.done || 0);
  $("sumFailed").textContent = String(summary.failed || 0);
  $("sumTotal").textContent = String(summary.total || 0);
}

function renderTable(items) {
  const upiItems = items.filter((item) => {
    const result = item.result && typeof item.result === 'object' ? item.result : {};
    return String(result.link_type || '').trim() === 'upi';
  });
  if (!upiItems.length) {
    $("taskTableWrap").innerHTML = '<div class="upi-panel muted">当前没有任务记录</div>';
    return;
  }
  $("taskTableWrap").innerHTML = `<table class="upi-table"><thead><tr><th>状态</th><th>任务</th><th>账号</th><th>阶段</th><th>更新时间</th><th>结果</th><th>操作</th></tr></thead><tbody>${upiItems.map((item) => {
    const result = item.result && typeof item.result === 'object' ? item.result : {};
    const stateClass = item.error ? 'failed' : item.done ? 'success' : 'pending';
    const summary = [result.link_type || '', result.billing_country || '', result.currency || '', result.approval_result || '', result.submission_state || ''].filter(Boolean).join(' / ');
    return `<tr data-job-id="${item.job_id}"><td><span class="upi-badge ${stateClass}">${item.error ? 'failed' : item.done ? 'done' : 'running'}</span></td><td><div>${item.job_id}</div><code>${result.cs_id || '-'}</code></td><td>${result.claimed_account_email || '-'}</td><td>${item.percent || 0}% / ${item.text || '-'}</td><td>${formatTime(item.updated_at || 0)}</td><td>${summary || '-'}</td><td><a class="upi-button secondary" href="/upi/result?job_id=${encodeURIComponent(item.job_id)}">Result</a></td></tr>`;
  }).join('')}</tbody></table>`;
  document.querySelectorAll('[data-job-id]').forEach((row) => {
    row.addEventListener('click', () => openLogs(row.getAttribute('data-job-id') || ''));
  });
}

function appendLines(lines) {
  $("cliOutput").textContent = lines.join('\n');
  if (autoScroll) $("cliOutput").scrollTop = $("cliOutput").scrollHeight;
}

async function loadLogs(jobId) {
  const response = await fetch(`/api/upi/tasks/logs?job_id=${encodeURIComponent(jobId)}&limit=200`);
  const data = await response.json();
  const task = data.task && typeof data.task === 'object' ? data.task : {};
  $("cliTitle").textContent = `Task Logs · ${jobId}`;
  $("cliMeta").textContent = `${task.text || '-'} / ${formatTime(task.updated_at || 0)}`;
  const rows = Array.isArray(data.items) ? data.items : [];
  appendLines(rows.map((item) => `[${formatTime(item.ts || 0)}] ${item.kind || '-'} ${item.status || '-'} ${item.cs_id || '-'} ${item.job_id || '-'} ${item.message || '-'}`));
}

function openCli() {
  $("logModal").classList.remove('hidden');
  $("logModal").setAttribute('aria-hidden', 'false');
}

function closeCli() {
  $("logModal").classList.add('hidden');
  $("logModal").setAttribute('aria-hidden', 'true');
  clearInterval(pollTimer);
  pollTimer = 0;
}

async function openLogs(jobId) {
  currentJobId = jobId;
  openCli();
  await loadLogs(jobId);
  clearInterval(pollTimer);
  pollTimer = setInterval(() => loadLogs(jobId).catch(() => {}), 1200);
}

async function refreshTasks() {
  const response = await fetch('/api/upi/tasks?page=1&page_size=50');
  const data = await response.json();
  renderSummary({
    running: Number((data.summary || {}).running || 0),
    done: Number((data.summary || {}).done || 0),
    failed: Number((data.summary || {}).failed || 0),
    total: Number((data.summary || {}).total || 0),
  });
  renderTable(Array.isArray(data.items) ? data.items : []);
}

$("refreshTasks").addEventListener('click', () => refreshTasks().catch(() => {}));
$("refreshLogs").addEventListener('click', () => currentJobId && loadLogs(currentJobId).catch(() => {}));
$("closeCli").addEventListener('click', closeCli);
$("logModal").addEventListener('click', (event) => { if (event.target === $("logModal")) closeCli(); });
window.addEventListener('keydown', (event) => { if (event.key === 'Escape' && !$("logModal").classList.contains('hidden')) closeCli(); });
refreshTasks().catch(() => {});
