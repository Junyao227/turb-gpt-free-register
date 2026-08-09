const $ = (id) => document.getElementById(id);
const PAGE_SCOPE = "qr";
const STATUS_TERMINAL_STATES = ["failed", "expired", "canceled"];
const TERMINAL_STATES = ["succeeded", ...STATUS_TERMINAL_STATES];
const QR_REFRESH_INTERVAL_MS = 30000;
const CARD_REMOVE_DELAY_MS = 180;

let refreshTimer = 0;
let latestRenderableItems = [];
let loadSequence = 0;
let activeLoadSequence = 0;
const cardNodes = new Map();
window.latestRenderableItems = latestRenderableItems;

function redirectToLogin(scope = PAGE_SCOPE) {
  const next = encodeURIComponent(window.location.pathname || "/qr");
  window.location.href = `/login?scope=${encodeURIComponent(scope)}&next=${next}`;
}

async function readJsonResponse(response) {
  const text = await response.text();
  try {
    return text ? JSON.parse(text) : {};
  } catch (_) {
    return { detail: text || translate("statusInvalidJson") };
  }
}

async function apiFetch(url, options = {}, scope = PAGE_SCOPE) {
  const response = await fetch(url, {
    cache: "no-store",
    ...options,
  });
  if (response.status === 401) {
    redirectToLogin(scope);
    throw new Error(translate("statusSessionExpired"));
  }
  return response;
}

function formatTime(value) {
  const n = Number(value || 0);
  if (!Number.isFinite(n) || n <= 0) return "";
  return new Date(n * 1000).toLocaleString();
}

function badgeClass(state) {
  const normalized = String(state || "").toLowerCase();
  if (TERMINAL_STATES.includes(normalized)) return `badge ${normalized}`;
  return "badge";
}

function hasRenderableQr(item) {
  return Boolean(item && (item.pixQrImageUrlPng || item.pixQrCode));
}

function resolvePaymentLink(item) {
  if (!item || typeof item !== "object") return "";
  return String(item.paymentPageUrl || "").trim();
}

function createCardElements(item, index) {
  const state = String(item.state || "pending");
  const isSucceeded = state === "succeeded";
  const paymentLink = resolvePaymentLink(item);
  const card = document.createElement("section");
  card.className = "card";
  card.dataset.csId = String(item.csId || "");

  const head = document.createElement("div");
  head.className = "card-head";

  const title = document.createElement("div");
  title.className = "card-title";

  const badge = document.createElement("span");

  const qrWrap = document.createElement("div");
  qrWrap.className = "qr-wrap";

  if (item.pixQrImageUrlPng) {
    const image = document.createElement("img");
    image.src = item.pixQrImageUrlPng;
    image.alt = "PIX QR";
    qrWrap.appendChild(image);
  } else {
    const empty = document.createElement("div");
    empty.className = "muted";
    empty.textContent = translate("cardNoQrImage");
    qrWrap.appendChild(empty);
  }

  const actions = document.createElement("div");
  actions.className = "card-actions";

  const paymentLinkElement = document.createElement("a");
  paymentLinkElement.className = "payment-help-link";
  paymentLinkElement.target = "_blank";
  paymentLinkElement.rel = "noopener noreferrer";
  paymentLinkElement.dataset.openLink = paymentLink ? "1" : "0";
  paymentLinkElement.href = paymentLink || "#";

  head.appendChild(title);
  head.appendChild(badge);
  actions.appendChild(paymentLinkElement);
  card.appendChild(head);
  card.appendChild(qrWrap);
  card.appendChild(actions);

  updateCardElements(card, item, index, isSucceeded);
  bindCardActions(card);
  return card;
}

function ensureSuccessOverlay(qrWrap, isSucceeded) {
  const existing = qrWrap.querySelector(".qr-success");
  if (!isSucceeded) {
    if (existing) existing.remove();
    return;
  }
  if (existing) return;
  const overlay = document.createElement("div");
  overlay.className = "qr-success";
  const mark = document.createElement("div");
  mark.className = "qr-success-mark";
  mark.textContent = "✓";
  overlay.appendChild(mark);
  qrWrap.appendChild(overlay);
}

