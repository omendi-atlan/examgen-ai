(() => {
  "use strict";

  const state = {
    apiBase: "",
    token: "",
    workspaceId: "",
    subjectId: "",
    examId: "",
    activeAttempt: null,
    submitting: false,
    responses: {},
    saveTimers: new Map(),
    savePromises: new Map(),
    timerId: null,
    lastFinalisedAttempt: "",
  };

  const byId = (id) => document.getElementById(id);
  const setStatus = (message, isError = false) => {
    const node = byId("global-status");
    node.textContent = message;
    node.classList.toggle("error", isError);
  };
  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const api = async (path, options = {}) => {
    const response = await fetch(state.apiBase.replace(/\/$/, "") + "/api/v1" + path, {
      ...options,
      headers: {
        ...(options.headers || {}),
        ...(state.token ? { Authorization: "Bearer " + state.token } : {}),
      },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "The request could not be completed.");
    return data;
  };
  const jsonOptions = (method, body) => ({
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const fillSelect = (select, items, placeholder, label) => {
    select.replaceChildren(new Option(placeholder, ""));
    for (const item of items) select.add(new Option(label(item), item.id));
    select.disabled = items.length === 0;
  };

  async function signIn(event) {
    event.preventDefault();
    state.apiBase = byId("api-base").value.trim();
    byId("login-button").disabled = true;
    setStatus("Signing in…");
    try {
      const response = await fetch(state.apiBase.replace(/\/$/, "") + "/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: byId("email").value, password: byId("password").value }),
      });
      const data = await response.json();
      if (!response.ok || !data.access_token) throw new Error(data.detail || "Sign-in failed.");
      state.token = data.access_token;
      byId("password").value = "";
      const workspaces = await api("/workspaces");
      fillSelect(byId("workspace-select"), workspaces, "Choose workspace", (item) => item.name);
      byId("account-panel").hidden = true;
      byId("selection-panel").hidden = false;
      setStatus("Signed in. Select your coursework workspace and subject.");
    } catch (error) {
      setStatus(error.message || "Sign-in failed.", true);
    } finally {
      byId("login-button").disabled = false;
    }
  }

  async function clearAttemptView() {
    if (state.activeAttempt?.status === "in_progress" && !state.submitting) {
      try {
        await flushResponses();
      } catch (error) {
        setStatus("Some responses may not have saved before leaving this attempt: " + error.message, true);
      }
    }
    if (state.timerId) window.clearInterval(state.timerId);
    state.timerId = null;
    for (const timer of state.saveTimers.values()) window.clearTimeout(timer);
    state.saveTimers.clear();
    state.activeAttempt = null;
    state.responses = {};
  }

  async function loadSubjects() {
    await clearAttemptView();
    state.workspaceId = byId("workspace-select").value;
    state.subjectId = "";
    state.examId = "";
    byId("subject-select").disabled = true;
    byId("exam-select").disabled = true;
    byId("history-panel").hidden = true;
    byId("attempt-panel").hidden = true;
    if (!state.workspaceId) return;
    try {
      const subjects = await api("/workspaces/" + state.workspaceId + "/subjects");
      fillSelect(byId("subject-select"), subjects, "Choose subject", (item) => item.name);
    } catch (error) {
      setStatus(error.message, true);
    }
  }

  async function loadExams() {
    await clearAttemptView();
    state.subjectId = byId("subject-select").value;
    state.examId = "";
    byId("exam-select").disabled = true;
    byId("history-panel").hidden = true;
    byId("attempt-panel").hidden = true;
    if (!state.subjectId) return;
    try {
      const exams = await api("/workspaces/" + state.workspaceId + "/subjects/" + state.subjectId + "/practice-exams");
      fillSelect(
        byId("exam-select"),
        exams,
        "Choose practice examination",
        (item) => item.title + " · " + item.total_marks + " marks",
      );
      setStatus(exams.length ? "Choose an exam to see your attempts." : "No practice examinations yet. Build one from your question bank.");
    } catch (error) {
      setStatus(error.message, true);
    }
  }

  async function loadHistory() {
    await clearAttemptView();
    state.examId = byId("exam-select").value;
    byId("attempt-panel").hidden = true;
    if (!state.examId) {
      byId("history-panel").hidden = true;
      return;
    }
    try {
      const attempts = await api(
        "/workspaces/" + state.workspaceId + "/subjects/" + state.subjectId +
        "/practice-exams/" + state.examId + "/attempts",
      );
      const history = byId("attempt-history");
      history.replaceChildren();
      for (const attempt of attempts) {
        const row = element("div", "history-item");
        const details = element("div");
        details.append(
          element("strong", "", attempt.status.replaceAll("_", " ")),
          element("small", "", new Date(attempt.started_at).toLocaleString() + " · " + attempt.awarded_marks + "/" + attempt.total_marks + " marks"),
        );
        const button = element("button", "", attempt.status === "in_progress" ? "Resume" : "Review");
        button.type = "button";
        button.addEventListener("click", () => openAttempt(attempt.id));
        row.append(details, button);
        history.append(row);
      }
      byId("history-panel").hidden = false;
      byId("start-button").disabled = false;
      setStatus(attempts.length ? "Select an attempt to resume or review, or start another." : "No attempts yet. Start when you are ready.");
    } catch (error) {
      setStatus(error.message, true);
    }
  }

  async function startAttempt() {
    if (!state.examId) return;
    byId("start-button").disabled = true;
    try {
      const attempt = await api(
        "/workspaces/" + state.workspaceId + "/subjects/" + state.subjectId +
        "/practice-exams/" + state.examId + "/attempts",
        { method: "POST" },
      );
      activateAttempt(attempt);
      setStatus("Your timed practice attempt has started. The server controls the deadline.");
    } catch (error) {
      setStatus(error.message, true);
    } finally {
      byId("start-button").disabled = false;
    }
  }

  async function openAttempt(attemptId) {
    try {
      const attempt = await api(
        "/workspaces/" + state.workspaceId + "/subjects/" + state.subjectId +
        "/practice-attempts/" + attemptId,
      );
      activateAttempt(attempt);
    } catch (error) {
      setStatus(error.message, true);
    }
  }

  function activateAttempt(attempt) {
    state.activeAttempt = attempt;
    state.responses = {};
    for (const question of attempt.questions) {
      state.responses[question.exam_question_id] = question.response || {};
    }
    state.lastFinalisedAttempt = "";
    byId("attempt-panel").hidden = false;
    renderAttempt();
    if (state.timerId) window.clearInterval(state.timerId);
    if (attempt.status === "in_progress") {
      state.timerId = window.setInterval(updateTimer, 1000);
      updateTimer();
    } else {
      byId("timer").textContent = attempt.status;
      byId("timer-caption").textContent = "Attempt finalised";
    }
  }

  function updateTimer() {
    const attempt = state.activeAttempt;
    if (!attempt || attempt.status !== "in_progress") return;
    const remaining = Math.max(0, Math.floor((Date.parse(attempt.expires_at) - Date.now()) / 1000));
    const minutes = String(Math.floor(remaining / 60)).padStart(2, "0");
    const seconds = String(remaining % 60).padStart(2, "0");
    byId("timer").textContent = minutes + ":" + seconds;
    byId("timer").classList.toggle("warning", remaining < 300);
    if (remaining === 0 && state.lastFinalisedAttempt !== attempt.id) {
      state.lastFinalisedAttempt = attempt.id;
      if (state.timerId) window.clearInterval(state.timerId);
      openAttempt(attempt.id).then(() => setStatus("The server deadline passed and your attempt was finalised."));
    }
  }

  function updateResponse(questionId, response) {
    state.responses[questionId] = response;
    byId("save-indicator").textContent = "Changes pending autosave…";
    if (state.saveTimers.has(questionId)) window.clearTimeout(state.saveTimers.get(questionId));
    const timer = window.setTimeout(() => saveResponse(questionId), 650);
    state.saveTimers.set(questionId, timer);
  }

  async function saveResponse(questionId) {
    const attempt = state.activeAttempt;
    if (!attempt || attempt.status !== "in_progress") return;
    state.saveTimers.delete(questionId);
    const inFlight = state.savePromises.get(questionId);
    if (inFlight) {
      await inFlight;
      if (state.activeAttempt?.id === attempt.id && state.activeAttempt.status === "in_progress") {
        return saveResponse(questionId);
      }
      return;
    }

    const snapshot = JSON.stringify(state.responses[questionId] || {});
    const task = api(
      "/workspaces/" + state.workspaceId + "/subjects/" + state.subjectId +
      "/practice-attempts/" + attempt.id + "/responses/" + questionId,
      jsonOptions("PUT", { response: JSON.parse(snapshot) }),
    );
    state.savePromises.set(questionId, task);
    try {
      await task;
      byId("save-indicator").textContent = state.saveTimers.size ? "Saving responses…" : "All responses saved";
    } catch (error) {
      byId("save-indicator").textContent = "Autosave issue: " + error.message;
      if (error.message.toLowerCase().includes("expired")) {
        await openAttempt(attempt.id);
      }
    } finally {
      if (state.savePromises.get(questionId) === task) state.savePromises.delete(questionId);
    }

    if (
      state.activeAttempt?.id === attempt.id &&
      state.activeAttempt.status === "in_progress" &&
      JSON.stringify(state.responses[questionId] || {}) !== snapshot
    ) {
      const timer = window.setTimeout(() => saveResponse(questionId), 150);
      state.saveTimers.set(questionId, timer);
    }
  }

  async function flushResponses() {
    const attempt = state.activeAttempt;
    if (!attempt) return;
    await Promise.all([...state.savePromises.values()]);
    if (state.activeAttempt?.id !== attempt.id || state.activeAttempt.status !== "in_progress") {
      throw new Error("The practice attempt has already been finalised.");
    }
    for (const question of attempt.questions) {
      if (state.saveTimers.has(question.exam_question_id)) {
        window.clearTimeout(state.saveTimers.get(question.exam_question_id));
        state.saveTimers.delete(question.exam_question_id);
      }
      await api(
        "/workspaces/" + state.workspaceId + "/subjects/" + state.subjectId +
        "/practice-attempts/" + attempt.id + "/responses/" + question.exam_question_id,
        jsonOptions("PUT", { response: state.responses[question.exam_question_id] || {} }),
      );
    }
  }

  async function submitAttempt() {
    const attempt = state.activeAttempt;
    if (!attempt || attempt.status !== "in_progress") return;
    state.submitting = true;
    byId("submit-button").disabled = true;
    renderAttempt();
    try {
      await flushResponses();
      const result = await api(
        "/workspaces/" + state.workspaceId + "/subjects/" + state.subjectId +
        "/practice-attempts/" + attempt.id + "/submit",
        { method: "POST" },
      );
      await loadHistory();
      activateAttempt(result);
      setStatus(result.status === "expired"
        ? "The server deadline had passed. Your attempt was finalised."
        : "Attempt submitted. Review your score and model answers.");
    } catch (error) {
      setStatus(error.message || "Submission failed.", true);
      await openAttempt(attempt.id);
    } finally {
      state.submitting = false;
      byId("submit-button").disabled = false;
      if (state.activeAttempt?.status === "in_progress") renderAttempt();
    }
  }

  function renderResponse(question, card) {
    const response = state.responses[question.exam_question_id] || {};
    const disabled = state.activeAttempt.status !== "in_progress" || state.submitting;
    const options = question.options || [];
    const update = (next) => updateResponse(question.exam_question_id, next);
    if (["multiple_choice", "true_false"].includes(question.question_type)) {
      const list = element("div", "option-list");
      for (const option of options) {
        const label = element("label", "option");
        const input = element("input");
        input.type = "radio";
        input.name = "question-" + question.exam_question_id;
        input.value = option.id;
        input.checked = response.option_id === option.id;
        input.disabled = disabled;
        input.addEventListener("change", () => update({ option_id: option.id }));
        label.append(input, element("span", "", option.id + ". " + option.text));
        list.append(label);
      }
      card.append(list);
      return;
    }
    if (question.question_type === "multiple_select") {
      const list = element("div", "option-list");
      const selected = Array.isArray(response.option_ids) ? response.option_ids : [];
      for (const option of options) {
        const label = element("label", "option");
        const input = element("input");
        input.type = "checkbox";
        input.checked = selected.includes(option.id);
        input.disabled = disabled;
        input.addEventListener("change", () => update({
          option_ids: input.checked ? [...selected, option.id] : selected.filter((id) => id !== option.id),
        }));
        label.append(input, element("span", "", option.id + ". " + option.text));
        list.append(label);
      }
      card.append(list);
      return;
    }
    const label = element("label", "response-input", question.question_type === "numeric" ? "Your numeric answer" : "Your response");
    const input = question.question_type === "long_answer" || question.question_type === "programming" ||
      question.question_type === "diagram_interpretation" || question.question_type === "diagram_construction"
      ? element("textarea")
      : element("input");
    if (question.question_type === "numeric") input.type = "number";
    input.disabled = disabled;
    input.value = question.question_type === "numeric"
      ? (typeof response.value === "number" ? String(response.value) : "")
      : (typeof response.text === "string" ? response.text : "");
    input.addEventListener("input", () => {
      if (question.question_type === "numeric") {
        update(input.value === "" ? {} : { value: Number(input.value) });
      } else {
        update({ text: input.value });
      }
    });
    label.append(input);
    card.append(label);
  }

  function renderAttempt() {
    const attempt = state.activeAttempt;
    if (!attempt) return;
    byId("attempt-title").textContent = attempt.exam_title;
    byId("attempt-meta").textContent = attempt.questions.length + " questions · " + attempt.total_marks + " marks";
    byId("submit-row").hidden = attempt.status !== "in_progress";
    byId("result-summary").hidden = attempt.status === "in_progress";
    byId("save-indicator").textContent = attempt.status === "in_progress" ? "All responses saved" : "Attempt finalised";
    const list = byId("question-list");
    list.replaceChildren();
    for (const question of attempt.questions) {
      const card = element("article", "question-card");
      const heading = element("h3");
      heading.append(element("strong", "", "Question " + question.ordinal));
      heading.append(element("span", "", question.marks + " marks · " + question.question_type.replaceAll("_", " ")));
      card.append(heading, element("p", "question-stem", question.stem));
      renderResponse(question, card);
      if (attempt.status !== "in_progress") {
        const review = element("div", "review");
        const mark = question.awarded_marks === undefined ? "Pending review" : question.awarded_marks + "/" + question.marks + " marks";
        review.append(element("p", "", "Marking: " + question.marking_status + " · " + mark));
        if (question.correct_answer) review.append(element("pre", "", "Model answer: " + JSON.stringify(question.correct_answer, null, 2)));
        if (question.explanation) review.append(element("p", "", "Explanation: " + question.explanation));
        card.append(review);
      }
      list.append(card);
    }
    if (attempt.status !== "in_progress") {
      const summary = byId("result-summary");
      summary.replaceChildren(
        element("strong", "", "Final objective score: " + attempt.awarded_marks + "/" + attempt.total_marks),
        element("p", "", attempt.pending_review_count + " written or complex response(s) require further marking."),
      );
    }
  }

  byId("login-form").addEventListener("submit", signIn);
  byId("workspace-select").addEventListener("change", loadSubjects);
  byId("subject-select").addEventListener("change", loadExams);
  byId("exam-select").addEventListener("change", loadHistory);
  byId("start-button").addEventListener("click", startAttempt);
  byId("submit-button").addEventListener("click", submitAttempt);
})();
