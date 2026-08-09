(() => {
  "use strict";

  const form = document.querySelector("#proxyConfigForm");
  const providerTitle = document.querySelector("#providerTitle");
  const fallbackState = document.querySelector("#fallbackState");
  const poolState = document.querySelector("#poolState");
  const fallbackUpdate = document.querySelector("#fallbackUpdate");
  const poolUpdate = document.querySelector("#poolUpdate");
  const fallbackProxy = document.querySelector("#fallbackProxy");
  const proxyPool = document.querySelector("#proxyPool");
  const saveButton = document.querySelector("#saveButton");
  const testButton = document.querySelector("#testButton");
  const formStatus = document.querySelector("#formStatus");
  const paypalProfileSection = document.querySelector("#paypalProfileSection");
  const paypalProfileState = document.querySelector("#paypalProfileState");
  const paypalCountry = document.querySelector("#paypalCountry");
  const saveProfileButton = document.querySelector("#saveProfileButton");
  const provider = String(new URLSearchParams(window.location.search).get("provider") || "pix").trim().toLowerCase();

  function setStatus(message, kind = "") {
    formStatus.textContent = message;
    formStatus.className = `proxy-config__status${kind ? ` is-${kind}` : ""}`;
  }

  function setBusy(busy) {
    saveButton.disabled = busy;
    testButton.disabled = busy;
    if (saveProfileButton) saveProfileButton.disabled = busy;
  }

  function setUpdateState() {
    fallbackProxy.disabled = !fallbackUpdate.checked;
    proxyPool.disabled = !poolUpdate.checked;
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

  function displayConfig(config) {
    providerTitle.textContent = `${config.display_name || provider} 代理配置`;
    const fallback = config.fallback || {};
    const pool = config.pool || {};
    fallbackState.textContent = `${fallback.env_key || "-"} · ${fallback.configured ? "已配置" : "未配置"}`;
    poolState.textContent = `${pool.env_key || "-"} · ${pool.configured ? `已配置 ${Number(pool.count || 0)} 条` : "未配置"}`;
    fallbackProxy.placeholder = fallback.configured ? "已配置，输入新地址后保存" : "http://host:port";
    proxyPool.placeholder = pool.configured ? "已配置，输入新代理池后保存" : "每行一个代理地址";
  }

  function displayProfile(config) {
    if (!paypalProfileSection || !paypalCountry || !paypalProfileState) return;
    paypalProfileSection.hidden = false;
    const choices = Array.isArray(config.choices) ? config.choices : [];
    paypalCountry.replaceChildren();
    choices.forEach((choice) => {
      const option = document.createElement("option");
      option.value = String(choice.country || "");
      option.textContent = `${choice.label || choice.country} (${choice.country || "-"} / ${choice.currency || "-"})`;
      option.selected = option.value === String(config.country || "");
      paypalCountry.append(option);
    });
    paypalProfileState.textContent = `${config.country || "-"} / ${config.locale || "-"} / ${config.currency || "-"}`;
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

  if (saveProfileButton) {
    saveProfileButton.addEventListener("click", async () => {
      if (provider !== "paypal" || !paypalCountry) return;
      setBusy(true);
      setStatus("Saving profile...");
      try {
        const response = await fetch("/api/config/provider", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ provider, country: paypalCountry.value }),
        });
        const result = await responseData(response);
        displayProfile(result.config || {});
        await loadConfig();
        setStatus("Profile saved", "success");
      } catch (error) {
        setStatus(error.message || "Profile save failed", "error");
      } finally {
        setBusy(false);
      }
    });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!fallbackUpdate.checked && !poolUpdate.checked) {
      setStatus("请选择要更新的配置项", "error");
      return;
    }
    const payload = { provider };
    if (fallbackUpdate.checked) payload.fallbackProxy = fallbackProxy.value.trim();
    if (poolUpdate.checked) payload.proxyPool = proxyPool.value.trim();
    setBusy(true);
    setStatus("保存中...");
    try {
      const response = await fetch("/api/config/proxy", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await responseData(response);
      displayConfig(result.config || {});
      fallbackProxy.value = "";
      proxyPool.value = "";
      fallbackUpdate.checked = false;
      poolUpdate.checked = false;
      setUpdateState();
      setStatus("配置已保存", "success");
    } catch (error) {
      setStatus(error.message || "保存失败", "error");
    } finally {
      setBusy(false);
    }
  });

  testButton.addEventListener("click", async () => {
    setBusy(true);
    setStatus("测试中...");
    try {
      const response = await fetch("/api/config/proxy/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider }),
      });
      const result = await responseData(response);
      const duration = Number.isFinite(result.duration_ms) ? ` (${result.duration_ms} ms)` : "";
      setStatus(`${result.message || "测试完成"}${duration}`, result.ok ? "success" : "error");
    } catch (error) {
      setStatus(error.message || "测试失败", "error");
    } finally {
      setBusy(false);
    }
  });

  fallbackUpdate.addEventListener("change", setUpdateState);
  poolUpdate.addEventListener("change", setUpdateState);
  setUpdateState();
  loadConfig().catch((error) => setStatus(error.message || "加载失败", "error"));
})();
