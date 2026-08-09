const $ = (id) => document.getElementById(id);
const PAGE_SCOPE = "qr";
const PROVIDER_PAGE = document.body.dataset.providerPage || "generic";
const LINK_TYPE =
  PROVIDER_PAGE === "korea"
    ? "korea"
    : PROVIDER_PAGE === "swiss" || PROVIDER_PAGE === "twint"
      ? "swiss"
      : PROVIDER_PAGE === "upi"
        ? "upi"
        : PROVIDER_PAGE === "ideal"
          ? "ideal"
          : PROVIDER_PAGE === "gcash"
            ? "gcash"
          : PROVIDER_PAGE === "gopay"
          ? "gopay"
          : "";
const REFRESH_INTERVAL_MS = 30000;

let refreshTimer = 0;

function redirectToLogin(scope = PAGE_SCOPE) {
  const next = encodeURIComponent(window.location.pathname || "/");
  window.location.href = `/login?scope=${encodeURIComponent(scope)}&next=${next}`;
}

async function readJsonResponse(response) {
  const text = await response.text();
  try {
    return text ? JSON.parse(text) : {};
  } catch (_) {
    return { detail: text || "响应不是有效 JSON" };
  }
}

async function apiFetch(url, options = {}, scope = PAGE_SCOPE) {
  const response = await fetch(url, {
    cache: "no-store",
    ...options,
  });
  if (response.status === 401) {
    redirectToLogin(scope);
    throw new Error("登录已失效");
  }
  return response;
}

function resolveTitle() {
  if (PROVIDER_PAGE === "twint") return "Twint 支付队列";
  if (LINK_TYPE === "korea") return "韩国 KakaoPay 队列";
  if (LINK_TYPE === "swiss") return "瑞士支付队列";
  if (LINK_TYPE === "upi") return "OPLL-UPI · IN-QR";
  if (LINK_TYPE === "ideal") return "荷兰 iDEAL 队列";
  if (LINK_TYPE === "gcash") return "菲律宾 GCash 队列";
  if (LINK_TYPE === "gopay") return "印度尼西亚 GoPay 队列";
  return "Provider 支付队列";
}

function resolveOpenLabel() {
  if (PROVIDER_PAGE === "twint") return "Open Twint payment page";
  if (LINK_TYPE === "korea") return "Open KakaoPay page";
  if (LINK_TYPE === "swiss") return "Open Swiss payment page";
  if (LINK_TYPE === "upi") return "Open UPI payment page";
  if (LINK_TYPE === "ideal") return "Open iDEAL payment page";
  if (LINK_TYPE === "gcash") return "Open GCash payment page";
  if (LINK_TYPE === "gopay") return "Open GoPay payment page";
  return "Open payment page";
}

function resolveLink(item) {
  return String(item.providerRedirectUrl || item.paymentPageUrl || item.longUrl || "").trim();
}

function isHttpUrl(value) {
  return /^https?:\/\//i.test(String(value || "").trim());
}

function formatExpiresAt(value) {
  const n = Number(value || 0);
  if (!Number.isFinite(n) || n <= 0) return "";
  return new Date(n * 1000).toLocaleString();
}

function setStatus(text) {
  $("status").textContent = text;
}

