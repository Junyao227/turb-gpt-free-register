(() => {
  "use strict";

  const PUBLIC_TYPE_ALIASES = {
    korea: "kakao_pay",
    swiss: "twint",
  };
  const LEGACY_PROVIDER_BY_PATH = {
    "/qr": "pix",
    "/upi": "upi",
    "/upi/tasks": "upi",
    "/upi/logs": "upi",
    "/upi/result": "upi",
    "/in-qr": "upi",
    "/kr-qr": "kakao_pay",
    "/ch-qr": "twint",
    "/nl-qr": "ideal",
    "/ph-qr": "gcash",
  };
  const GLOBAL_ITEMS = [
    ["generate", "生成中心"],
    ["tasks", "任务中心"],
    ["queues", "支付队列"],
    ["debug", "调试工具"],
    ["stats", "运行统计"],
    ["settings", "配置"],
  ];

  const state = {
    providers: [],
    activeProvider: "pix",
    activeSection: "generate",
    shell: null,
  };

  function normalizePublicType(value) {
    const normalized = String(value || "").trim().toLowerCase();
    return PUBLIC_TYPE_ALIASES[normalized] || normalized;
  }

  function sectionFromLocation() {
    const path = window.location.pathname;
    if (path === "/debug-generate") return "debug";
    if (path === "/stats") return "stats";
    if (path === "/settings") return "settings";
    if (["/qr", "/kr-qr", "/ch-qr", "/in-qr", "/nl-qr", "/ph-qr", "/id-qr"].includes(path)) return "queues";
    const requestedView = new URLSearchParams(window.location.search).get("view");
    if ((path === "/" && requestedView === "tasks") || window.location.hash === "#tasks") return "tasks";
    if (["/upi/tasks", "/upi/logs", "/upi/result"].includes(path)) return "tasks";
    return "generate";
  }

  function providerFromLocation() {
    const queryProvider = new URLSearchParams(window.location.search).get("provider");
    if (queryProvider) return normalizePublicType(queryProvider);
    const bodyProvider = document.body ? document.body.dataset.providerPage : "";
    if (bodyProvider) return normalizePublicType(bodyProvider);
    return LEGACY_PROVIDER_BY_PATH[window.location.pathname] || "pix";
  }

  function currentProvider() {
    return state.providers.find((provider) => provider.public_type === state.activeProvider) || state.providers[0] || null;
  }

  function targetFor(section, provider) {
    const publicType = encodeURIComponent(provider ? provider.public_type : state.activeProvider || "pix");
    if (section === "tasks") return `/?provider=${publicType}&view=tasks`;
    if (section === "queues") return provider && provider.queue_path ? provider.queue_path : "/qr";
    if (section === "debug") return `/debug-generate?provider=${publicType}`;
    if (section === "stats") return `/stats?provider=${publicType}`;
    if (section === "settings") return `/settings?provider=${publicType}`;
    return `/?provider=${publicType}`;
  }

  function makeLink(label, href, className, active) {
    const link = document.createElement("a");
    link.className = `${className}${active ? " is-active" : ""}`;
    link.href = href;
    link.textContent = label;
    if (active) link.setAttribute("aria-current", "page");
    return link;
  }

  function revealTab(container, tab) {
    if (!container || !tab) return;
    const left = tab.offsetLeft;
    const right = left + tab.offsetWidth;
    if (left < container.scrollLeft) {
      container.scrollLeft = left;
    } else if (right > container.scrollLeft + container.clientWidth) {
      container.scrollLeft = right - container.clientWidth;
    }
  }

  async function logout() {
    try {
      await fetch("/api/auth/logout", { method: "POST", cache: "no-store" });
    } catch (_) {
      // The login page remains the recovery path if the session is already gone.
    }
    const next = encodeURIComponent(window.location.pathname || "/");
    window.location.href = `/login?scope=admin&next=${next}`;
  }

  function render() {
    if (!state.shell) return;
    document.body.dataset.paylinkSection = state.activeSection;
    const provider = currentProvider();
    const primary = document.createElement("div");
    primary.className = "paylink-app-shell__primary";

    const brand = makeLink("Paylink Console", targetFor("generate", provider), "paylink-app-shell__brand", false);
    const globalNav = document.createElement("nav");
    globalNav.className = "paylink-app-shell__global";
    globalNav.setAttribute("aria-label", "全局导航");
    for (const [section, label] of GLOBAL_ITEMS) {
      globalNav.append(makeLink(label, targetFor(section, provider), "paylink-app-shell__link", section === state.activeSection));
    }

    const logoutButton = document.createElement("button");
    logoutButton.className = "paylink-app-shell__logout";
    logoutButton.type = "button";
    logoutButton.textContent = "退出";
    logoutButton.title = "退出登录";
    logoutButton.addEventListener("click", logout);
    primary.append(brand, globalNav, logoutButton);

    const providers = document.createElement("div");
    providers.className = "paylink-app-shell__providers";
    const providerLabel = document.createElement("span");
    providerLabel.className = "paylink-app-shell__provider-label";
    providerLabel.textContent = "提链模块";
    const providerNav = document.createElement("nav");
    providerNav.className = "paylink-app-shell__provider-list";
    providerNav.setAttribute("aria-label", "Provider 导航");
    for (const item of state.providers) {
      providerNav.append(
        makeLink(
          item.display_name,
          targetFor(state.activeSection, item),
          "paylink-app-shell__provider-link",
          item.public_type === state.activeProvider,
        ),
      );
    }
    providers.append(providerLabel, providerNav);

    state.shell.replaceChildren(primary, providers);
    revealTab(globalNav, globalNav.querySelector(".is-active"));
    revealTab(providerNav, providerNav.querySelector(".is-active"));
  }

  async function loadProviders() {
    const response = await fetch("/api/providers", { cache: "no-store" });
    if (!response.ok) throw new Error(`provider metadata request failed (${response.status})`);
    const payload = await response.json();
    state.providers = Array.isArray(payload.providers) ? payload.providers : [];
    if (!state.providers.some((provider) => provider.public_type === state.activeProvider)) {
      state.activeProvider = state.providers[0] ? state.providers[0].public_type : state.activeProvider;
    }
  }

  async function boot() {
    state.activeSection = sectionFromLocation();
    state.activeProvider = providerFromLocation();
    state.shell = document.createElement("header");
    state.shell.className = "paylink-app-shell";
    document.body.classList.add("paylink-shell-ready");
    document.body.prepend(state.shell);
    render();
    try {
      await loadProviders();
    } catch (error) {
      console.error("[Paylink Shell]", error);
    }
    render();
  }

  window.addEventListener("paylink:provider-change", (event) => {
    const nextProvider = normalizePublicType(event.detail && event.detail.publicType);
    if (!nextProvider) return;
    state.activeProvider = nextProvider;
    render();
  });
  window.addEventListener("hashchange", () => {
    state.activeSection = sectionFromLocation();
    render();
  });
  document.addEventListener("DOMContentLoaded", boot, { once: true });
})();
