const $ = (id) => document.getElementById(id);
let currentJobId = '';
let autoScroll = true;
let pollTimer = 0;

function formatTime(value) {
  const n = Number(value || 0);
  if (!Number.isFinite(n) || n <= 0) return '-';
  return new Date(n * 1000).toLocaleString();
}

function renderLines(rows) {
  $("cliOutput").textContent = rows.map((item) => `[${formatTime(item.ts || 0)}] ${item.kind || '-'} ${item.status || '-'} ${item.cs_id || '-'} ${item.job_id || '-'} ${item.message || '-'}`).join('\n');
  if (autoScroll) $("cliOutput").scrollTop = $("cliOutput").scrollHeight;
}

async function loadLogs() {
  if (!currentJobId) return;
  const response = await fetch(`/api/upi/tasks/logs?job_id=${encodeURIComponent(currentJobId)}&limit=300`);
  const data = await response.json();
  const task = data.task && typeof data.task === 'object' ? data.task : {};
  $("cliMeta").textContent = `${task.text || '-'} / ${formatTime(task.updated_at || 0)} / ${currentJobId}`;
  renderLines(Array.isArray(data.items) ? data.items : []);
}

function bind() {
  $("loadJobLogs").addEventListener('click', () => {
    currentJobId = $("jobIdInput").value.trim();
    clearInterval(pollTimer);
    loadLogs().catch(() => {});
    if (currentJobId) pollTimer = setInterval(() => loadLogs().catch(() => {}), 1200);
  });
  $("refreshLogs").addEventListener('click', () => loadLogs().catch(() => {}));
  $("toggleAutoscroll").addEventListener('click', () => {
    autoScroll = !autoScroll;
    $("toggleAutoscroll").textContent = autoScroll ? '暂停滚动' : '恢复滚动';
  });
}

bind();
