(() => {
  "use strict";

  const STORAGE_KEY = "muchen-newcomer-village-isolated-draft-v1";
  const steps = ["arrival", "context-review", "action-plan", "action-check", "evidence-capture", "receipt"];
  const stepNames = ["抵达新手村", "读取融入起点", "选择真实行动", "完成真实协作", "留下证据草稿", "核对本地回执"];
  const actionLabels = {
    "align-role-expectation": "与角色负责人确认一项当前优先事项及完成标准",
    "confirm-collaboration-rhythm": "与一位协作伙伴确认更新渠道、节奏与需要提前同步的风险",
    "restate-team-decision": "阅读一条近期团队决策记录，并向相关角色复述自己的下一步",
  };

  const screens = [...document.querySelectorAll("[data-screen]")];
  const stepLabel = document.querySelector("#step-label");
  const stepName = document.querySelector("#step-name");
  const progressBar = document.querySelector("#progress-bar");
  const liveRegion = document.querySelector("#live-region");
  const actionForm = document.querySelector("#action-form");
  const evidenceForm = document.querySelector("#evidence-form");
  let draft = loadDraft();

  function emptyDraft() {
    return { screen: "arrival", action: "", actionTime: "", evidenceKind: "", counterpartRole: "", observation: "", repeatBehavior: "", privacyAttestation: false };
  }

  function loadDraft() {
    try {
      const saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY));
      if (!saved || !steps.includes(saved.screen)) return emptyDraft();
      return { ...emptyDraft(), ...saved };
    } catch {
      return emptyDraft();
    }
  }

  function saveDraft() {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
    } catch {
      liveRegion.textContent = "浏览器未保存临时草稿；你仍可继续当前演练。";
    }
  }

  function showScreen(screenId, options = {}) {
    const index = steps.indexOf(screenId);
    if (index < 0) return;
    screens.forEach((screen) => {
      const active = screen.dataset.screen === screenId;
      screen.hidden = !active;
      screen.classList.toggle("is-active", active);
    });
    draft.screen = screenId;
    stepLabel.textContent = `第 ${index + 1} 步，共 ${steps.length} 步`;
    stepName.textContent = stepNames[index];
    progressBar.style.width = `${((index + 1) / steps.length) * 100}%`;
    saveDraft();
    if (options.announce !== false) liveRegion.textContent = `已进入：${stepNames[index]}`;
    const heading = document.querySelector(`[data-screen="${screenId}"] h1, [data-screen="${screenId}"] h2`);
    if (heading && options.focus !== false) {
      heading.setAttribute("tabindex", "-1");
      heading.focus({ preventScroll: true });
      heading.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function hydrateForms() {
    if (draft.action) {
      [...actionForm.elements.action].forEach((input) => { input.checked = input.value === draft.action; });
    }
    actionForm.elements["action-time"].value = draft.actionTime;
    evidenceForm.elements["counterpart-role"].value = draft.counterpartRole;
    evidenceForm.elements.observation.value = draft.observation;
    evidenceForm.elements["repeat-behavior"].value = draft.repeatBehavior;
    evidenceForm.elements["privacy-attestation"].checked = draft.privacyAttestation;
    renderActionTicket();
    renderReceipt();
  }

  function renderActionTicket() {
    document.querySelector("#ticket-action").textContent = actionLabels[draft.action] || "尚未选择行动";
    document.querySelector("#ticket-time").textContent = draft.actionTime || "尚未选择时间";
  }

  function renderReceipt() {
    document.querySelector("#receipt-kind").textContent = draft.evidenceKind || "证据类型待确认";
    document.querySelector("#receipt-action").textContent = actionLabels[draft.action] || "—";
    document.querySelector("#receipt-role").textContent = draft.counterpartRole || "—";
    document.querySelector("#receipt-observation").textContent = draft.observation || "—";
    document.querySelector("#receipt-repeat").textContent = draft.repeatBehavior || "—";
  }

  document.addEventListener("click", (event) => {
    const nextButton = event.target.closest("[data-next]");
    if (nextButton) showScreen(nextButton.dataset.next);
    const backButton = event.target.closest("[data-back]");
    if (backButton) showScreen(backButton.dataset.back);
  });

  actionForm.addEventListener("input", () => {
    draft.action = actionForm.elements.action.value;
    draft.actionTime = actionForm.elements["action-time"].value;
    const selectedInput = actionForm.querySelector("input[name=action]:checked");
    draft.evidenceKind = selectedInput?.dataset.evidenceKind || "";
    document.querySelector("#action-error").hidden = true;
    saveDraft();
  });

  actionForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const error = document.querySelector("#action-error");
    if (!draft.action || !draft.actionTime) {
      error.hidden = false;
      error.focus();
      return;
    }
    error.hidden = true;
    renderActionTicket();
    showScreen("action-check");
  });

  evidenceForm.addEventListener("input", () => {
    draft.counterpartRole = evidenceForm.elements["counterpart-role"].value;
    draft.observation = evidenceForm.elements.observation.value.trim();
    draft.repeatBehavior = evidenceForm.elements["repeat-behavior"].value.trim();
    draft.privacyAttestation = evidenceForm.elements["privacy-attestation"].checked;
    document.querySelector("#evidence-error").hidden = true;
    saveDraft();
  });

  evidenceForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const error = document.querySelector("#evidence-error");
    const valid = draft.counterpartRole && draft.observation.length >= 12 && draft.repeatBehavior.length >= 12 && draft.privacyAttestation;
    if (!valid) {
      error.hidden = false;
      error.focus();
      return;
    }
    error.hidden = true;
    renderReceipt();
    showScreen("receipt");
  });

  document.querySelector("#restart-button").addEventListener("click", () => {
    sessionStorage.removeItem(STORAGE_KEY);
    draft = emptyDraft();
    actionForm.reset();
    evidenceForm.reset();
    renderActionTicket();
    renderReceipt();
    showScreen("arrival");
  });

  hydrateForms();
  showScreen(draft.screen, { announce: false, focus: false });
})();
