/* EXAMGEN AI — interactive examination website runner.
 *
 * Renders every supported question type with the mandated control:
 *   fill-in            -> text box
 *   predefined choice  -> dropdown
 *   multiple answers   -> checkboxes
 * Autosaves responses (debounced + on unload), tracks a countdown against the
 * server deadline, supports flagging, navigation and submission.
 */
(function () {
  "use strict";
  const { api, el, clear, escapeHtml, statusBadge, formatDuration, toast } = window.EXAMGEN;

  const state = {
    attemptId: null,
    workspaceId: null,
    data: null,
    responses: {},
    flags: {},
    current: 0,
    timer: null,
    remaining: null,
    dirty: new Set(),
    saveTimer: null,
    saving: false,
    submitted: false,
    order: {},
  };

  const dom = {};

  document.addEventListener("DOMContentLoaded", init);

  function init() {
    const params = new URLSearchParams(window.location.search);
    state.attemptId = params.get("attempt") || "";
    state.workspaceId = params.get("workspace") || api.store.workspaceId;

    if (!api.store.token) {
      document.getElementById("exam-root").innerHTML =
        '<div class="container-narrow"><div class="alert alert-warn">' +
        "You must sign in to sit this examination.</div>" +
        '<a class="btn btn-primary" href="/">Return to the portal</a></div>';
      return;
    }
    if (!state.attemptId || !state.workspaceId) {
      renderError("This examination link is incomplete. Start the examination from the portal.");
      return;
    }
    buildShell();
    load();
    window.addEventListener("beforeunload", function (event) {
      if (state.dirty.size && !state.submitted) {
        event.preventDefault();
        event.returnValue = "";
      }
    });
    window.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "hidden" && state.dirty.size) saveNow();
    });
  }

  function renderError(message) {
    document.getElementById("exam-root").innerHTML =
      '<div class="container-narrow"><div class="alert alert-danger">' +
      escapeHtml(message) + "</div></div>";
  }

  /* --------------------------------------------------------------- shell */

  function buildShell() {
    const root = document.getElementById("exam-root");
    clear(root);

    const bar = el("div", { class: "exam-bar", id: "exam-bar" }, [
      el("div", { class: "title", id: "exam-title", text: "Loading examination…" }),
      el("div", { class: "spacer" }),
      el("div", { class: "autosave-state", id: "autosave-state", "aria-live": "polite" }),
      el("div", { class: "timer", id: "timer", role: "timer", "aria-live": "off", text: "--:--" }),
      el("button", { class: "btn btn-primary btn-sm", id: "submit-top", type: "button",
        text: "Submit", onclick: confirmSubmit }),
    ]);

    const main = el("main", { class: "container" }, [
      el("div", { class: "exam-shell" }, [
        el("div", {}, [
          el("div", { class: "q-panel", id: "q-panel" }),
          el("div", { class: "exam-nav-row" }, [
            el("button", { class: "btn", id: "prev-btn", type: "button", text: "← Previous",
              onclick: function () { go(state.current - 1); } }),
            el("div", { class: "spacer" }),
            el("button", { class: "btn btn-primary", id: "next-btn", type: "button",
              text: "Next →", onclick: function () { go(state.current + 1); } }),
          ]),
        ]),
        el("aside", { class: "card nav-panel", id: "nav-panel" }),
      ]),
    ]);

    root.appendChild(bar);
    root.appendChild(main);
    dom.title = bar.querySelector("#exam-title");
    dom.timer = bar.querySelector("#timer");
    dom.autosave = bar.querySelector("#autosave-state");
    dom.panel = main.querySelector("#q-panel");
    dom.navPanel = main.querySelector("#nav-panel");
    dom.prev = main.querySelector("#prev-btn");
    dom.next = main.querySelector("#next-btn");
  }

  /* --------------------------------------------------------------- loading */

  async function load() {
    try {
      const data = await api.get(
        "/api/workspaces/" + state.workspaceId + "/attempts/" + state.attemptId);
      state.data = data;
      state.responses = data.responses || {};
      state.flags = data.flags || {};
      state.remaining = data.remaining_seconds;
      dom.title.textContent = data.examination.title;
      document.title = data.examination.title + " — EXAMGEN AI";
      renderInstructions();
      renderNav();
      renderQuestion(0);
      startTimer();
      setAutosave("saved", "All changes saved");
    } catch (error) {
      renderError(error.message || "The examination could not be loaded.");
    }
  }

  function renderInstructions() {
    const exam = state.data.examination;
    const answered = Object.keys(state.responses).filter(
      (id) => isAnswered(state.responses[id])).length;
    dom.navPanel.innerHTML = "";
    dom.navPanel.appendChild(el("h2", { text: "Examination" }));
    dom.navPanel.appendChild(el("dl", { class: "kv" }, [
      el("dt", { text: "Subject" }), el("dd", { text: exam.subject_name }),
      el("dt", { text: "Module" }), el("dd", { text: exam.module_name || "—" }),
      el("dt", { text: "Mode" }), el("dd", { text: exam.mode === "formal" ? "Formal simulation" : "Practice" }),
      el("dt", { text: "Duration" }), el("dd", { text: exam.duration_minutes + " minutes" }),
      el("dt", { text: "Total marks" }), el("dd", { text: String(exam.total_marks) }),
      el("dt", { text: "Questions" }), el("dd", { text: String(state.data.questions.length) }),
      el("dt", { text: "Answered" }), el("dd", { id: "answered-count", text: answered + " of " + state.data.questions.length }),
    ]));
    dom.navPanel.appendChild(el("p", { class: "small muted",
      style: "margin-top:.75rem", text: "Answers save automatically. You may flag questions and return to them before submitting." }));
  }

  /* --------------------------------------------------------------- timer */

  function startTimer() {
    if (state.timer) clearInterval(state.timer);
    if (state.remaining === null || state.remaining === undefined) {
      dom.timer.classList.add("hidden");
      return;
    }
    updateTimerDisplay();
    state.timer = setInterval(function () {
      state.remaining = Math.max(0, state.remaining - 1);
      updateTimerDisplay();
      if (state.remaining === 0) {
        clearInterval(state.timer);
        autoSubmit();
      }
    }, 1000);
  }

  function updateTimerDisplay() {
    dom.timer.textContent = formatDuration(state.remaining);
    dom.timer.classList.remove("is-warning", "is-critical");
    if (state.remaining <= 60) dom.timer.classList.add("is-critical");
    else if (state.remaining <= 300) dom.timer.classList.add("is-warning");
  }

  async function autoSubmit() {
    toast("Time is up. Your examination is being submitted.", "warn");
    await doSubmit(true);
  }

  /* --------------------------------------------------------------- nav */

  function renderNav() {
    const nav = dom.navPanel;
    const existing = nav.querySelector(".nav-grid");
    if (existing) existing.remove();
    const legend = nav.querySelector(".legend");
    if (legend) legend.remove();

    const grid = el("div", { class: "nav-grid", style: "margin-top:1rem" });
    state.data.questions.forEach(function (question, index) {
      const answered = isAnswered(state.responses[question.question_id]);
      const classes = ["nav-btn"];
      if (answered) classes.push("is-answered");
      if (state.flags[question.question_id]) classes.push("is-flagged");
      if (index === state.current) classes.push("is-current");
      grid.appendChild(el("button", {
        class: classes.join(" "), type: "button",
        title: "Question " + (index + 1) + (answered ? " (answered)" : " (unanswered)"),
        "aria-label": "Go to question " + (index + 1),
        text: String(index + 1),
        onclick: function () { go(index); },
      }));
    });
    nav.appendChild(grid);
    nav.appendChild(el("div", { class: "legend" }, [
      el("span", {}, [el("i", { class: "ok" }), "Answered"]),
      el("span", {}, [el("i", {}), "Not yet answered"]),
      el("span", {}, [el("i", { class: "cur" }), "Current question"]),
      el("span", {}, [el("i", { style: "background:var(--flag-soft);border-color:#ddd6fe" }), "Flagged for review"]),
    ]));
    const counter = nav.querySelector("#answered-count");
    if (counter) {
      counter.textContent = Object.keys(state.responses).filter(
        (id) => isAnswered(state.responses[id])).length + " of " + state.data.questions.length;
    }
  }

  function go(index) {
    if (index < 0 || index >= state.data.questions.length) return;
    flushDirty();
    state.current = index;
    renderQuestion(index);
    renderNav();
    dom.panel.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  /* --------------------------------------------------------------- render */

  function renderQuestion(index) {
    const question = state.data.questions[index];
    const total = state.data.questions.length;
    clear(dom.panel);

    const flagged = !!state.flags[question.question_id];
    dom.panel.appendChild(el("div", { class: "q-head" }, [
      el("span", { class: "badge badge-info", text: "Question " + (index + 1) + " of " + total }),
      el("span", { class: "badge", text: question.section || "Section A" }),
      el("span", { class: "badge", text: question.marks + (question.marks === 1 ? " mark" : " marks") }),
      el("span", { class: "badge", text: question.qtype.replace(/_/g, " ") }),
      el("div", { class: "spacer" }),
      el("button", {
        class: "btn btn-sm" + (flagged ? " btn-danger" : ""), type: "button",
        "aria-pressed": String(flagged),
        text: flagged ? "★ Flagged" : "☆ Flag for review",
        onclick: function (event) { toggleFlag(question.question_id, event.currentTarget); },
      }),
    ]));

    const body = el("div", { class: "q-body" });
    if (question.instructions) {
      body.appendChild(el("p", { class: "q-instructions", text: question.instructions }));
    }
    body.appendChild(el("p", { class: "q-prompt", text: question.prompt }));
    if (question.visual) body.appendChild(renderVisual(question.visual));

    const area = el("div", { class: "answer-area" });
    area.appendChild(buildControl(question));
    body.appendChild(area);

    if (state.data.examination.mode === "practice") {
      const hint = el("details", { style: "margin-top:1rem" }, [
        el("summary", { class: "small muted", style: "cursor:pointer",
          text: "Practice mode — show mark allocation guidance" }),
        el("p", { class: "small muted", style: "margin-top:.4rem",
          text: "This question is worth " + question.marks + " mark(s) and targets the " +
                (question.bloom || "understand") + " level of Bloom's taxonomy. " +
                "In practice mode you receive immediate feedback after submission." }),
      ]);
      body.appendChild(hint);
    }
    dom.panel.appendChild(body);

    dom.prev.disabled = index === 0;
    dom.next.disabled = index === total - 1;
  }

  function renderVisual(visual) {
    const figure = el("figure", { class: "visual-figure" });
    const host = el("div", { html: visual.svg || "" });
    figure.appendChild(host);
    figure.appendChild(el("figcaption", { class: "visual-caption",
      text: visual.title + " (version " + visual.version + ")" }));
    return figure;
  }

  function answerFor(questionId) {
    return state.responses[questionId] || {};
  }

  function setAnswer(questionId, patch) {
    const current = Object.assign({}, state.responses[questionId] || {});
    Object.assign(current, patch);
    state.responses[questionId] = current;
    state.dirty.add(questionId);
    scheduleSave();
    renderNav();
  }

  function markDirty(questionId) {
    state.dirty.add(questionId);
    scheduleSave();
  }

  /* --------------------------------------------------------------- controls */

  function buildControl(question) {
    const id = question.question_id;
    const answer = answerFor(id);
    const payload = question.payload || {};

    switch (question.qtype) {
      case "fill_blank":
      case "short_answer":
        return labelledInput("Your answer", el("input", {
          type: "text", value: answer.value || "", autocomplete: "off",
          placeholder: "Type your answer here",
          oninput: function (event) { setAnswer(id, { value: event.target.value }); },
        }));

      case "numerical":
        return labelledInput("Your answer (number only)", el("input", {
          type: "number", step: "any", value: answer.value !== undefined ? answer.value : "",
          placeholder: "e.g. 42.5",
          oninput: function (event) { setAnswer(id, { value: event.target.value }); },
        }));

      case "extended_response":
      case "essay":
        return labelledInput("Your response", el("textarea", {
          rows: question.qtype === "essay" ? 16 : 10,
          placeholder: "Write your answer here. Structure it clearly and use subject terminology.",
          oninput: function (event) { setAnswer(id, { value: event.target.value }); },
        }, [document.createTextNode(answer.value || "")]));

      case "diagram_interpretation":
        return labelledInput("Interpretation", el("textarea", {
          rows: 8,
          placeholder: "Describe the diagram: identify components and explain their relationships.",
          oninput: function (event) { setAnswer(id, { value: event.target.value }); },
        }, [document.createTextNode(answer.value || "")]));

      case "single_choice": {
        const select = el("select", { onchange: function (event) {
          setAnswer(id, { index: Number(event.target.value), value: question.options[Number(event.target.value)] });
        } }, [el("option", { value: "", text: "— Select an answer —" })]);
        question.options.forEach(function (option, index) {
          const isSelected = answer.index === index ||
            (answer.value && answer.value === option);
          select.appendChild(el("option", { value: String(index), text: String(option),
            selected: isSelected }));
        });
        return labelledInput("Select one answer (dropdown)", select);
      }

      case "multiple_choice": {
        const selected = Array.isArray(answer.selected) ? answer.selected.slice() : [];
        const wrap = el("fieldset", { style: "border:none;padding:0;margin:0" }, [
          el("legend", { class: "small", style: "font-weight:600;margin-bottom:.4rem",
            text: "Select all correct answers (checkboxes)" }),
        ]);
        question.options.forEach(function (option) {
          const box = el("input", { type: "checkbox", value: option,
            checked: selected.indexOf(option) !== -1,
            onchange: function (event) {
              const list = (state.responses[id] && state.responses[id].selected) ? state.responses[id].selected.slice() : [];
              const at = list.indexOf(option);
              if (event.target.checked && at === -1) list.push(option);
              if (!event.target.checked && at !== -1) list.splice(at, 1);
              setAnswer(id, { selected: list });
            } });
          wrap.appendChild(el("label", { style: "display:flex;gap:.55rem;align-items:flex-start;padding:.35rem 0;cursor:pointer" },
            [box, el("span", { text: String(option) })]));
        });
        return wrap;
      }

      case "matching": {
        const items = payload.items || [];
        const matches = Object.assign({}, answer.matches || {});
        const wrap = el("div", {}, [
          el("p", { class: "small", style: "font-weight:600;margin-bottom:.5rem",
            text: "Match each term to its correct description (dropdown per item)" }),
        ]);
        items.forEach(function (item) {
          const select = el("select", { onchange: function (event) {
            const next = Object.assign({}, state.responses[id] && state.responses[id].matches || {});
            next[item.prompt] = event.target.value;
            setAnswer(id, { matches: next });
          } }, [el("option", { value: "", text: "— Select —" })]);
          question.options.forEach(function (option) {
            select.appendChild(el("option", { value: String(option), text: String(option),
              selected: matches[item.prompt] === option }));
          });
          wrap.appendChild(el("div", { class: "match-row" }, [
            el("div", { class: "small", text: item.prompt }),
            select,
          ]));
        });
        return wrap;
      }

      case "ordering": {
        const correct = payload.correct_order || question.options || [];
        const current = Array.isArray(answer.order) && answer.order.length === correct.length
          ? answer.order.slice() : question.options.slice();
        const list = el("ol", { class: "order-list" });
        const repaint = function () {
          clear(list);
          current.forEach(function (item, index) {
            list.appendChild(el("li", { draggable: "true", dataset: { index: String(index) } }, [
              el("span", { class: "handle", text: "⠿" }),
              el("span", { class: "grow", text: String(item) }),
              el("span", { class: "move" }, [
                el("button", { class: "btn btn-sm", type: "button", text: "↑",
                  "aria-label": "Move up", disabled: index === 0,
                  onclick: function () { swap(index, index - 1); } }),
                el("button", { class: "btn btn-sm", type: "button", text: "↓",
                  "aria-label": "Move down", disabled: index === current.length - 1,
                  onclick: function () { swap(index, index + 1); } }),
              ]),
            ]));
          });
          bindDrag(list, current, repaint);
        };
        const swap = function (a, b) {
          const tmp = current[a]; current[a] = current[b]; current[b] = tmp;
          setAnswer(id, { order: current.slice() });
          repaint();
        };
        repaint();
        return el("div", {}, [
          el("p", { class: "small", style: "font-weight:600;margin-bottom:.5rem",
            text: "Reorder the items into the correct sequence. Drag, or use the arrow buttons." }),
          list,
        ]);
      }

      case "formula": {
        const symbols = payload.symbols || [];
        const symbolValues = Object.assign({}, answer.symbols || {});
        const wrap = el("div", {}, [
          labelledInput("State the formula / relationship", el("input", {
            type: "text", value: answer.value || "", placeholder: "e.g. V = I × R",
            oninput: function (event) { setAnswer(id, { value: event.target.value }); },
          })),
        ]);
        if (symbols.length) {
          wrap.appendChild(el("p", { class: "small", style: "font-weight:600",
            text: "Identify each symbol" }));
          symbols.forEach(function (symbol) {
            wrap.appendChild(el("div", { class: "match-row" }, [
              el("div", { class: "mono", text: symbol }),
              el("input", { type: "text", value: symbolValues[symbol] || "",
                placeholder: "meaning / unit",
                oninput: function (event) {
                  const next = Object.assign({}, state.responses[id] && state.responses[id].symbols || {});
                  next[symbol] = event.target.value;
                  setAnswer(id, { symbols: next });
                } }),
            ]));
          });
        }
        return wrap;
      }

      case "diagram_labelling": {
        const items = payload.items || [];
        const labels = Object.assign({}, answer.labels || {});
        const wrap = el("div", {}, [
          el("p", { class: "small", style: "font-weight:600;margin-bottom:.5rem",
            text: "Supply the correct label for each numbered position (text boxes)" }),
        ]);
        items.forEach(function (item, index) {
          wrap.appendChild(el("div", { class: "match-row" }, [
            el("div", { class: "small", text: item.prompt || ("Position " + (index + 1)) }),
            el("input", { type: "text", value: labels[item.prompt] || "",
              placeholder: "Label",
              oninput: function (event) {
                const next = Object.assign({}, state.responses[id] && state.responses[id].labels || {});
                next[item.prompt] = event.target.value;
                setAnswer(id, { labels: next });
              } }),
          ]));
        });
        return wrap;
      }

      case "case_study": {
        const items = payload.items || [];
        const subAnswers = Object.assign({}, answer.sub_answers || {});
        const wrap = el("div", {}, [
          el("p", { class: "small", style: "font-weight:600",
            text: "Answer each part of the case study." }),
        ]);
        items.forEach(function (item, index) {
          wrap.appendChild(el("div", { style: "margin-top:.75rem" }, [
            el("p", { class: "small", text: item.prompt || ("Part " + (index + 1)) }),
            el("textarea", { rows: 5, placeholder: "Your answer",
              oninput: function (event) {
                const next = Object.assign({}, state.responses[id] && state.responses[id].sub_answers || {});
                next[String(index)] = event.target.value;
                setAnswer(id, { sub_answers: next });
              } }, [document.createTextNode(subAnswers[String(index)] || "")]),
          ]));
        });
        return wrap;
      }

      default:
        return labelledInput("Your answer", el("textarea", {
          rows: 6, oninput: function (event) { setAnswer(id, { value: event.target.value }); },
        }, [document.createTextNode(answer.value || "")]));
    }
  }

  function labelledInput(label, control) {
    return el("div", {}, [
      el("label", { class: "small", style: "font-weight:600;display:block;margin-bottom:.35rem", text: label }),
      control,
    ]);
  }

  function bindDrag(list, current, repaint) {
    let dragIndex = null;
    Array.prototype.forEach.call(list.children, function (node) {
      node.addEventListener("dragstart", function (event) {
        dragIndex = Number(node.dataset.index);
        node.classList.add("dragging");
        if (event.dataTransfer) event.dataTransfer.effectAllowed = "move";
      });
      node.addEventListener("dragend", function () { node.classList.remove("dragging"); });
      node.addEventListener("dragover", function (event) {
        event.preventDefault();
        node.style.borderColor = "var(--accent)";
      });
      node.addEventListener("dragleave", function () { node.style.borderColor = ""; });
      node.addEventListener("drop", function (event) {
        event.preventDefault();
        node.style.borderColor = "";
        const target = Number(node.dataset.index);
        if (dragIndex === null || dragIndex === target) return;
        const moved = current.splice(dragIndex, 1)[0];
        current.splice(target, 0, moved);
        dragIndex = null;
        const id = state.data.questions[state.current].question_id;
        setAnswer(id, { order: current.slice() });
        repaint();
      });
    });
  }

  function toggleFlag(questionId, button) {
    state.flags[questionId] = !state.flags[questionId];
    const flagged = state.flags[questionId];
    button.textContent = flagged ? "★ Flagged" : "☆ Flag for review";
    button.setAttribute("aria-pressed", String(flagged));
    button.classList.toggle("btn-danger", flagged);
    state.dirty.add(questionId);
    scheduleSave();
    renderNav();
  }

  /* --------------------------------------------------------------- autosave */

  function isAnswered(answer) {
    if (!answer) return false;
    const keys = ["value", "text", "selected", "order", "matches", "index", "labels", "sub_answers", "symbols"];
    for (let i = 0; i < keys.length; i += 1) {
      const value = answer[keys[i]];
      if (value === null || value === undefined) continue;
      if (typeof value === "string" && value.trim()) return true;
      if (Array.isArray(value) && value.length) return true;
      if (typeof value === "object" && !Array.isArray(value) && Object.keys(value).length) {
        if (Object.keys(value).some(function (k) { return String(value[k] || "").trim(); })) return true;
      }
      if (typeof value === "number") return true;
    }
    return false;
  }

  function setAutosave(kind, message) {
    dom.autosave.className = "autosave-state " + (kind || "");
    clear(dom.autosave);
    if (kind === "saving") dom.autosave.appendChild(window.EXAMGEN.spinner(true));
    dom.autosave.appendChild(document.createTextNode(message));
  }

  function scheduleSave() {
    setAutosave("saving", "Saving…");
    if (state.saveTimer) clearTimeout(state.saveTimer);
    state.saveTimer = setTimeout(saveNow, 1200);
  }

  function flushDirty() {
    if (state.dirty.size) saveNow();
  }

  async function saveNow() {
    if (state.saving || state.submitted) return;
    if (!state.dirty.size) { setAutosave("saved", "All changes saved"); return; }
    const ids = Array.from(state.dirty);
    const payload = { responses: ids.map(function (id) {
      return { question_id: id, answer: state.responses[id] || {}, flagged: !!state.flags[id] };
    }) };
    state.saving = true;
    setAutosave("saving", "Saving…");
    try {
      await api.put("/api/workspaces/" + state.workspaceId + "/attempts/" +
        state.attemptId + "/responses", payload);
      ids.forEach(function (id) { state.dirty.delete(id); });
      setAutosave("saved", "Saved " + new Date().toLocaleTimeString());
    } catch (error) {
      setAutosave("error", "Save failed — retrying");
      setTimeout(saveNow, 3000);
    } finally {
      state.saving = false;
    }
  }

  /* --------------------------------------------------------------- submit */

  function confirmSubmit() {
    if (state.submitted) return;
    const unanswered = state.data.questions.filter(function (question) {
      return !isAnswered(state.responses[question.question_id]);
    }).length;
    const flagged = Object.keys(state.flags).filter(function (key) { return state.flags[key]; }).length;

    const body = [
      el("p", { text: "You are about to submit your examination." }),
      el("ul", { class: "list-plain" }, [
        el("li", {}, [el("span", { class: "grow",
          text: unanswered + " question(s) remain unanswered." })]),
        el("li", {}, [el("span", { class: "grow",
          text: flagged + " question(s) are flagged for review." })]),
      ]),
      el("p", { class: "small muted",
        text: "Once submitted, your answers are locked and marked. " +
              (state.data.examination.mode === "formal"
                ? "Feedback for formal simulations is released by your lecturer."
                : "Practice results and feedback are shown immediately.") }),
    ];
    const dialog = el("div", { class: "modal-backdrop", role: "dialog", "aria-modal": "true",
      "aria-label": "Confirm submission" }, [
      el("div", { class: "modal" }, [
        el("h2", { text: "Submit examination?" }),
        el("div", {}, body),
        el("div", { class: "modal-actions" }, [
          el("button", { class: "btn", type: "button", text: "Continue working",
            onclick: function () { dialog.remove(); } }),
          el("button", { class: "btn btn-primary", type: "button", text: "Submit now",
            onclick: function () { dialog.remove(); doSubmit(false); } }),
        ]),
      ]),
    ]);
    document.body.appendChild(dialog);
    const first = dialog.querySelector("button");
    if (first) first.focus();
  }

  async function doSubmit(auto) {
    if (state.submitted) return;
    try {
      await saveNow();
      const result = await api.post("/api/workspaces/" + state.workspaceId +
        "/attempts/" + state.attemptId + "/submit", {});
      state.submitted = true;
      if (state.timer) clearInterval(state.timer);
      renderResult(result, auto);
    } catch (error) {
      toast(error.message || "Submission failed. Please try again.", "danger");
    }
  }

  async function renderResult(result, auto) {
    const root = document.getElementById("exam-root");
    clear(root);
    const released = result.feedback_available;
    const score = result.score;
    const max = result.max_score;
    const percentage = result.percentage;

    const container = el("div", { class: "container-narrow" });
    container.appendChild(el("div", { class: "alert " + (auto ? "alert-warn" : "alert-ok") },
      [document.createTextNode(auto
        ? "Time expired — your examination was submitted automatically."
        : "Your examination has been submitted successfully. Your attempt is recorded.")]));

    const card = el("div", { class: "card" }, [
      el("h1", { text: "Submission received" }),
      el("p", { class: "muted", text: state.data.examination.title }),
    ]);
    if (released && score !== null && score !== undefined) {
      card.appendChild(el("div", { class: "result-score" }, [
        el("div", { class: "pct", text: percentage + "%" }),
        el("div", { class: "fraction", text: score + " / " + max + " marks" }),
      ]));
      const progress = el("div", { class: "progress " +
        (percentage >= 70 ? "is-ok" : percentage >= 50 ? "is-warn" : "is-danger") });
      progress.appendChild(el("i", { style: "width:" + Math.max(2, Math.min(100, percentage)) + "%" }));
      card.appendChild(progress);
    } else {
      card.appendChild(el("div", { class: "alert alert-info",
        text: "This is a formal simulation. Your answers are recorded and will be marked. " +
              "Feedback, the memorandum and detailed results are released by your lecturer." }));
    }
    container.appendChild(card);

    const actions = el("div", { class: "card" }, [el("h2", { text: "Next steps" })]);
    const links = el("div", { style: "display:flex;gap:.6rem;flex-wrap:wrap;margin-top:.5rem" });
    links.appendChild(el("a", { class: "btn btn-primary", href: "/",
      text: "Return to subject portal" }));
    if (released) {
      links.appendChild(el("a", { class: "btn", href: "/?workspace=" + state.workspaceId + "&view=results",
        text: "View detailed results and feedback" }));
    }
    actions.appendChild(links);
    container.appendChild(actions);

    root.appendChild(container);
  }
})();