function renderQueue(items) {
  const root = $("queue");
  root.innerHTML = "";
  if (!items.length) {
    root.innerHTML = '<div class="empty">当前没有待处理支付会话。</div>';
    return;
  }

  for (const [index, item] of items.entries()) {
    const card = document.createElement("section");
    card.className = "card";
    const link = resolveLink(item);
    const state = String(item.state || "pending");
    const expiredAt = Number(item.expiredAt || 0);
    const iframeHtml = link
      ? `<div class="qr-wrap provider-frame-wrap"><iframe src="${link}" loading="lazy" referrerpolicy="no-referrer" style="width:100%;height:520px;border:0;border-radius:12px;background:#fff;"></iframe></div>`
      : `<div class="qr-wrap"><div class="muted">No payment page URL.</div></div>`;
    card.innerHTML = `
      <div class="card-head">
        <div class="card-title">订单 #${index + 1}<br>${String(item.csId || "")}</div>
        <span class="badge ${state}">${state}</span>
      </div>
      ${iframeHtml}
      <div class="meta">
        <div class="meta-row"><div class="meta-label">支付方式</div><code>${String(item.paymentMethodType || "")}</code></div>
        ${expiredAt ? `<div class="meta-row"><div class="meta-label">过期时间</div><code>${formatExpiresAt(expiredAt)}</code></div>` : ""}
        ${String(item.iosAppUrl || "").trim() ? `<div class="meta-row"><div class="meta-label">iOS 拉起</div><code>${String(item.iosAppUrl || "").trim()}</code></div>` : ""}
        ${String(item.aosAppUrl || "").trim() ? `<div class="meta-row"><div class="meta-label">Android 拉起</div><code>${String(item.aosAppUrl || "").trim()}</code></div>` : ""}
        <div class="meta-row"><div class="meta-label">Provider URL</div><code>${link || ""}</code></div>
      </div>
      <div class="card-actions">
        <a class="payment-help-link" href="${link || "#"}" target="_blank" rel="noopener noreferrer">${resolveOpenLabel()}</a>
        <button class="secondary" type="button" data-delete="${String(item.csId || "")}">删除</button>
      </div>
    `;
    const anchor = card.querySelector("a");
    if (!link) {
      anchor.addEventListener("click", (event) => {
        event.preventDefault();
        setStatus("No payment page URL.");
      });
    }
    const deleteButton = card.querySelector("button[data-delete]");
    deleteButton.addEventListener("click", async () => {
      try {
        const response = await apiFetch(
          `/api/provider/delete?link_type=${encodeURIComponent(LINK_TYPE)}&cs_id=${encodeURIComponent(String(item.csId || ""))}`,
          { method: "POST" },
        );
        const data = await readJsonResponse(response);
        if (!response.ok) {
          throw new Error(data.detail || `删除失败 (${response.status})`);
        }
        await loadQueue();
      } catch (error) {
        setStatus(error instanceof Error ? error.message : String(error));
      }
    });
    root.appendChild(card);
  }
}

async function loadQueue() {
  setStatus(`正在加载${resolveTitle()}...`);
  try {
    const endpoint = LINK_TYPE === "upi"
      ? "/api/upi/queue?limit=200"
      : `/api/provider/pending?link_type=${encodeURIComponent(LINK_TYPE)}&limit=200`;
    const response = await apiFetch(endpoint);
    const data = await readJsonResponse(response);
    if (!response.ok) {
      throw new Error(data.detail || `队列加载失败 (${response.status})`);
    }
    const items = Array.isArray(data.items) ? data.items : [];
    renderQueue(items);
    setStatus(`当前 ${items.length} 个支付会话。`);
  } catch (error) {
    setStatus(error instanceof Error ? error.message : String(error));
  }
}

async function clearTerminal() {
  try {
    const response = await apiFetch(`/api/provider/clear-terminal?link_type=${encodeURIComponent(LINK_TYPE)}`, {
      method: "POST",
    });
    const data = await readJsonResponse(response);
    if (!response.ok) {
      throw new Error(data.detail || `清理失败 (${response.status})`);
    }
    await loadQueue();
  } catch (error) {
    setStatus(error instanceof Error ? error.message : String(error));
  }
}

function bindActions() {
  $("refresh").addEventListener("click", loadQueue);
  $("clearTerminal").addEventListener("click", clearTerminal);
  $("logout").addEventListener("click", async () => {
    try {
      await apiFetch("/api/auth/logout", { method: "POST" });
    } catch (_) {}
    redirectToLogin(PAGE_SCOPE);
  });
}

function init() {
  document.title = resolveTitle();
  $("pageTitle").textContent = resolveTitle();
  bindActions();
  loadQueue();
  refreshTimer = window.setInterval(loadQueue, REFRESH_INTERVAL_MS);
}

init();
