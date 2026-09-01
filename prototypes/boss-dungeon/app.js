(() => {
  "use strict";

  const STORAGE_KEY = "muchen-boss-dungeon-synthetic-v1";
  const order = ["briefing", "safety", "team", "decision", "receipt"];
  const stages = [...document.querySelectorAll("[data-stage]")];
  const progressItems = [...document.querySelectorAll("[data-progress]")];
  const liveRegion = document.querySelector("#app-status");
  const state = loadState();

  function emptyState() {
    return { stage: "briefing", safetyConfirmed: false, role: "", teamConfirmed: false, decision: "", evidence: "", constraint: "", rationale: "" };
  }

  function loadState() {
    if (new URLSearchParams(window.location.search).has("reset")) {
      sessionStorage.removeItem(STORAGE_KEY);
      history.replaceState({}, "", window.location.pathname);
      return emptyState();
    }

    try {
      const saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "null");
      return saved && order.includes(saved.stage) ? { ...emptyState(), ...saved } : emptyState();
    } catch {
      return emptyState();
    }
  }

  function saveState() {
    try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch { /* The prototype remains usable without storage. */ }
  }

  function renderProgress(stageName) {
    const activeIndex = order.indexOf(stageName);
    progressItems.forEach((item, index) => {
      item.classList.toggle("is-complete", index < activeIndex);
      if (index === activeIndex) item.setAttribute("aria-current", "step");
      else item.removeAttribute("aria-current");
    });
  }

  function hydrateForms() {
    const safety = document.querySelector('[name="safety-confirmed"]');
    const team = document.querySelector('[name="team-confirmed"]');
    const role = document.querySelector(`[name="role"][value="${CSS.escape(state.role)}"]`);
    const decision = document.querySelector(`[name="decision"][value="${CSS.escape(state.decision)}"]`);
    safety.checked = state.safetyConfirmed;
    team.checked = state.teamConfirmed;
    if (role) role.checked = true;
    if (decision) decision.checked = true;
    document.querySelector('[name="evidence"]').value = state.evidence;
    document.querySelector('[name="constraint"]').value = state.constraint;
    document.querySelector('[name="rationale"]').value = state.rationale;
    updateCount();
    renderReceipt();
  }

  function showStage(stageName, announce = true) {
    const target = stages.find((stage) => stage.dataset.stage === stageName);
    if (!target) return;
    stages.forEach((stage) => { stage.hidden = stage !== target; stage.removeAttribute("aria-busy"); });
    state.stage = stageName;
    saveState();
    renderProgress(stageName);
    if (stageName === "receipt") renderReceipt();
    if (announce) {
      liveRegion.textContent = `已进入第 ${order.indexOf(stageName) + 1} 步，共 ${order.length} 步。`;
      target.querySelector("h2")?.focus({ preventScroll: true });
      target.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    }
  }

  function transitionTo(stageName) {
    const current = stages.find((stage) => !stage.hidden);
    current?.setAttribute("aria-busy", "true");
    liveRegion.textContent = "正在切换演练状态。";
    const delay = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 180;
    window.setTimeout(() => showStage(stageName), delay);
  }

  function showError(name, message) {
    const error = document.querySelector(`[data-error="${name}"]`);
    error.textContent = message;
    error.hidden = false;
    error.focus();
  }

  function clearError(name) {
    document.querySelector(`[data-error="${name}"]`).hidden = true;
  }

  function updateCount() {
    const length = document.querySelector('[name="rationale"]').value.trim().length;
    document.querySelector("[data-count]").textContent = `${length} / 20`;
  }

  function renderReceipt() {
    const values = {
      decision: state.decision || "—",
      evidence: state.evidence || "—",
      constraint: state.constraint || "—",
      rationale: state.rationale || "—",
      role: state.role || "—"
    };
    Object.entries(values).forEach(([key, value]) => {
      document.querySelector(`[data-receipt="${key}"]`).textContent = value;
    });
  }

  document.querySelector("[data-next='safety']").addEventListener("click", () => transitionTo("safety"));

  document.querySelector('[data-form="safety"]').addEventListener("submit", (event) => {
    event.preventDefault();
    const checked = event.currentTarget.elements["safety-confirmed"].checked;
    if (!checked) return showError("safety", "请先确认合成模拟与用途边界。真实人员决定不属于本演练。 ");
    clearError("safety");
    state.safetyConfirmed = true;
    transitionTo("team");
  });

  document.querySelector('[data-form="team"]').addEventListener("submit", (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const role = data.get("role")?.toString() || "";
    const confirmed = data.get("team-confirmed") === "on";
    if (!role || !confirmed) return showError("team", "请选择本人模拟角色，并确认四个角色和时间、范围、隐私三项约束。 ");
    clearError("team");
    state.role = role;
    state.teamConfirmed = true;
    transitionTo("decision");
  });

  document.querySelector('[name="rationale"]').addEventListener("input", updateCount);

  document.querySelector('[data-form="decision"]').addEventListener("submit", (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const decision = data.get("decision")?.toString() || "";
    const evidence = data.get("evidence")?.toString() || "";
    const constraint = data.get("constraint")?.toString() || "";
    const rationale = data.get("rationale")?.toString().trim() || "";
    if (!decision || !evidence || !constraint || rationale.length < 20) {
      return showError("decision", "请完成方案、证据、约束和不少于 20 个字符的理由，才能生成可核对回执。 ");
    }
    clearError("decision");
    Object.assign(state, { decision, evidence, constraint, rationale });
    transitionTo("receipt");
  });

  document.querySelector("[data-reset]").addEventListener("click", () => {
    sessionStorage.removeItem(STORAGE_KEY);
    Object.assign(state, emptyState());
    document.querySelectorAll("form").forEach((form) => form.reset());
    document.querySelectorAll("[data-error]").forEach((error) => { error.hidden = true; });
    hydrateForms();
    showStage("briefing");
  });

  hydrateForms();
  showStage(state.stage, false);
})();
