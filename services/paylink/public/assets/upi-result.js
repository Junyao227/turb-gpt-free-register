const $ = (id) => document.getElementById(id);

function queryParam(name) {
  return new URLSearchParams(window.location.search).get(name) || '';
}

function isHttpUrl(value) {
  return /^https?:\/\//i.test(String(value || '').trim());
}

function setArtifact(data) {
  const wrap = $("artifactViewport");
  const qrSvg = String(data.provider_qr_svg || '').trim();
  const qrImage = String(data.upi_qr_image_url || data.provider_qr_url || '').trim();
  const qrData = String(data.upi_qr_data || '').trim();
  const redirectUrl = String(data.upi_redirect_url || data.provider_redirect_url || '').trim();
  const hostedUrl = String(data.upi_hosted_url || data.long_url || '').trim();
  if (qrSvg) {
    wrap.innerHTML = qrSvg;
    return qrData || qrImage || hostedUrl || redirectUrl;
  }
  if (qrImage && isHttpUrl(qrImage)) {
    wrap.innerHTML = `<img src="${qrImage}" alt="UPI QR" loading="lazy" referrerpolicy="no-referrer" />`;
    return qrImage;
  }
  if (qrData) {
    wrap.innerHTML = `<code>${qrData}</code>`;
    return qrData;
  }
  if (redirectUrl || hostedUrl) {
    wrap.innerHTML = `<code>${redirectUrl || hostedUrl}</code>`;
    return redirectUrl || hostedUrl;
  }
  wrap.innerHTML = '<div class="muted">当前没有可显示产物</div>';
  return '';
}

function setMeta(task, result) {
  const reason = String(result.reason || '').trim() || (task.error ? task.text || '-' : 'ok');
  $("metaJobId").textContent = task.job_id || '-';
  $("metaCsId").textContent = result.cs_id || '-';
  $("metaReason").textContent = reason;
  $("metaRetryable").textContent = result.retryable == null ? '-' : String(result.retryable);
  $("metaApproval").textContent = result.approval_result || '-';
  $("metaSubmission").textContent = result.submission_state || '-';
  $("metaActionType").textContent = result.next_action_type || '-';
  $("metaSummary").textContent = [result.link_type || '-', result.billing_country || '-', result.currency || '-'].join(' / ');
  $("resultState").textContent = task.text || '-';
  $("resultBadge").textContent = task.error ? 'failed' : task.done ? 'done' : 'running';
  $("resultBadge").className = `upi-badge ${task.error ? 'failed' : task.done ? 'success' : 'pending'}`;
}

async function loadResult() {
  const jobId = queryParam('job_id');
  if (!jobId) {
    $("resultState").textContent = '缺少 job_id';
    return;
  }
  $("openLogsLink").href = `/upi/logs?job_id=${encodeURIComponent(jobId)}`;
  const taskResp = await fetch(`/api/upi/tasks/logs?job_id=${encodeURIComponent(jobId)}&limit=120`);
  const taskData = await taskResp.json();
  const task = taskData.task && typeof taskData.task === 'object' ? taskData.task : {};
  const result = task.result && typeof task.result === 'object' ? task.result : {};
  const artifact = setArtifact(result);
  setMeta(task, result);
  $("openArtifact").href = artifact && isHttpUrl(artifact) ? artifact : '#';
  $("openArtifact").classList.toggle('disabled', !artifact || !isHttpUrl(artifact));
  const rows = Array.isArray(taskData.items) ? taskData.items : [];
  $("protocolSummary").textContent = rows.map((item) => `[${new Date(Number(item.ts || 0) * 1000).toLocaleString()}] ${item.kind || '-'} ${item.status || '-'} ${item.cs_id || '-'} ${item.message || '-'}`).join('\n');
}

$("copyArtifact").addEventListener('click', async () => {
  const text = $("artifactViewport").textContent || $("openArtifact").href || '';
  if (text) await navigator.clipboard.writeText(text);
});
loadResult().catch((error) => { $("resultState").textContent = String(error); });
