const $ = (id) => document.getElementById(id);
let currentRequestId = "";
let cliAbort = null;
let autoScroll = true;

function setGenerateStatus(text, state = "pending") {
  const node = $("generateStatus");
  node.textContent = text;
  node.className = `upi-status ${state === "failed" ? "failed" : state === "success" ? "success" : "muted"}`;
  $("resultBadge").textContent = state;
  $("resultBadge").className = `upi-badge ${state === "failed" ? "failed" : state === "success" ? "success" : "pending"}`;
}

function isHttpUrl(value) {
  return /^https?:\/\//i.test(String(value || "").trim());
}

function setArtifact(data) {
  const wrap = $("artifactViewport");
  const qrImage = String(data.upi_qr_image_url || data.provider_qr_url || "").trim();
  const qrData = String(data.upi_qr_data || "").trim();
  const redirectUrl = String(data.upi_redirect_url || "").trim();
  const hostedUrl = String(data.upi_hosted_url || "").trim();
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
  wrap.innerHTML = '<div class="muted">当前没有可显示结果</div>';
  return "";
}

function setMeta(data) {
  $("metaRequestId").textContent = data.request_id || "-";
  $("metaReason").textContent = data.reason || "-";
  $("metaRetryable").textContent = data.retryable == null ? "-" : String(data.retryable);
  $("metaActionType").textContent = data.next_action_type || "-";
}

function appendCliLine(line) {
  const out = $("cliOutput");
  out.textContent += `${line}\n`;
  if (autoScroll) out.scrollTop = out.scrollHeight;
}

function openCli() {
  $("logModal").classList.remove("hidden");
  $("logModal").setAttribute("aria-hidden", "false");
}

function closeCli() {
  $("logModal").classList.add("hidden");
  $("logModal").setAttribute("aria-hidden", "true");
  if (cliAbort) cliAbort.abort();
  cliAbort = null;
}

async function startStream() {
  if (cliAbort) cliAbort.abort();
  cliAbort = new AbortController();
  autoScroll = true;
  $("cliOutput").textContent = "";
  openCli();
  const body = {
    token: $("token").value.trim(),
    promoId: $("promoId").value.trim() || "plus-1-month-free",
    poolKeep: Number($("poolKeep").value || 10),
    poolMax: Number($("poolMax").value || 200),
  };
  const response = await fetch('/api/upi/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: cliAbort.signal,
  });
  if (!response.ok) {
    const text = await response.text();
    appendCliLine(text || `stream failed (${response.status})`);
    return;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split('\n\n');
    buffer = chunks.pop() || '';
    for (const chunk of chunks) {
      if (!chunk.trim()) continue;
      appendCliLine(chunk);
      const dataLine = chunk.split('\n').find((line) => line.startsWith('data: '));
      if (!dataLine) continue;
      try {
        const payload = JSON.parse(dataLine.slice(6));
        if (payload.request_id) {
          currentRequestId = payload.request_id;
          $("cliMeta").textContent = payload.request_id;
        }
        if (payload.ok === true || payload.ok === false) {
          setGenerateStatus(payload.ok ? '完成' : '失败', payload.ok ? 'success' : 'failed');
          const artifact = setArtifact(payload);
          setMeta(payload);
          $("openArtifact").href = artifact && isHttpUrl(artifact) ? artifact : '#';
          $("openArtifact").classList.toggle('disabled', !artifact || !isHttpUrl(artifact));
        }
      } catch (_) {}
    }
  }
}

async function submitGenerate() {
  setGenerateStatus('提交中', 'pending');
  const response = await fetch('/api/upi', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      token: $("token").value.trim(),
      promoId: $("promoId").value.trim() || 'plus-1-month-free',
      poolKeep: Number($("poolKeep").value || 10),
      poolMax: Number($("poolMax").value || 200),
    }),
  });
  const data = await response.json();
  setMeta(data);
  const artifact = setArtifact(data);
  $("openArtifact").href = artifact && isHttpUrl(artifact) ? artifact : '#';
  $("openArtifact").classList.toggle('disabled', !artifact || !isHttpUrl(artifact));
  setGenerateStatus(data.ok ? '完成' : '失败', data.ok ? 'success' : 'failed');
}

$("submitGenerate").addEventListener('click', () => submitGenerate().catch((error) => setGenerateStatus(String(error), 'failed')));
$("openLiveLogs").addEventListener('click', () => startStream().catch((error) => appendCliLine(String(error))));
$("closeCli").addEventListener('click', closeCli);
$("toggleAutoscroll").addEventListener('click', () => { autoScroll = !autoScroll; $("toggleAutoscroll").textContent = autoScroll ? '暂停滚动' : '恢复滚动'; });
$("copyArtifact").addEventListener('click', async () => { const text = $("artifactViewport").textContent || $("openArtifact").href || ''; if (text) await navigator.clipboard.writeText(text); });
$("logModal").addEventListener('click', (event) => { if (event.target === $("logModal")) closeCli(); });
window.addEventListener('keydown', (event) => { if (event.key === 'Escape' && !$("logModal").classList.contains('hidden')) closeCli(); });
