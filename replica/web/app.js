/* 衣镜 Studio · AI 换装工作台 */
(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);

  const state = {
    tab: "restyle",
    person: null,        // 换装人物图 {id, url}
    garment: null,       // 换装目标服装图
    tryonPerson: null,   // 试衣人物图
    tryonGarment: null,  // 试衣服装图
    tryonBottom: null,   // 试衣下装图
    videoImage: null,    // 视频首帧
    models: null,
    modelTarget: null,
    modelFilter: "all",
    taskId: null,
    currentTaskId: null,
    schemes: [],
    timer: null,
    source: null,
    config: null,
    busy: false,
  };

  const els = {
    personDrop: $("#personDrop"),
    personInput: $("#personInput"),
    personPreview: $("#personPreview"),
    personRemove: $("#personRemove"),
    garmentDrop: $("#garmentDrop"),
    garmentInput: $("#garmentInput"),
    garmentPreview: $("#garmentPreview"),
    garmentRemove: $("#garmentRemove"),
    instruction: $("#instruction"),
    part: $("#part"),
    count: $("#count"),
    size: $("#size"),
    model: $("#model"),
    dryRun: $("#dryRun"),
    generate: $("#generate"),
    formError: $("#formError"),
    taskError: $("#taskError"),
    statusLine: $("#statusLine"),
    emptyState: $("#emptyState"),
    loading: $("#loading"),
    loadingText: $("#loadingText"),
    results: $("#results"),
    promptBox: $("#promptBox"),
    promptText: $("#promptText"),
    copyPrompt: $("#copyPrompt"),
    costEstimate: $("#costEstimate"),
    costModel: $("#costModel"),
    ledger: $("#ledger"),
    ledgerTotal: $("#ledgerTotal"),
    ledgerMeta: $("#ledgerMeta"),
    emptyTitle: $("#emptyTitle"),
    emptyDesc: $("#emptyDesc"),
    restyleForm: $("#restyleForm"),
    tryonForm: $("#tryonForm"),
    tryonPersonDrop: $("#tryonPersonDrop"),
    tryonPersonInput: $("#tryonPersonInput"),
    tryonPersonPreview: $("#tryonPersonPreview"),
    tryonPersonRemove: $("#tryonPersonRemove"),
    tryonGarmentDrop: $("#tryonGarmentDrop"),
    tryonGarmentInput: $("#tryonGarmentInput"),
    tryonGarmentPreview: $("#tryonGarmentPreview"),
    tryonGarmentRemove: $("#tryonGarmentRemove"),
    tryonBottomDrop: $("#tryonBottomDrop"),
    tryonBottomInput: $("#tryonBottomInput"),
    tryonBottomPreview: $("#tryonBottomPreview"),
    tryonBottomRemove: $("#tryonBottomRemove"),
    tryonPart: $("#tryonPart"),
    tryonCount: $("#tryonCount"),
    tryonSize: $("#tryonSize"),
    tryonMethod: $("#tryonMethod"),
    tryonDesc: $("#tryonDesc"),
    tryonDryRun: $("#tryonDryRun"),
    tryonGenerate: $("#tryonGenerate"),
    tryonError: $("#tryonError"),
    tryonModelLabel: $("#tryonModelLabel"),
    tryonEstimate: $("#tryonEstimate"),
    layout: $("#layout"),
    formPanel: $("#formPanel"),
    resultTitle: $("#resultTitle"),
    historyView: $("#historyView"),
    historyGrid: $("#historyGrid"),
    historyEmpty: $("#historyEmpty"),
    historyCount: $("#historyCount"),
    historyRefresh: $("#historyRefresh"),
    historyError: $("#historyError"),
    exportLookbook: $("#exportLookbook"),
    stylistForm: $("#stylistForm"),
    styleOccasion: $("#styleOccasion"),
    styleSeason: $("#styleSeason"),
    stylePalette: $("#stylePalette"),
    styleAnchor: $("#styleAnchor"),
    styleGenerate: $("#styleGenerate"),
    styleFormError: $("#styleFormError"),
    styleModelLabel: $("#styleModelLabel"),
    styleView: $("#styleView"),
    styleGrid: $("#styleGrid"),
    styleEmpty: $("#styleEmpty"),
    styleError: $("#styleError"),
    styleMeta: $("#styleMeta"),
    videoForm: $("#videoForm"),
    videoDrop: $("#videoDrop"),
    videoInput: $("#videoInput"),
    videoPreview: $("#videoPreview"),
    videoRemove: $("#videoRemove"),
    videoPrompt: $("#videoPrompt"),
    videoDuration: $("#videoDuration"),
    videoResolution: $("#videoResolution"),
    videoMethod: $("#videoMethod"),
    videoDryRun: $("#videoDryRun"),
    videoGenerate: $("#videoGenerate"),
    videoError: $("#videoError"),
    videoModelLabel: $("#videoModelLabel"),
    videoEstimate: $("#videoEstimate"),
    modelModal: $("#modelModal"),
    modelClose: $("#modelClose"),
    modelGrid: $("#modelGrid"),
    modelFilters: $("#modelFilters"),
    modelError: $("#modelError"),
    restyleModelPick: $("#restyleModelPick"),
    tryonModelPick: $("#tryonModelPick"),
    balanceButton: $("#balanceButton"),
    balanceModal: $("#balanceModal"),
    balanceClose: $("#balanceClose"),
    balanceBody: $("#balanceBody"),
    balanceError: $("#balanceError"),
    balanceRefresh: $("#balanceRefresh"),
  };

  /* ── 通用 UI ─────────────────────────────────────── */
  function showError(message) {
    const targets = {
      restyle: els.formError,
      tryon: els.tryonError,
      stylist: els.styleFormError,
      video: els.videoError,
    };
    const target = targets[state.tab] || els.formError;
    Object.values(targets).forEach((element) => {
      if (element !== target) element.hidden = true;
    });
    target.textContent = message;
    target.hidden = false;
    clearTimeout(showError._timer);
    showError._timer = setTimeout(() => {
      target.hidden = true;
    }, 8000);
  }

  function setStatus(text) {
    els.statusLine.textContent = text;
  }

  function setBusy(busy) {
    state.busy = busy;
    els.generate.textContent = busy && state.tab === "restyle" ? "生成中…" : "开始换装";
    els.tryonGenerate.textContent = busy && state.tab === "tryon" ? "试衣中…" : "开始试衣";
    els.styleGenerate.disabled = busy;
    els.styleGenerate.textContent = busy ? "生成中…" : "生成 3 套搭配";
    els.videoGenerate.disabled = busy || !state.videoImage;
    els.videoGenerate.textContent = busy && state.tab === "video" ? "生成中…" : "生成视频";
    refreshButton();
  }

  function canGenerate() {
    if (state.tab === "history" || state.tab === "stylist") return false;
    if (state.tab === "video") return Boolean(state.videoImage);
    if (state.tab === "tryon") {
      if (!state.tryonPerson || !state.tryonGarment) return false;
      if (els.tryonPart.value === "full" && !state.tryonBottom) return false;
      return true;
    }
    return Boolean(state.person) && Boolean(els.instruction.value.trim() || state.garment);
  }

  function showLoading(show, text) {
    els.loading.hidden = !show;
    if (text) els.loadingText.textContent = text;
  }

  function showPrompt(prompt, open = false) {
    if (!prompt) return;
    const wasHidden = els.promptBox.hidden;
    els.promptText.textContent = prompt;
    els.promptBox.hidden = false;
    if (wasHidden) els.promptBox.open = open;
  }

  /* ── 上传 ────────────────────────────────────────── */
  function setupDropzone(drop, input, key, previewImg, removeBtn) {
    const openPicker = () => input.click();

    drop.addEventListener("click", (event) => {
      if (event.target.closest("button")) return;
      openPicker();
    });
    drop.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openPicker();
      }
    });
    input.addEventListener("change", () => {
      if (input.files[0]) handleFile(input.files[0], key);
      input.value = "";
    });
    ["dragenter", "dragover"].forEach((name) => {
      drop.addEventListener(name, (event) => {
        event.preventDefault();
        drop.classList.add("dragging");
      });
    });
    ["dragleave", "drop"].forEach((name) => {
      drop.addEventListener(name, (event) => {
        event.preventDefault();
        drop.classList.remove("dragging");
      });
    });
    drop.addEventListener("drop", (event) => {
      const file = event.dataTransfer.files[0];
      if (file) handleFile(file, key);
    });
    removeBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      clearImage(key);
    });
  }

  const DROPZONE_ELS = {
    person: () => ({ preview: els.personPreview, drop: els.personDrop }),
    garment: () => ({ preview: els.garmentPreview, drop: els.garmentDrop }),
    tryonPerson: () => ({ preview: els.tryonPersonPreview, drop: els.tryonPersonDrop }),
    tryonGarment: () => ({ preview: els.tryonGarmentPreview, drop: els.tryonGarmentDrop }),
    tryonBottom: () => ({ preview: els.tryonBottomPreview, drop: els.tryonBottomDrop }),
    video: () => ({ preview: els.videoPreview, drop: els.videoDrop }),
  };

  function getEls(key) {
    return (DROPZONE_ELS[key] || DROPZONE_ELS.garment)();
  }

  function stateKeyFor(key) {
    return key === "video" ? "videoImage" : key;
  }

  const UPLOAD_LABELS = {
    person: ["正在上传人物图…", "人物图已就绪"],
    garment: ["正在上传服装图…", "服装图已就绪"],
    tryonPerson: ["正在上传人物图…", "人物图已就绪"],
    tryonGarment: ["正在上传服装图…", "服装图已就绪"],
    tryonBottom: ["正在上传下装图…", "下装图已就绪"],
    video: ["正在上传首帧图片…", "首帧图片已就绪"],
  };

  async function handleFile(file, key) {
    if (!/^image\/(jpeg|png|webp|bmp)$/.test(file.type)) {
      showError("仅支持 JPG / PNG / WEBP / BMP 图片");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      showError("图片超过 10MB，请压缩后再上传");
      return;
    }
    const labels = UPLOAD_LABELS[key] || ["正在上传…", "素材已就绪"];
    setStatus(labels[0]);

    const form = new FormData();
    form.append("file", file);
    try {
      const response = await fetch("/api/upload", { method: "POST", body: form });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "上传失败");
      state[stateKeyFor(key)] = { id: data.asset_id, url: data.url };
      const { preview, drop } = getEls(key);
      preview.src = data.url;
      preview.parentElement.hidden = false;
      drop.querySelector(".drop-empty").hidden = true;
      drop.classList.add("has-image");
      setStatus(labels[1]);
      refreshButton();
      updateEstimate();
      updateTryonEstimate();
    } catch (error) {
      showError(error.message);
      setStatus("上传失败");
    }
  }

  function clearImage(key) {
    state[stateKeyFor(key)] = null;
    const { preview, drop } = getEls(key);
    preview.removeAttribute("src");
    preview.parentElement.hidden = true;
    drop.querySelector(".drop-empty").hidden = false;
    drop.classList.remove("has-image");
    refreshButton();
    updateEstimate();
    updateTryonEstimate();
    setStatus("素材已移除");
  }

  /* ── 内置模特库 ──────────────────────────────────── */
  async function openModelPicker(target) {
    state.modelTarget = target;
    els.modelError.hidden = true;
    els.modelModal.hidden = false;
    if (state.models) {
      renderModels();
      return;
    }
    els.modelGrid.innerHTML = '<div class="model-empty">正在加载模特库…</div>';
    try {
      const response = await fetch("/api/models");
      const data = await response.json().catch(() => []);
      if (!response.ok) throw new Error(data.detail || "加载模特库失败");
      state.models = Array.isArray(data) ? data : [];
      renderModels();
    } catch (error) {
      els.modelGrid.innerHTML = "";
      els.modelError.textContent = error.message;
      els.modelError.hidden = false;
    }
  }

  function closeModelPicker() {
    els.modelModal.hidden = true;
    state.modelTarget = null;
  }

  function renderModels() {
    const filter = state.modelFilter;
    const models = (state.models || []).filter((model) => {
      if (filter === "all") return true;
      if (filter === "child") return model.ageGroup === "child";
      return model.gender === filter && model.ageGroup !== "child";
    });

    els.modelGrid.innerHTML = "";
    if (!models.length) {
      els.modelGrid.innerHTML = '<div class="model-empty">没有匹配的模特</div>';
      return;
    }
    models.forEach((model) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "model-card";
      card.dataset.modelId = model.id;
      card.innerHTML = `
        <img src="${escapeAttr(model.image_url)}" alt="${escapeAttr(model.name)}" loading="lazy">
        <div class="model-info">
          <div class="model-name">${escapeHtml(model.name)}</div>
          <div class="model-meta">${escapeHtml(model.style)} · ${escapeHtml(model.height)} · ${escapeHtml(model.bodyType)}</div>
        </div>`;
      els.modelGrid.appendChild(card);
    });
  }

  async function chooseModel(modelId) {
    const model = (state.models || []).find((item) => item.id === modelId);
    const target = state.modelTarget;
    if (!model || !model.image_url || !target) return;
    setStatus(`正在载入模特：${model.name}…`);
    try {
      const response = await fetch(model.image_url);
      if (!response.ok) throw new Error("模特图片加载失败");
      const blob = await response.blob();
      const subtype = (blob.type.split("/")[1] || "png").replace("jpeg", "jpg");
      const file = new File([blob], `model_${model.id}.${subtype}`, {
        type: blob.type || "image/png",
      });
      closeModelPicker();
      await handleFile(file, target);
      setStatus(`已选择模特：${model.name}`);
    } catch (error) {
      els.modelError.textContent = error.message;
      els.modelError.hidden = false;
    }
  }

  /* ── 余额与额度 ──────────────────────────────────── */
  function openBalanceModal() {
    els.balanceError.hidden = true;
    els.balanceModal.hidden = false;
    loadBalance();
  }

  function closeBalanceModal() {
    els.balanceModal.hidden = true;
  }

  function money(value) {
    if (value === null || value === undefined || value === "") return "—";
    const number = Number(value);
    return Number.isFinite(number) ? `¥${number.toFixed(2)}` : escapeHtml(String(value));
  }

  async function loadBalance() {
    els.balanceError.hidden = true;
    els.balanceBody.innerHTML = '<p class="hint">正在检测…</p>';
    try {
      const response = await fetch("/api/balance");
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "余额检测失败");
      renderBalance(data);
    } catch (error) {
      els.balanceBody.innerHTML = "";
      els.balanceError.textContent = error.message;
      els.balanceError.hidden = false;
    }
  }

  function renderBalance(data) {
    const parts = [];
    if (data.available) {
      parts.push(`
        <div class="balance-hero">
          <span>可用余额</span>
          <strong>${money(data.available_amount)}</strong>
          <small>${escapeHtml(data.currency || "CNY")}</small>
        </div>`);
      parts.push(`
        <div class="balance-grid">
          <div><span>现金余额</span><strong>${money(data.cash_amount)}</strong></div>
          <div><span>信控额度</span><strong>${money(data.credit_amount)}</strong></div>
          <div><span>网商信控</span><strong>${money(data.mybank_credit_amount)}</strong></div>
        </div>`);
    } else if (!data.configured) {
      parts.push(`
        <div class="balance-warning">
          未配置阿里云 AccessKey，无法查询账户余额。<br>
          百炼 <code>sk-</code> API Key 没有余额接口，请在下方填写阿里云 AccessKey。
        </div>`);
    } else {
      parts.push(`
        <div class="balance-warning">
          余额查询失败：${escapeHtml(data.error || "未知错误")}
          ${data.hint ? `<br>${escapeHtml(data.hint)}` : ""}
        </div>`);
    }

    const summary = data.cost_summary || {};
    parts.push(`
      <div class="balance-grid">
        <div><span>本地估算成本</span><strong>${money(summary.total_amount)}</strong></div>
        <div><span>生成次数</span><strong>${Number(summary.calls || 0)}</strong></div>
        <div><span>百炼 Key</span><strong>${data.dashscope_key_configured ? "已配置" : "未配置"}</strong></div>
      </div>`);

    const masked = data.access_key_id_masked || "";
    const configOpen = !data.available;
    parts.push(`
      <details class="balance-config" ${configOpen ? "open" : ""}>
        <summary>${masked ? `AccessKey：${escapeHtml(masked)}（点击更换）` : "配置阿里云 AccessKey"}</summary>
        <form id="balanceConfigForm" class="balance-config-form">
          <label>AccessKey ID
            <input id="balanceKeyId" autocomplete="off" placeholder="LTAI...">
          </label>
          <label>AccessKey Secret
            <input id="balanceKeySecret" type="password" autocomplete="new-password"
              placeholder="只保存在本机 .env，不会回显">
          </label>
          <div class="balance-config-actions">
            <button type="submit" class="primary">保存并检测</button>
            ${masked ? '<button type="button" id="balanceClearKey" class="chip">清除 AccessKey</button>' : ""}
          </div>
          <p class="hint">
            保存在本机 <code>replica/.env</code>（已 gitignore）；
            建议使用仅有 <code>AliyunBSSReadOnlyAccess</code> 权限的 RAM 用户。
          </p>
        </form>
      </details>`);

    if (data.recent_quota_error) {
      const error = data.recent_quota_error;
      parts.push(`
        <div class="balance-quota">
          <strong>最近一次额度错误</strong>
          <span>${escapeHtml(error.type || "")} · ${formatTime(error.created_at)}</span>
          <p>${escapeHtml(error.error || "")}</p>
          <p class="hint">到百炼控制台「模型用量 → 免费额度」关闭「免费额度用完即停」，或充值后重试。</p>
        </div>`);
    }

    parts.push(`
      <p class="hint">
        文本模型：${escapeHtml(data.stylist_model || "—")} ·
        视频模型：${escapeHtml(data.video_model || "—")}
      </p>`);
    els.balanceBody.innerHTML = parts.join("");
  }

  function refreshButton() {
    const disabled = state.busy || !canGenerate();
    els.generate.disabled = disabled;
    els.tryonGenerate.disabled = disabled;
    els.videoGenerate.disabled = state.busy || !state.videoImage;
  }

  /* ── 提交任务 ────────────────────────────────────── */
  async function submitRestyle() {
    if (!state.person) {
      showError("请先上传人物图");
      return;
    }
    if (!canGenerate()) {
      showError("请填写换装指令，或上传目标服装图");
      return;
    }
    await startTask("/api/restyle", {
      image_id: state.person.id,
      garment_id: state.garment ? state.garment.id : null,
      instruction: els.instruction.value.trim() || null,
      part: els.part.value,
      count: Number(els.count.value),
      size: els.size.value.trim() || null,
      model: els.model.value || null,
      dry_run: els.dryRun.checked,
    });
  }

  async function submitTryon() {
    if (!state.tryonPerson) {
      showError("请先上传人物图");
      return;
    }
    if (!state.tryonGarment) {
      showError("请上传服装图");
      return;
    }
    if (els.tryonPart.value === "full" && !state.tryonBottom) {
      showError("整套模式需要上传下装图");
      return;
    }
    await startTask("/api/tryon", {
      person_image_id: state.tryonPerson.id,
      garment_id: state.tryonGarment.id,
      bottom_garment_id: state.tryonBottom ? state.tryonBottom.id : null,
      part: els.tryonPart.value,
      variants: Number(els.tryonCount.value),
      method: els.tryonMethod.value,
      size: els.tryonSize.value.trim() || "2K",
      desc: els.tryonDesc.value.trim() || null,
      dry_run: els.tryonDryRun.checked,
    });
  }

  async function submitVideo() {
    if (!state.videoImage) {
      showError("请先上传首帧图片");
      return;
    }
    await startTask("/api/video", {
      image_id: state.videoImage.id,
      prompt: els.videoPrompt.value.trim() || null,
      duration: Number(els.videoDuration.value),
      resolution: els.videoResolution.value,
      method: els.videoMethod.value,
      dry_run: els.videoDryRun.checked,
    });
  }

  async function startTask(endpoint, payload) {
    els.formError.hidden = true;
    els.tryonError.hidden = true;
    els.taskError.hidden = true;
    els.results.innerHTML = "";
    els.promptBox.hidden = true;
    els.emptyState.hidden = true;
    els.exportLookbook.hidden = true;
    state.currentTaskId = null;
    if (state.timer) {
      clearTimeout(state.timer);
      state.timer = null;
    }
    setBusy(true);
    showLoading(true, "正在提交任务…");
    setStatus("提交中…");

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "提交失败");

      if (data.status === "dry_run") {
        showLoading(false);
        showPrompt(data.prompt, true);
        const estimate = data.cost && data.cost.estimated != null
          ? ` · 预计 ¥${Number(data.cost.estimated).toFixed(2)}`
          : "";
        setStatus(`Prompt 预览完成${estimate}（未调用 API）`);
        setBusy(false);
        els.emptyState.hidden = false;
        return;
      }

      state.taskId = data.id;
      showLoading(true, "已提交，等待生成…");
      setStatus("排队中…");
      subscribe(data.id);
    } catch (error) {
      showLoading(false);
      setBusy(false);
      setStatus("提交失败");
      showError(error.message);
      if (!els.results.children.length) els.emptyState.hidden = false;
    }
  }

  function subscribe(taskId) {
    if (state.source) {
      state.source.close();
      state.source = null;
    }
    if (!("EventSource" in window)) {
      poll(taskId);
      return;
    }

    const source = new EventSource(`/api/tasks/${taskId}/events`);
    state.source = source;
    let done = false;

    const finish = () => {
      if (done) return;
      done = true;
      source.close();
      if (state.source === source) state.source = null;
      showLoading(false);
      setBusy(false);
      refreshLedger();
    };

    source.onmessage = (event) => {
      let task;
      try {
        task = JSON.parse(event.data);
      } catch {
        return;
      }
      renderTask(task);
      if (task.status === "succeeded" || task.status === "failed") finish();
    };
    source.onerror = () => {
      if (done) return;
      done = true;
      source.close();
      if (state.source === source) state.source = null;
      poll(taskId); // SSE 断开时回退到轮询
    };
  }

  async function poll(taskId) {
    try {
      const response = await fetch(`/api/tasks/${taskId}`);
      const task = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(task.detail || "查询任务失败");
      renderTask(task);

      if (task.status === "queued" || task.status === "running") {
        state.timer = setTimeout(() => poll(taskId), 1500);
        return;
      }
      state.timer = null;
      showLoading(false);
      setBusy(false);
      refreshLedger();
    } catch (error) {
      showLoading(false);
      setBusy(false);
      setStatus("查询失败");
      showError(error.message);
    }
  }

  function renderTask(task) {
    if (task.prompt) showPrompt(task.prompt, task.status === "dry_run");
    if (task.used_model) $("#modelTag").textContent = task.used_model;

    if (task.status === "queued") {
      showLoading(true, "排队中，前面还有任务…");
      setStatus("排队中…");
      return;
    }
    if (task.status === "running") {
      const isVideo = task.type === "video";
      const action = isVideo ? "生成视频" : task.type === "tryon" ? "试衣" : "换装";
      const wait = isVideo ? "约 1–3 分钟" : "约 30–60 秒";
      showLoading(true, `正在${action}，${wait}…`);
      setStatus("生成中…");
      return;
    }
    if (task.status === "failed") {
      showLoading(false);
      setStatus("生成失败");
      els.taskError.textContent = task.error || "生成失败，请重试";
      els.taskError.hidden = false;
      if (!els.results.children.length) els.emptyState.hidden = false;
      return;
    }
    if (task.status === "succeeded") {
      showLoading(false);
      state.currentTaskId = task.id;
      const costText = formatCost(task.cost);
      if (task.type === "video") {
        els.exportLookbook.hidden = true;
        const request = task.request || {};
        setStatus(
          `完成 · 视频 ${request.duration || ""} 秒 · ${formatMs(task.elapsed_ms)}` +
            (costText ? ` · ${costText}（估算）` : "")
        );
        renderVideoResult(task);
        return;
      }
      els.exportLookbook.hidden = false;
      setStatus(
        `完成 · ${(task.images || []).length} 张 · ${formatMs(task.elapsed_ms)}` +
          (costText ? ` · ${costText}（估算）` : "") +
          (task.fallback ? " · 通用编辑兜底" : "")
      );
      renderResults(task);
    }
  }

  function renderVideoResult(task) {
    els.taskError.hidden = true;
    els.emptyState.hidden = true;
    const video = task.video || {};
    const url = video.url || "";
    const request = task.request || {};
    const cost = formatCost(task.cost);
    const poster = task.image_url ? ` poster="${escapeAttr(task.image_url)}"` : "";
    els.results.innerHTML = `
      <article class="video-result">
        <video src="${escapeAttr(url)}" controls autoplay loop playsinline${poster}></video>
        <div class="video-meta">
          <div>
            <strong>图生视频</strong>
            <span>${escapeHtml(task.used_model || task.model || "")} · ${escapeHtml(request.resolution || "")} · ${escapeHtml(String(request.duration || ""))} 秒${cost ? ` · ${cost}（估算）` : ""}</span>
          </div>
          <div class="actions">
            <a href="${escapeAttr(url)}" download>下载视频</a>
            <a href="${escapeAttr(url)}" target="_blank" rel="noopener">查看原视频</a>
          </div>
        </div>
      </article>`;
  }

  function renderResults(task) {
    els.taskError.hidden = true;
    els.emptyState.hidden = true;
    els.results.innerHTML = "";

    const beforeUrl =
      task.image_url ||
      (task.type === "tryon" ? state.tryonPerson && state.tryonPerson.url : state.person && state.person.url) ||
      "";
    const afterLabel = task.type === "tryon" ? "试衣后" : "换装后";
    (task.images || []).forEach((image, index) => {
      const card = document.createElement("article");
      card.className = "result-card";
      card.innerHTML = `
        <div class="ba">
          <img class="ba-after" src="${escapeAttr(image.url)}" alt="换装结果 ${index + 1}">
          <img class="ba-before" src="${escapeAttr(beforeUrl)}" alt="原图">
          <div class="ba-line"></div>
          <span class="ba-label left">原图</span>
          <span class="ba-label right">${afterLabel}</span>
          <input class="ba-range" type="range" min="0" max="100" value="55" aria-label="拖动对比原图与结果">
        </div>
        <div class="result-meta">
          <div>
            <strong>候选 ${index + 1}</strong>
            <span>${escapeHtml(task.used_model || task.model || "")}${formatCost(task.cost) ? ` · ${formatCost(task.cost)}（估算）` : ""}</span>
          </div>
          <div class="actions">
            <a href="${escapeAttr(image.url)}" download>下载</a>
            <a href="${escapeAttr(image.url)}" target="_blank" rel="noopener">查看原图</a>
          </div>
        </div>`;
      els.results.appendChild(card);
      initCompare(card.querySelector(".ba"));
    });
  }

  function initCompare(container) {
    const before = container.querySelector(".ba-before");
    const line = container.querySelector(".ba-line");
    const range = container.querySelector(".ba-range");
    const apply = (value) => {
      before.style.clipPath = `inset(0 ${100 - value}% 0 0)`;
      line.style.left = `${value}%`;
    };
    range.addEventListener("input", () => apply(Number(range.value)));
    apply(Number(range.value));
  }

  function formatMs(ms) {
    if (!ms) return "";
    return ms >= 1000 ? `${(ms / 1000).toFixed(1)} 秒` : `${ms} 毫秒`;
  }

  function formatCost(cost) {
    if (!cost || cost.amount == null) return "";
    return `¥${Number(cost.amount).toFixed(2)}`;
  }

  function modelPrice(modelId) {
    if (!state.config || !Array.isArray(state.config.models)) return null;
    const found = state.config.models.find((item) => item.id === modelId);
    return found && found.price != null ? Number(found.price) : null;
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[ch]));
  }

  function escapeAttr(value) {
    return escapeHtml(value).replace(/`/g, "&#96;");
  }

  function tryonModelInfo() {
    const cfg = state.config;
    if (!cfg) return { id: "", price: null, resolved: "qwen" };
    const method = els.tryonMethod.value;
    const resolved = method === "auto" ? (cfg.ark_configured ? "seedream" : "qwen") : method;
    const id = (cfg.tryon_method_models || {})[resolved] || "";
    const entry = (cfg.tryon_models || []).find((item) => item.id === id);
    return { id, price: entry && entry.price != null ? Number(entry.price) : null, resolved };
  }

  function updateTryonEstimate() {
    const { id, price, resolved } = tryonModelInfo();
    const count = Number(els.tryonCount.value);
    const modeLabel = resolved === "qwen" && state.config && state.config.tryon_engine === "edit"
      ? "图像编辑"
      : resolved;
    els.tryonModelLabel.textContent = id ? `${id}（${modeLabel}）` : "—";
    if (els.tryonDryRun.checked) {
      els.tryonEstimate.textContent = "预览免费";
    } else if (price == null) {
      els.tryonEstimate.textContent = "预计费用待核对";
    } else {
      els.tryonEstimate.textContent = `预计 ¥${(price * count).toFixed(2)}`;
    }
  }

  function updateVideoEstimate() {
    const method = els.videoMethod.value;
    const useWan = method !== "seedance";
    const model = useWan
      ? (state.config && state.config.video_model) || "wan2.5-i2v-preview"
      : "Seedance";
    const duration = Number(els.videoDuration.value);
    const resolution = els.videoResolution.value;
    els.videoModelLabel.textContent = model;

    if (els.videoDryRun.checked) {
      els.videoEstimate.textContent = "预览免费";
      return;
    }
    if (!useWan) {
      els.videoEstimate.textContent = "方舟计费";
      return;
    }
    const prices = (state.config && state.config.video_prices) || {};
    const unit = prices[resolution];
    els.videoEstimate.textContent =
      unit != null ? `预计 ¥${(unit * duration).toFixed(2)}` : "预计费用待核对";
  }

  function applyTab(tab) {
    state.tab = tab;
    document.querySelectorAll(".tab").forEach((btn) => {
      const active = btn.dataset.tab === tab;
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-selected", String(active));
    });
    const isHistory = tab === "history";
    const isStylist = tab === "stylist";
    const isVideo = tab === "video";
    els.restyleForm.hidden = tab !== "restyle";
    els.tryonForm.hidden = tab !== "tryon";
    els.stylistForm.hidden = !isStylist;
    els.videoForm.hidden = !isVideo;
    els.formPanel.hidden = isHistory;
    els.layout.classList.toggle("history-mode", isHistory);
    els.historyView.hidden = !isHistory;
    els.styleView.hidden = !isStylist;
    els.resultTitle.textContent = isHistory
      ? "历史记录"
      : isStylist
        ? "搭配方案"
        : isVideo
          ? "视频结果"
          : "生成结果";
    refreshButton();
  }

  function switchTab(tab) {
    if (state.busy) {
      showError("请等待当前任务完成后再切换页签");
      return;
    }
    applyTab(tab);
    els.formError.hidden = true;
    els.tryonError.hidden = true;
    els.styleFormError.hidden = true;
    els.videoError.hidden = true;
    els.taskError.hidden = true;
    els.historyError.hidden = true;
    els.results.innerHTML = "";
    els.promptBox.hidden = true;
    els.promptBox.open = false;
    els.loading.hidden = true;
    els.exportLookbook.hidden = true;

    if (tab === "history") {
      els.emptyState.hidden = true;
      setStatus("加载中…");
      loadHistory();
      return;
    }

    if (tab === "stylist") {
      els.emptyState.hidden = true;
      els.styleError.hidden = true;
      els.styleEmpty.hidden = els.styleGrid.children.length > 0;
      setStatus("选择偏好后生成");
      return;
    }

    if (tab === "video") {
      els.emptyState.hidden = false;
      els.emptyTitle.textContent = "上传首帧图片，生成短视频";
      els.emptyDesc.textContent = "首帧可以是模特图、试衣图或换装结果；视频约 5–10 秒";
      setStatus("等待上传");
      updateVideoEstimate();
      return;
    }

    els.emptyState.hidden = false;
    els.emptyTitle.textContent = tab === "restyle"
      ? "上传人物图并输入换装指令"
      : "上传人物图和服装图，开始试衣";
    els.emptyDesc.textContent = tab === "restyle"
      ? "结果会保留人物的脸、发型、姿势和背景"
      : "用图像编辑把服装自然合成到人物，保留姿势与背景";
    setStatus("等待上传");
    updateEstimate();
    updateTryonEstimate();
  }

  /* ── 历史记录 ────────────────────────────────────── */
  function showHistoryError(message) {
    els.historyError.textContent = message;
    els.historyError.hidden = false;
    clearTimeout(showHistoryError._timer);
    showHistoryError._timer = setTimeout(() => {
      els.historyError.hidden = true;
    }, 8000);
  }

  async function loadHistory() {
    els.historyError.hidden = true;
    try {
      const response = await fetch("/api/history?limit=100");
      const items = await response.json().catch(() => []);
      if (!response.ok) throw new Error(items.detail || "加载历史记录失败");
      renderHistory(Array.isArray(items) ? items : []);
    } catch (error) {
      els.historyGrid.innerHTML = "";
      els.historyEmpty.hidden = false;
      els.historyCount.textContent = "0 条记录";
      setStatus("加载失败");
      showHistoryError(error.message);
    }
  }

  function renderHistory(items) {
    els.historyGrid.innerHTML = "";
    els.historyCount.textContent = `${items.length} 条记录`;
    els.historyEmpty.hidden = items.length > 0;
    setStatus(items.length ? `共 ${items.length} 条` : "暂无记录");

    items.forEach((item) => {
      const card = document.createElement("article");
      card.className = "history-card";
      const isVideo = item.type === "video";
      const badge = isVideo
        ? "图生视频"
        : item.type === "tryon"
          ? "虚拟试衣"
          : "AI 换装";
      const badgeClass = isVideo ? "video" : item.type === "tryon" ? "tryon" : "";
      const metaParts = [];
      if (item.model) metaParts.push(item.model);
      if (isVideo) {
        metaParts.push(`${item.resolution || ""} · ${item.duration || ""} 秒`);
      } else {
        metaParts.push(`${item.image_count} 张`);
      }
      const cost = formatCost(item.cost);
      if (cost) metaParts.push(`${cost}（估算）`);
      if (item.elapsed_ms) metaParts.push(formatMs(item.elapsed_ms));

      const images = item.images || [];
      const video = item.video || {};
      const media = isVideo && video.url
        ? `<video class="history-video" src="${escapeAttr(video.url)}" controls preload="metadata"${item.image_url ? ` poster="${escapeAttr(item.image_url)}"` : ""}></video>`
        : `<div class="history-thumbs">
            ${images.map((image, index) => `
              <figure class="thumb">
                <a href="${escapeAttr(image.url)}" target="_blank" rel="noopener">
                  <img src="${escapeAttr(image.thumb_url || image.url)}" alt="生成结果">
                </a>
                <button class="thumb-del" type="button" title="删除这张图"
                  data-task-id="${escapeAttr(item.id)}" data-index="${index}">×</button>
              </figure>`).join("")}
          </div>`;

      const exportAction = isVideo && video.url
        ? `<a class="history-export" href="${escapeAttr(video.url)}" download>下载视频</a>`
        : `<a class="history-export" href="/api/lookbook/${encodeURIComponent(item.id)}">导出 Lookbook</a>`;

      card.innerHTML = `
        <div class="history-head">
          <span class="type-badge ${badgeClass}">${badge}</span>
          <span class="history-time">${formatTime(item.created_at)}</span>
        </div>
        <p class="history-title">${escapeHtml(item.title || "未命名记录")}</p>
        ${media}
        <div class="history-meta">
          <span>${escapeHtml(metaParts.join(" · "))}</span>
          <div class="history-actions">
            ${exportAction}
            <button class="history-delete" type="button"
              data-task-id="${escapeAttr(item.id)}">删除整条</button>
          </div>
        </div>`;
      els.historyGrid.appendChild(card);
    });
  }

  async function deleteHistoryImage(taskId, index) {
    if (!window.confirm("确定删除这张图片？本地文件会被移除。")) return;
    try {
      const response = await fetch(
        `/api/history/${encodeURIComponent(taskId)}/images/${index}`,
        { method: "DELETE" }
      );
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "删除失败");
      await loadHistory();
      refreshLedger();
    } catch (error) {
      showHistoryError(error.message);
    }
  }

  async function deleteHistoryTask(taskId) {
    if (!window.confirm("确定删除这条记录及其所有图片？")) return;
    try {
      const response = await fetch(`/api/history/${encodeURIComponent(taskId)}`, {
        method: "DELETE",
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "删除失败");
      await loadHistory();
      refreshLedger();
    } catch (error) {
      showHistoryError(error.message);
    }
  }

  function formatTime(ts) {
    if (!ts) return "";
    return new Date(Number(ts) * 1000).toLocaleString("zh-CN", { hour12: false });
  }

  /* ── 智能穿搭 ────────────────────────────────────── */
  async function submitStylist() {
    els.styleFormError.hidden = true;
    els.styleError.hidden = true;
    els.styleEmpty.hidden = true;
    els.styleGrid.innerHTML = "";
    els.styleMeta.textContent = "";
    setBusy(true);
    setStatus("生成搭配中…");
    showLoading(true, "正在生成 3 套搭配…");

    try {
      const response = await fetch("/api/stylist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          occasion: els.styleOccasion.value,
          season: els.styleSeason.value,
          palette: els.stylePalette.value,
          anchor: els.styleAnchor.value.trim() || null,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "生成搭配失败");
      renderSchemes(data);
    } catch (error) {
      els.styleError.textContent = error.message;
      els.styleError.hidden = false;
      els.styleEmpty.hidden = false;
      setStatus("生成失败");
    } finally {
      showLoading(false);
      setBusy(false);
    }
  }

  function renderSchemes(data) {
    state.schemes = data.schemes || [];
    els.styleGrid.innerHTML = "";
    els.styleEmpty.hidden = state.schemes.length > 0;
    els.styleError.hidden = true;

    const source = data.generated_by === "fallback" ? "规则模板" : (data.model || "LLM");
    els.styleMeta.textContent =
      `由 ${source} 生成 · ${state.schemes.length} 套方案` +
      (data.note ? ` · ${data.note}` : "");

    state.schemes.forEach((scheme, index) => {
      const card = document.createElement("article");
      card.className = "style-card";
      const items = (scheme.items || [])
        .map(
          (item) => `<span class="item-chip">${escapeHtml(item.name)}<small>${escapeHtml(item.category)} · ${escapeHtml(item.color)}</small></span>`
        )
        .join("");
      const tips = (scheme.tips || [])
        .map((tip) => `<li>${escapeHtml(tip)}</li>`)
        .join("");
      card.innerHTML = `
        <div class="style-card-head">
          <span class="style-index">方案 ${index + 1}</span>
          <h3>${escapeHtml(scheme.title || "")}</h3>
        </div>
        <div class="style-items">${items}</div>
        <p class="style-reason">${escapeHtml(scheme.reason || "")}</p>
        ${tips ? `<ul class="style-tips">${tips}</ul>` : ""}
        <div class="style-actions">
          <button class="chip style-use" type="button" data-index="${index}">用作换装指令</button>
          <button class="link-btn style-copy" type="button" data-index="${index}">复制文案</button>
        </div>`;
      els.styleGrid.appendChild(card);
    });
    setStatus(`完成 · ${state.schemes.length} 套方案`);
  }

  function schemeText(scheme) {
    const items = (scheme.items || []).map((item) => `${item.name}（${item.category}·${item.color}）`);
    const tips = (scheme.tips || []).map((tip) => `- ${tip}`).join("\n");
    return [
      `【${scheme.title}】`,
      `单品：${items.join("、")}`,
      scheme.reason ? `理由：${scheme.reason}` : "",
      tips ? `搭配要点：\n${tips}` : "",
    ]
      .filter(Boolean)
      .join("\n");
  }

  function useScheme(index) {
    const scheme = state.schemes[index];
    if (!scheme) return;
    switchTab("restyle");
    els.instruction.value = scheme.instruction || schemeText(scheme);
    refreshButton();
    els.instruction.focus();
  }

  async function copyScheme(index) {
    const scheme = state.schemes[index];
    if (!scheme) return;
    try {
      await navigator.clipboard.writeText(schemeText(scheme));
      setStatus("搭配文案已复制");
    } catch {
      showError("复制失败，请手动选择文本");
    }
  }

  /* ── 恢复进行中的任务（刷新页面不丢进度）────────── */
  async function resumeLatest() {
    try {
      const response = await fetch("/api/tasks");
      const tasks = await response.json();
      if (!Array.isArray(tasks) || !tasks.length) return;
      const latest = tasks[0];
      if (latest.status !== "queued" && latest.status !== "running") return;

      const detail = await fetch(`/api/tasks/${latest.id}`).then((res) => res.json());
      const tab = detail.type === "tryon"
        ? "tryon"
        : detail.type === "video"
          ? "video"
          : "restyle";
      applyTab(tab);
      state.taskId = latest.id;
      els.emptyState.hidden = true;
      setBusy(true);
      const action = detail.type === "tryon"
        ? "试衣"
        : detail.type === "video"
          ? "生成视频"
          : "换装";
      const wait = detail.type === "video" ? "约 1–3 分钟" : "约 30–60 秒";
      showLoading(true, latest.status === "running" ? `正在${action}，${wait}…` : "排队中…");
      renderTask(detail);
      subscribe(latest.id);
    } catch {
      /* 忽略：没有历史任务时保持首屏 */
    }
  }

  /* ── 初始化 ─────────────────────────────────────── */
  function bindChips() {
    document.querySelectorAll("#instructionChips .chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        els.instruction.value = chip.textContent.trim();
        refreshButton();
      });
    });
  }

  function fillSelect(select, values) {
    if (!Array.isArray(values) || !values.length) return;
    const current = select.value;
    select.innerHTML = "";
    values.forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      select.appendChild(option);
    });
    if (values.includes(current)) select.value = current;
  }

  function updateEstimate() {
    const selected = els.model.value;
    const modelId = selected || (state.config && state.config.edit_model) || "";
    const price = modelPrice(modelId);
    const count = Number(els.count.value);

    els.costModel.textContent = selected ? selected : `${modelId}（自动）`;
    if (els.dryRun.checked) {
      els.costEstimate.textContent = "预览免费";
    } else if (price == null) {
      els.costEstimate.textContent = "预计费用待核对";
    } else {
      els.costEstimate.textContent = `预计 ¥${(price * count).toFixed(2)}`;
    }
  }

  async function refreshLedger() {
    try {
      const response = await fetch("/api/costs");
      if (!response.ok) return;
      const summary = await response.json();
      els.ledger.hidden = false;
      els.ledgerTotal.textContent = `¥${Number(summary.total_amount || 0).toFixed(2)}`;
      els.ledgerMeta.textContent = `${summary.calls || 0} 次 · ${summary.total_images || 0} 张`;
    } catch {
      /* 台账不可用时保持隐藏 */
    }
  }

  async function loadConfig() {
    try {
      const response = await fetch("/api/config");
      const config = await response.json();
      state.config = config;

      const badge = $("#providerBadge");
      if (config.dashscope_configured) {
        badge.textContent = "百炼已连接";
        badge.className = "badge badge-ok";
      } else {
        badge.textContent = "未配置 API Key";
        badge.className = "badge badge-warn";
      }
      $("#modelTag").textContent = config.edit_model;

      els.model.innerHTML = "";
      const auto = document.createElement("option");
      auto.value = "";
      auto.textContent = `自动（${config.edit_model}，失败降级）`;
      els.model.appendChild(auto);
      (config.models || []).forEach((model) => {
        const option = document.createElement("option");
        option.value = model.id;
        option.textContent = model.price != null
          ? `${model.id} · ¥${Number(model.price).toFixed(2)}/张`
          : model.id;
        els.model.appendChild(option);
      });
      els.model.value = "";

      const tryonAvailability = Object.fromEntries(
        (config.tryon_methods || []).map((item) => [item.id, item.available])
      );
      Array.from(els.tryonMethod.options).forEach((option) => {
        option.disabled = tryonAvailability[option.value] === false;
      });
      if (els.tryonMethod.selectedOptions[0] && els.tryonMethod.selectedOptions[0].disabled) {
        els.tryonMethod.value = "auto";
      }

      const engine = config.tryon_engine || "edit";
      const autoOption = els.tryonMethod.querySelector('option[value="auto"]');
      const qwenOption = els.tryonMethod.querySelector('option[value="qwen"]');
      if (autoOption) {
        autoOption.textContent = engine === "edit"
          ? "自动（有方舟走 Seedream，否则百炼图像编辑）"
          : "自动（有方舟走 Seedream，否则百炼试衣）";
      }
      if (qwenOption) {
        qwenOption.textContent = engine === "edit"
          ? "百炼图像编辑（qwen-image，推荐）"
          : "百炼 AI 试衣（aitryon-plus）";
      }

      if (config.stylist_model) els.styleModelLabel.textContent = config.stylist_model;
      const stylistOptions = config.stylist_options || {};
      fillSelect(els.styleOccasion, stylistOptions.occasions);
      fillSelect(els.styleSeason, stylistOptions.seasons);
      fillSelect(els.stylePalette, stylistOptions.palettes);

      els.balanceButton.hidden = !config.balance_ui_enabled;

      if (config.video_model) els.videoModelLabel.textContent = config.video_model;
      const seedanceOption = els.videoMethod.querySelector('option[value="seedance"]');
      if (seedanceOption) {
        seedanceOption.disabled = !config.ark_configured;
      }
      if (!config.ark_configured && els.videoMethod.value === "seedance") {
        els.videoMethod.value = "auto";
      }

      updateEstimate();
      updateTryonEstimate();
      updateVideoEstimate();
    } catch {
      $("#providerBadge").textContent = "服务未就绪";
    }
  }

  setupDropzone(els.personDrop, els.personInput, "person", els.personPreview, els.personRemove);
  setupDropzone(els.garmentDrop, els.garmentInput, "garment", els.garmentPreview, els.garmentRemove);
  setupDropzone(els.tryonPersonDrop, els.tryonPersonInput, "tryonPerson",
    els.tryonPersonPreview, els.tryonPersonRemove);
  setupDropzone(els.tryonGarmentDrop, els.tryonGarmentInput, "tryonGarment",
    els.tryonGarmentPreview, els.tryonGarmentRemove);
  setupDropzone(els.tryonBottomDrop, els.tryonBottomInput, "tryonBottom",
    els.tryonBottomPreview, els.tryonBottomRemove);
  setupDropzone(els.videoDrop, els.videoInput, "video",
    els.videoPreview, els.videoRemove);

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });

  els.restyleModelPick.addEventListener("click", () => openModelPicker("person"));
  els.tryonModelPick.addEventListener("click", () => openModelPicker("tryonPerson"));
  els.modelClose.addEventListener("click", closeModelPicker);
  els.modelModal.addEventListener("click", (event) => {
    if (event.target.closest("[data-close-model]")) closeModelPicker();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (!els.modelModal.hidden) closeModelPicker();
    if (!els.balanceModal.hidden) closeBalanceModal();
  });

  els.balanceButton.addEventListener("click", openBalanceModal);
  els.balanceClose.addEventListener("click", closeBalanceModal);
  els.balanceModal.addEventListener("click", (event) => {
    if (event.target.closest("[data-close-balance]")) closeBalanceModal();
  });
  els.balanceRefresh.addEventListener("click", loadBalance);

  els.balanceBody.addEventListener("submit", async (event) => {
    if (event.target.id !== "balanceConfigForm") return;
    event.preventDefault();
    const keyId = els.balanceBody.querySelector("#balanceKeyId").value.trim();
    const secret = els.balanceBody.querySelector("#balanceKeySecret").value.trim();
    if (!keyId || !secret) {
      els.balanceError.textContent = "请填写 AccessKey ID 和 AccessKey Secret";
      els.balanceError.hidden = false;
      return;
    }
    try {
      const response = await fetch("/api/balance/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ access_key_id: keyId, access_key_secret: secret }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "保存失败");
      await loadBalance();
      if (data.warning) {
        els.balanceError.textContent = data.warning;
        els.balanceError.hidden = false;
      }
    } catch (error) {
      els.balanceError.textContent = error.message;
      els.balanceError.hidden = false;
    }
  });

  els.balanceBody.addEventListener("click", async (event) => {
    if (!event.target.closest("#balanceClearKey")) return;
    if (!window.confirm("确定清除本机保存的 AccessKey？")) return;
    try {
      const response = await fetch("/api/balance/config", { method: "DELETE" });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "清除失败");
      await loadBalance();
    } catch (error) {
      els.balanceError.textContent = error.message;
      els.balanceError.hidden = false;
    }
  });
  els.modelFilters.addEventListener("click", (event) => {
    const button = event.target.closest("[data-filter]");
    if (!button) return;
    state.modelFilter = button.dataset.filter;
    els.modelFilters.querySelectorAll(".chip").forEach((chip) => {
      chip.classList.toggle("active", chip === button);
    });
    renderModels();
  });
  els.modelGrid.addEventListener("click", (event) => {
    const card = event.target.closest("[data-model-id]");
    if (card) chooseModel(card.dataset.modelId);
  });

  els.historyGrid.addEventListener("click", (event) => {
    const deleteImageButton = event.target.closest(".thumb-del");
    if (deleteImageButton) {
      deleteHistoryImage(
        deleteImageButton.dataset.taskId,
        Number(deleteImageButton.dataset.index)
      );
      return;
    }
    const deleteTaskButton = event.target.closest(".history-delete");
    if (deleteTaskButton) {
      deleteHistoryTask(deleteTaskButton.dataset.taskId);
    }
  });
  els.historyRefresh.addEventListener("click", loadHistory);

  els.styleGenerate.addEventListener("click", submitStylist);
  els.videoGenerate.addEventListener("click", submitVideo);
  els.videoDuration.addEventListener("change", updateVideoEstimate);
  els.videoResolution.addEventListener("change", updateVideoEstimate);
  els.videoMethod.addEventListener("change", updateVideoEstimate);
  els.videoDryRun.addEventListener("change", updateVideoEstimate);
  els.styleGrid.addEventListener("click", (event) => {
    const useButton = event.target.closest(".style-use");
    if (useButton) {
      useScheme(Number(useButton.dataset.index));
      return;
    }
    const copyButton = event.target.closest(".style-copy");
    if (copyButton) copyScheme(Number(copyButton.dataset.index));
  });
  els.exportLookbook.addEventListener("click", () => {
    if (!state.currentTaskId) return;
    window.location.href = `/api/lookbook/${encodeURIComponent(state.currentTaskId)}`;
  });

  els.instruction.addEventListener("input", refreshButton);
  els.model.addEventListener("change", updateEstimate);
  els.count.addEventListener("change", updateEstimate);
  els.dryRun.addEventListener("change", updateEstimate);
  els.tryonPart.addEventListener("change", () => {
    refreshButton();
    updateTryonEstimate();
  });
  els.tryonCount.addEventListener("change", updateTryonEstimate);
  els.tryonMethod.addEventListener("change", updateTryonEstimate);
  els.tryonDryRun.addEventListener("change", updateTryonEstimate);
  els.generate.addEventListener("click", submitRestyle);
  els.tryonGenerate.addEventListener("click", submitTryon);
  els.copyPrompt.addEventListener("click", async (event) => {
    event.preventDefault();
    try {
      await navigator.clipboard.writeText(els.promptText.textContent || "");
      els.copyPrompt.textContent = "已复制";
      setTimeout(() => { els.copyPrompt.textContent = "复制"; }, 1500);
    } catch {
      showError("复制失败，请手动选择文本");
    }
  });

  bindChips();
  refreshButton();
  loadConfig();
  refreshLedger();
  const initialTab = new URLSearchParams(location.search).get("tab");
  if (initialTab === "tryon") {
    switchTab("tryon");
  } else if (initialTab === "stylist") {
    switchTab("stylist");
  } else if (initialTab === "video") {
    switchTab("video");
  } else if (initialTab === "history") {
    switchTab("history");
  }
  resumeLatest();
})();
