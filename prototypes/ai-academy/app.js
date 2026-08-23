(() => {
  "use strict";

  const stage = document.querySelector("#step-panel");
  const loadingState = document.querySelector("[data-loading-state]");
  const loadError = document.querySelector("[data-load-error]");
  const panels = [...document.querySelectorAll("[data-step]")];
  const indicators = [...document.querySelectorAll("[data-step-indicator]")];
  const responseValues = {};
  let fixture;
  let currentStep = 1;
  let learningExpanded = false;

  const setText = (selector, value) => {
    const element = document.querySelector(selector);
    if (element) element.textContent = value;
  };

  const updateProgress = () => {
    indicators.forEach((indicator, index) => {
      const step = index + 1;
      const status = indicator.querySelector("small");
      indicator.classList.toggle("is-complete", step < currentStep);
      if (step === currentStep) {
        indicator.setAttribute("aria-current", "step");
        status.textContent = "当前";
      } else {
        indicator.removeAttribute("aria-current");
        status.textContent = step < currentStep ? "已完成" : "未开始";
      }
    });
  };

  const showStep = (step) => {
    currentStep = step;
    panels.forEach((panel) => {
      panel.hidden = Number(panel.dataset.step) !== step;
    });
    updateProgress();
    stage.focus({ preventScroll: true });
    stage.scrollIntoView({ block: "start", behavior: "smooth" });
  };

  const createMethodCards = () => {
    const grid = document.querySelector("[data-method-grid]");
    grid.replaceChildren();
    fixture.learning_input.parts.forEach((part) => {
      const card = document.createElement("article");
      card.className = "method-card";
      const title = document.createElement("strong");
      const prompt = document.createElement("p");
      title.textContent = part.label;
      prompt.textContent = part.prompt;
      card.append(title, prompt);
      grid.append(card);
    });
  };

  const createPracticeFields = () => {
    const container = document.querySelector("[data-practice-fields]");
    container.replaceChildren();
    fixture.practice.fields.forEach((field, index) => {
      const wrapper = document.createElement("div");
      wrapper.className = "field";
      const label = document.createElement("label");
      const textarea = document.createElement("textarea");
      const meta = document.createElement("div");
      const hint = document.createElement("span");
      const count = document.createElement("span");
      const error = document.createElement("span");
      const id = `practice-${field.key}`;

      label.htmlFor = id;
      label.textContent = `${index + 1}. ${field.label}`;
      textarea.id = id;
      textarea.name = field.key;
      textarea.rows = 4;
      textarea.required = true;
      textarea.minLength = field.minimum;
      textarea.setAttribute("aria-describedby", `${id}-hint ${id}-error`);
      textarea.autocomplete = "off";
      hint.id = `${id}-hint`;
      hint.textContent = field.hint;
      count.textContent = `0 / 至少 ${field.minimum} 字`;
      error.id = `${id}-error`;
      error.className = "field-error";
      error.hidden = true;
      meta.className = "field-meta";
      meta.append(hint, count);

      textarea.addEventListener("input", () => {
        const length = textarea.value.trim().length;
        count.textContent = `${length} / 至少 ${field.minimum} 字`;
        if (length >= field.minimum) {
          textarea.removeAttribute("aria-invalid");
          error.hidden = true;
        }
      });

      wrapper.append(label, textarea, meta, error);
      container.append(wrapper);
    });
  };

  const populateFixture = () => {
    setText("[data-person-name]", fixture.person.display_name);
    setText("[data-person-goal]", fixture.person.capability_goal);
    setText("[data-role-name]", fixture.role.display_name);
    setText("[data-role-requirement]", fixture.role.capability_requirement);
    setText("[data-learning-title]", fixture.learning_input.title);
    setText("[data-learning-summary]", fixture.learning_input.summary);
    setText("[data-practice-title]", fixture.practice.title);
    setText("[data-practice-scenario]", fixture.practice.scenario);
    createMethodCards();
    createPracticeFields();
  };

  const loadFixture = async () => {
    stage.setAttribute("aria-busy", "true");
    loadingState.hidden = false;
    loadError.hidden = true;
    panels.forEach((panel) => { panel.hidden = true; });

    try {
      const response = await fetch("./synthetic-fixture.json", { cache: "no-store" });
      if (!response.ok) throw new Error("fixture response was not successful");
      const data = await response.json();
      if (data.fixture_type !== "SYNTHETIC_LEARNING_FIXTURE" || data.formal_course !== false) {
        throw new Error("fixture boundary is invalid");
      }
      fixture = data;
      populateFixture();
      loadingState.hidden = true;
      stage.setAttribute("aria-busy", "false");
      showStep(1);
    } catch (_error) {
      loadingState.hidden = true;
      loadError.hidden = false;
      stage.setAttribute("aria-busy", "false");
    }
  };

  document.querySelector("[data-retry]").addEventListener("click", loadFixture);
  document.querySelector("[data-complete-goal]").addEventListener("click", () => showStep(2));

  document.querySelector("[data-learning-action]").addEventListener("click", (event) => {
    const grid = document.querySelector("[data-method-grid]");
    const cover = document.querySelector("[data-method-cover]");
    if (!learningExpanded) {
      learningExpanded = true;
      grid.hidden = false;
      cover.hidden = true;
      event.currentTarget.innerHTML = '我已完成这份学习输入 <span aria-hidden="true">→</span>';
      grid.scrollIntoView({ block: "nearest", behavior: "smooth" });
      return;
    }
    showStep(3);
  });

  document.querySelector("[data-practice-form]").addEventListener("submit", (event) => {
    event.preventDefault();
    const errorSummary = document.querySelector("[data-error-summary]");
    const fields = fixture.practice.fields;
    let firstInvalid;

    fields.forEach((field) => {
      const textarea = document.querySelector(`#practice-${field.key}`);
      const error = document.querySelector(`#practice-${field.key}-error`);
      const value = textarea.value.trim();
      const valid = value.length >= field.minimum;
      textarea.setAttribute("aria-invalid", String(!valid));
      error.hidden = valid;
      error.textContent = valid ? "" : `请至少写 ${field.minimum} 个字，当前 ${value.length} 个字。`;
      if (!valid && !firstInvalid) firstInvalid = textarea;
      if (valid) responseValues[field.key] = value;
    });

    if (firstInvalid) {
      errorSummary.hidden = false;
      errorSummary.focus();
      firstInvalid.focus();
      return;
    }

    errorSummary.hidden = true;
    const evidence = document.querySelector("[data-evidence-inputs]");
    evidence.replaceChildren();
    fields.forEach((field) => {
      const row = document.createElement("div");
      const term = document.createElement("dt");
      const description = document.createElement("dd");
      term.textContent = field.label;
      description.textContent = responseValues[field.key];
      row.append(term, description);
      evidence.append(row);
    });
    showStep(4);
  });

  document.querySelector("[data-restart]").addEventListener("click", () => {
    Object.keys(responseValues).forEach((key) => { delete responseValues[key]; });
    learningExpanded = false;
    document.querySelector("[data-method-grid]").hidden = true;
    document.querySelector("[data-method-cover]").hidden = false;
    document.querySelector("[data-learning-action]").innerHTML = '展开完整学习输入 <span aria-hidden="true">↓</span>';
    createPracticeFields();
    showStep(1);
  });

  loadFixture();
})();
