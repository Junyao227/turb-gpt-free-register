const DEFAULT_LANGUAGE = "pt-BR";
const LANGUAGE_STORAGE_KEY = "opll.qr.language";

let currentLanguage = DEFAULT_LANGUAGE;

const translations = {
  "pt-BR": {
    pageTitle: "Fila de QR PIX",
    pageHintLine1: "Abaixo estao os pedidos disponiveis para pagamento.",
    pageHintLine2: "Use o aplicativo do seu banco para escanear o QR Code abaixo e concluir o pagamento. Se nao conseguir escanear, abra a pagina de pagamento Stripe abaixo.",
    pageHintLine3: "Apos o pagamento, o pedido desaparecera automaticamente desta pagina em ate 30 segundos, sem necessidade de confirmacao manual.",
    refresh: "Atualizar fila",
    logout: "Sair",
    statusLoading: "Carregando fila...",
    statusInvalidJson: "A resposta não é um JSON válido",
    statusSessionExpired: "Sua sessão expirou",
    statusOpenLinkMissing: "Link de pagamento indisponível.",
    statusQueueRefreshing: ({ count }) => `${count} pedidos na fila. Atualizando...`,
    statusQueueReady: ({ count }) => `${count} pedidos na fila.`,
    statusQueueLoadFailed: ({ status }) => `Falha ao carregar fila (${status})`,
    emptyQueue: "Nenhum QR PIX pendente no momento.",
    orderLabel: "Pedido",
    cardFallbackTitle: "Sessão PIX",
    cardNoQrImage: "Imagem do QR indisponível",
    openPaymentLink: "Nao consegue escanear? Abrir pagina de pagamento Stripe",
    stateLabels: {
      pending: "pendente",
      succeeded: "concluído",
      failed: "falhou",
      expired: "expirado",
      canceled: "cancelado",
      unknown: "desconhecido",
    },
  },
  "zh-CN": {
    pageTitle: "PIX 二维码队列",
    pageHintLine1: "以下是可支付的订单。",
    pageHintLine2: "请使用您的银行 App 扫描下方二维码完成支付；如无法扫码，可打开下方 Stripe 支付页面继续支付。",
    pageHintLine3: "支付后，订单将在最多 30 秒内自动从本页面消失，无需手动确认。",
    refresh: "刷新队列",
    logout: "退出",
    statusLoading: "正在加载队列...",
    statusInvalidJson: "响应不是有效 JSON",
    statusSessionExpired: "登录已失效",
    statusOpenLinkMissing: "支付链接不可用。",
    statusQueueRefreshing: ({ count }) => `当前 ${count} 个订单，正在刷新...`,
    statusQueueReady: ({ count }) => `当前 ${count} 个订单。`,
    statusQueueLoadFailed: ({ status }) => `队列加载失败 (${status})`,
    emptyQueue: "当前没有待支付的 PIX 二维码。",
    orderLabel: "订单",
    cardFallbackTitle: "PIX 会话",
    cardNoQrImage: "暂无二维码图片",
    openPaymentLink: "无法扫码？打开 Stripe 支付页面",
    stateLabels: {
      pending: "待支付",
      succeeded: "支付成功",
      failed: "失败",
      expired: "过期",
      canceled: "已取消",
      unknown: "未知",
    },
  },
};

function getTranslations(language = currentLanguage) {
  return translations[language] || translations[DEFAULT_LANGUAGE];
}

function translate(key, params) {
  const value = getTranslations()[key];
  if (typeof value === "function") return value(params || {});
  return value || "";
}

function translateState(state) {
  const normalized = String(state || "unknown").toLowerCase();
  const labels = getTranslations().stateLabels || {};
  return labels[normalized] || normalized;
}

function setStatus(text) {
  $("status").textContent = text;
}

function setLocalizedStatus(key, params) {
  setStatus(translate(key, params));
}

function applyLanguage() {
  const language = getTranslations();
  document.documentElement.lang = currentLanguage;
  document.title = language.pageTitle;
  $("pageTitle").textContent = language.pageTitle;
  $("pageHintLine1").textContent = language.pageHintLine1;
  $("pageHintLine2").textContent = language.pageHintLine2;
  $("pageHintLine3").textContent = language.pageHintLine3;
  $("refresh").textContent = language.refresh;
  $("logout").textContent = language.logout;
  $("langPt").classList.toggle("active", currentLanguage === "pt-BR");
  $("langZh").classList.toggle("active", currentLanguage === "zh-CN");
}

function persistLanguage(language) {
  try {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
  } catch (_) {}
}

function switchLanguage(language) {
  if (!translations[language]) return;
  currentLanguage = language;
  persistLanguage(language);
  applyLanguage();
  applyQueue(window.latestRenderableItems || []);
}

function loadInitialLanguage() {
  try {
    const stored = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (stored && translations[stored]) currentLanguage = stored;
  } catch (_) {}
}
