(() => {
  "use strict";

  const form = document.querySelector("#proxyConfigForm");
  const providerTitle = document.querySelector("#providerTitle");
  const stageConfigList = document.querySelector("#stageConfigList");
  const formStatus = document.querySelector("#formStatus");
  const paypalProfileSection = document.querySelector("#paypalProfileSection");
  const paypalProfileState = document.querySelector("#paypalProfileState");
  const paypalCountry = document.querySelector("#paypalCountry");
  const paypalLocale = document.querySelector("#paypalLocale");
  const saveProfileButton = document.querySelector("#saveProfileButton");
  const provider = String(new URLSearchParams(window.location.search).get("provider") || "pix").trim().toLowerCase();

  function setStatus(message, kind = "") {
    formStatus.textContent = message;
    formStatus.className = `proxy-config__status${kind ? ` is-${kind}` : ""}`;
  }

  function setBusy(busy) {
    form.querySelectorAll("button, input, textarea, select").forEach((node) => {
      node.disabled = busy || node.dataset.enabledByToggle === "false";
    });
  }

  function configError(payload, response) {
    const detail = payload && typeof payload.detail === "string" ? payload.detail : "请求失败";
    const error = new Error(detail);
    error.status = response.status;
    return error;
  }

  async function responseData(response) {
    let payload = {};
    try {
      payload = await response.json();
    } catch (_) {
      payload = {};
    }
    if (response.status === 401) {
      const next = encodeURIComponent(`${window.location.pathname}${window.location.search}`);
      window.location.assign(`/login?scope=admin&next=${next}`);
      throw new Error("需要管理员登录");
    }
    if (!response.ok) throw configError(payload, response);
    return payload;
  }

  function configuredText(flag) {
    return flag ? "已配置" : "未配置";
  }

  function stageItems(config) {
    if (Array.isArray(config.visible_stages) && config.visible_stages.length) return config.visible_stages;
    if (Array.isArray(config.stages) && config.stages.length) return config.stages;
    return [
      {
        stage: "provider",
        label: "Provider / Stripe 池",
        role: "stripe_provider",
        region: "",
        fallback: config.fallback || {},
        pool: config.pool || {},
      },
    ];
  }

  function toggleStageInputs(section) {
    const poolUpdate = section.querySelector("[data-role='pool-toggle']");
    const proxyPool = section.querySelector("[data-role='pool-input']");
    proxyPool.dataset.enabledByToggle = poolUpdate.checked ? "true" : "false";
    proxyPool.disabled = !poolUpdate.checked;
  }

  function renderStage(stage) {
    const section = document.createElement("section");
    section.className = "proxy-config__section proxy-config__stage";
    section.dataset.stage = String(stage.stage || "provider");

    const pool = stage.pool || {};
    const region = stage.region ? ` · ${stage.region}` : "";
    section.innerHTML = `
      <div class="proxy-config__section-header">
        <div>
          <h2>${stage.label || stage.stage || "阶段代理池"}${region}</h2>
          <p class="proxy-config__meta">${stage.role || "-"} · pool: ${pool.env_key || "-"}</p>
          <p class="proxy-config__meta">代理池 ${configuredText(pool.configured)}${pool.configured ? `（${Number(pool.count || 0)} 条）` : ""}</p>
        </div>
      </div>

      <div class="proxy-config__stage-grid">
        <label class="proxy-config__toggle">
          <input data-role="pool-toggle" type="checkbox" />
          <span>更新代理池</span>
        </label>

        <label class="proxy-config__label" for="${section.dataset.stage}-pool">代理池地址</label>
        <textarea id="${section.dataset.stage}-pool" data-role="pool-input" rows="6" autocomplete="off" spellcheck="false" placeholder="${pool.configured ? "已配置，输入新代理池后保存；留空保存表示清空" : "每行一个代理地址"}" disabled></textarea>
      </div>

      <div class="proxy-config__stage-actions">
        <button data-role="save-stage" type="button">保存此阶段</button>
        <button data-role="test-stage" class="proxy-config__secondary" type="button">测试此阶段</button>
      </div>
    `;

    section.querySelectorAll("[data-role='pool-toggle']").forEach((toggle) => {
      toggle.addEventListener("change", () => toggleStageInputs(section));
    });
    section.querySelector("[data-role='save-stage']").addEventListener("click", () => saveStage(section));
    section.querySelector("[data-role='test-stage']").addEventListener("click", () => testStage(section));
    toggleStageInputs(section);
    return section;
  }

  function displayConfig(config) {
    const stages = stageItems(config);
    providerTitle.textContent = `${config.display_name || provider} 代理池（${stages.length} 个配置池）`;
    stageConfigList.replaceChildren(...stages.map(renderStage));
  }

  function displayProfile(config) {
    if (!paypalProfileSection || !paypalCountry || !paypalLocale || !paypalProfileState) return;
    paypalProfileSection.hidden = false;
    const choices = Array.isArray(config.choices) ? config.choices : [];
    const localeChoices = Array.isArray(config.locale_choices) ? config.locale_choices : [];
    paypalCountry.replaceChildren();
    choices.forEach((choice) => {
      const option = document.createElement("option");
      option.value = String(choice.country || "");
      option.dataset.defaultLocale = String(choice.locale || "");
      option.textContent = `${choice.label || choice.country} (${choice.country || "-"} / ${choice.currency || "-"})`;
      option.selected = option.value === String(config.country || "");
      paypalCountry.append(option);
    });
    paypalLocale.replaceChildren();
    localeChoices.forEach((choice) => {
      const option = document.createElement("option");
      option.value = String(choice.locale || "");
      option.textContent = `${choice.label || choice.locale} (${choice.locale || "-"})`;
      option.selected = option.value === String(config.locale || "");
      paypalLocale.append(option);
    });
    paypalProfileState.textContent = `当前 Profile：${config.country || "-"} / ${config.locale || "-"} / ${config.currency || "-"}`;
  }

  async function loadProfile() {
    if (provider !== "paypal") return;
    const response = await fetch(`/api/config/provider?provider=${encodeURIComponent(provider)}`, { cache: "no-store" });
    const payload = await responseData(response);
    displayProfile(payload.config || {});
  }

  async function loadConfig() {
    setStatus("加载中...");
    const response = await fetch(`/api/config/proxy?provider=${encodeURIComponent(provider)}`, { cache: "no-store" });
    const payload = await responseData(response);
    displayConfig(payload.config || {});
    await loadProfile();
    setStatus("配置已加载");
  }

  async function saveStage(section) {
    const stage = section.dataset.stage || "provider";
    const poolUpdate = section.querySelector("[data-role='pool-toggle']");
    const proxyPool = section.querySelector("[data-role='pool-input']");
    if (!poolUpdate.checked) {
      setStatus("请选择要更新的代理池", "error");
      return;
    }
    const payload = { provider, stage, proxyPool: proxyPool.value.trim() };
    setBusy(true);
    setStatus(`保存 ${stage} 阶段中...`);
    try {
      const response = await fetch("/api/config/proxy", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await responseData(response);
      displayConfig(result.config || {});
      setStatus(`${stage} 阶段配置已保存`, "success");
    } catch (error) {
      setStatus(error.message || "保存失败", "error");
    } finally {
      setBusy(false);
      stageConfigList.querySelectorAll(".proxy-config__stage").forEach(toggleStageInputs);
    }
  }

  async function testStage(section) {
    const stage = section.dataset.stage || "provider";
    setBusy(true);
    setStatus(`测试 ${stage} 阶段中...`);
    try {
      const response = await fetch("/api/config/proxy/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider, stage }),
      });
      const result = await responseData(response);
      const duration = Number.isFinite(result.duration_ms) ? ` (${result.duration_ms} ms)` : "";
      setStatus(`${result.message || "测试完成"}${duration}`, result.ok ? "success" : "error");
    } catch (error) {
      setStatus(error.message || "测试失败", "error");
    } finally {
      setBusy(false);
      stageConfigList.querySelectorAll(".proxy-config__stage").forEach(toggleStageInputs);
    }
  }

  if (saveProfileButton) {
    saveProfileButton.addEventListener("click", async () => {
      if (provider !== "paypal" || !paypalCountry || !paypalLocale) return;
      setBusy(true);
      setStatus("保存 PayPal Profile 中...");
      try {
        const response = await fetch("/api/config/provider", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ provider, country: paypalCountry.value, locale: paypalLocale.value }),
        });
        const result = await responseData(response);
        displayProfile(result.config || {});
        await loadConfig();
        setStatus("PayPal Profile 已保存", "success");
      } catch (error) {
        setStatus(error.message || "PayPal Profile 保存失败", "error");
      } finally {
        setBusy(false);
      }
    });
  }

  form.addEventListener("submit", (event) => event.preventDefault());
  loadConfig().catch((error) => setStatus(error.message || "加载失败", "error"));
})();