function updateCardElements(card, item, index, isSucceededOverride) {
  const state = String(item.state || "pending");
  const isSucceeded = typeof isSucceededOverride === "boolean" ? isSucceededOverride : state === "succeeded";
  const title = card.querySelector(".card-title");
  const badge = card.querySelector(".card-head span");
  const qrWrap = card.querySelector(".qr-wrap");
  const paymentLink = card.querySelector(".payment-help-link");

  title.textContent = `${translate("orderLabel")} #${index + 1}`;
  badge.className = badgeClass(state);
  badge.textContent = translateState(state);
  ensureSuccessOverlay(qrWrap, isSucceeded);
  paymentLink.textContent = translate("openPaymentLink");
  const nextLink = resolvePaymentLink(item);
  paymentLink.dataset.openLink = nextLink ? "1" : "0";
  paymentLink.href = nextLink || "#";
}

function bindCardActions(card) {
  card.querySelectorAll("a[data-open-link]").forEach((link) => {
    link.addEventListener("click", (event) => {
      const enabled = link.getAttribute("data-open-link") === "1";
      if (enabled) return;
      event.preventDefault();
      setLocalizedStatus("statusOpenLinkMissing");
    });
  });
}

function removeCard(csId) {
  const card = cardNodes.get(csId);
  if (!card) return;
  card.classList.add("removing");
  window.setTimeout(() => {
    if (card.parentNode) card.parentNode.removeChild(card);
  }, CARD_REMOVE_DELAY_MS);
  cardNodes.delete(csId);
}

function upsertCard(item, index) {
  const csId = String(item.csId || "");
  if (!csId) return;
  const existing = cardNodes.get(csId);
  if (!existing) {
    const card = createCardElements(item, index);
    cardNodes.set(csId, card);
    $("queue").appendChild(card);
    return;
  }
  updateCardElements(existing, item, index);
}

function applyQueue(items) {
  const root = $("queue");
  const rows = Array.isArray(items) ? items.filter(hasRenderableQr) : [];
  latestRenderableItems = rows;
  window.latestRenderableItems = rows;
  const nextIds = new Set(rows.map((item) => String(item.csId || "")).filter(Boolean));
  if (!rows.length) {
    for (const csId of Array.from(cardNodes.keys())) removeCard(csId);
    root.innerHTML = `<div class="empty">${translate("emptyQueue")}</div>`;
    return;
  }
  const empty = root.querySelector(".empty");
  if (empty) empty.remove();
  rows.forEach((item, index) => upsertCard(item, index));
  for (const csId of Array.from(cardNodes.keys())) {
    if (!nextIds.has(csId)) removeCard(csId);
  }
}

async function loadQueue() {
  const sequence = loadSequence + 1;
  loadSequence = sequence;
  activeLoadSequence = sequence;
  setLocalizedStatus("statusLoading");
  try {
    const response = await apiFetch("/api/pix/pending?limit=200");
    const data = await readJsonResponse(response);
    if (!response.ok) {
      throw new Error(data.detail || translate("statusQueueLoadFailed", { status: response.status }));
    }

    const items = Array.isArray(data.items) ? data.items.filter(hasRenderableQr) : [];
    if (activeLoadSequence !== sequence) return;
    applyQueue(items);
    setLocalizedStatus("statusQueueRefreshing", { count: items.length });
    setLocalizedStatus("statusQueueReady", { count: items.length });
  } catch (error) {
    setStatus(error instanceof Error ? error.message : String(error));
  }
}

function startAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(loadQueue, QR_REFRESH_INTERVAL_MS);
}

function bindPageActions() {
  $("refresh").addEventListener("click", loadQueue);

  $("logout").addEventListener("click", async () => {
    try {
      await apiFetch("/api/auth/logout", { method: "POST" });
    } catch (_) {}
    redirectToLogin(PAGE_SCOPE);
  });

  $("langPt").addEventListener("click", () => switchLanguage("pt-BR"));
  $("langZh").addEventListener("click", () => switchLanguage("zh-CN"));
}

function initPage() {
  loadInitialLanguage();
  applyLanguage();
  bindPageActions();
  loadQueue();
  startAutoRefresh();
}

initPage();
