/* EXAMGEN AI — student portal.
 *
 * Drives the complete subject-specific workflow:
 *   select subject -> upload only its coursework -> review classification and
 *   gaps -> approve visuals -> configure the blueprint -> generate and moderate
 *   -> sit the examination -> view results -> download the memorandum and the
 *   subject mastery guide.
 */
(function () {
  "use strict";
  const { api, el, clear, escapeHtml, statusBadge, alertBox, withButtonState,
          toast, formatDateTime } = window.EXAMGEN;

  const state = { user: null, workspaces: [], workspace: null, tab: "resources",
                  topics: [], visuals: [], examinations: [], documents: [],
                  sufficiency: null, analytics: null, summary: null, blueprints: [] };

  const TAB_NAMES = ["resources", "classification", "visuals", "examinations", "results"];

  const root = () => document.getElementById("view");

  document.addEventListener("DOMContentLoaded", boot);

  async function boot() {
    const params = new URLSearchParams(window.location.search);
    const workspaceParam = params.get("workspace");
    if (workspaceParam) api.store.workspaceId = workspaceParam;
    // Deep links such as ?view=results (used after submitting an examination)
    // must land on the requested tab rather than the default one.
    const requestedTab = params.get("view");
    if (TAB_NAMES.indexOf(requestedTab) >= 0) state.tab = requestedTab;

    if (!api.store.token) { renderAuth(); return; }
    try {
      state.user = await api.get("/api/auth/me");
    } catch (_) {
      api.store.token = "";
      renderAuth();
      return;
    }
    renderShell();
    await loadWorkspaces();
    if (api.store.workspaceId) {
      const found = state.workspaces.find((w) => w.id === api.store.workspaceId);
      if (found) await openWorkspace(found.id);
      else renderWorkspaceList();
    } else {
      renderWorkspaceList();
    }
  }

  /* ---------------------------------------------------------------- auth */

  function renderAuth() {
    clear(root());
    let mode = "login";
    const panel = el("div", { class: "card", style: "max-width:420px;margin:3rem auto" });
    const draw = function () {
      clear(panel);
      panel.appendChild(el("h1", { text: mode === "login" ? "Sign in" : "Create your account" }));
      panel.appendChild(el("p", { class: "muted small",
        text: "EXAMGEN AI builds examinations from the coursework you upload for one subject at a time." }));

      const email = el("input", { type: "email", id: "auth-email", autocomplete: "email",
        placeholder: "you@example.com" });
      const password = el("input", { type: "password", id: "auth-password",
        autocomplete: mode === "login" ? "current-password" : "new-password",
        placeholder: mode === "login" ? "Your password" : "At least 8 characters" });
      const name = el("input", { type: "text", id: "auth-name", autocomplete: "name",
        placeholder: "Your name (optional)" });

      panel.appendChild(el("label", { class: "field" }, [el("span", { text: "Email" }), email]));
      if (mode === "register") {
        panel.appendChild(el("label", { class: "field" }, [el("span", { text: "Display name" }), name]));
      }
      panel.appendChild(el("label", { class: "field" }, [el("span", { text: "Password" }), password]));

      const submit = el("button", { class: "btn btn-primary btn-block", type: "button",
        text: mode === "login" ? "Sign in" : "Create account" });
      submit.addEventListener("click", async function () {
        await withButtonState(submit, async function () {
          try {
            const path = mode === "login" ? "/api/auth/login" : "/api/auth/register";
            const body = { email: email.value.trim(), password: password.value };
            if (mode === "register") body.display_name = name.value.trim();
            const result = await api.post(path, body);
            api.store.token = result.access_token;
            toast("Welcome to EXAMGEN AI", "ok");
            await boot();
          } catch (error) {
            clear(panel);
            panel.appendChild(alertBox("danger", error.message));
            draw();
          }
        });
      });
      panel.appendChild(submit);
      const toggle = el("button", { class: "btn btn-ghost btn-sm", style: "margin-top:.6rem",
        type: "button", text: mode === "login" ? "Create a new account" : "I already have an account" });
      toggle.addEventListener("click", function () { mode = mode === "login" ? "register" : "login"; draw(); });
      panel.appendChild(toggle);
    };
    draw();
    root().appendChild(panel);
  }

  /* ---------------------------------------------------------------- shell */

  function renderShell() {
    const header = document.getElementById("app-header");
    clear(header);
    header.appendChild(el("div", { class: "brand" }, [
      el("div", { class: "brand-mark", text: "EX" }),
      el("div", {}, [el("span", { text: "EXAMGEN AI" }),
        el("small", { text: "Academic examination & subject mastery platform" })]),
    ]));
    header.appendChild(el("div", { class: "spacer" }));
    if (state.workspace) {
      header.appendChild(el("button", { class: "btn btn-sm", type: "button",
        text: "← All subjects", onclick: function () {
          api.store.workspaceId = ""; state.workspace = null; renderShell(); renderWorkspaceList();
        } }));
    }
    header.appendChild(el("span", { class: "small muted", text: state.user.display_name || state.user.email }));
    header.appendChild(el("button", { class: "btn btn-sm btn-ghost", type: "button", text: "Sign out",
      onclick: function () { api.store.token = ""; api.store.workspaceId = ""; state.workspace = null; renderShell(); renderAuth(); } }));
  }

  /* ---------------------------------------------------------------- workspaces */

  async function loadWorkspaces() {
    state.workspaces = await api.get("/api/workspaces");
  }

  function renderWorkspaceList() {
    state.workspace = null;
    clear(root());
    const container = el("div", { class: "container" });
    container.appendChild(el("div", { class: "section-head" }, [
      el("div", {}, [el("h1", { text: "Your subjects" }),
        el("p", { class: "muted", text: "Each subject is an independent workspace. Upload only the coursework for the subject you are preparing." })]),
      el("div", { class: "spacer" }),
      el("button", { class: "btn btn-primary", type: "button", text: "+ New subject",
        onclick: openCreateDialog }),
    ]));

    if (!state.workspaces.length) {
      container.appendChild(el("div", { class: "card empty" }, [
        el("strong", { text: "No subjects yet" }),
        el("p", { class: "muted small", text: "Create your first subject workspace to begin. You will then upload only that subject's coursework." }),
      ]));
    } else {
      const grid = el("div", { class: "grid grid-3" });
      state.workspaces.forEach(function (workspace) {
        const card = el("div", { class: "card", style: "cursor:pointer" }, [
          el("h2", { text: workspace.name }),
          el("p", { class: "card-sub", text: [workspace.code, workspace.module, workspace.institution]
            .filter(Boolean).join(" · ") || "No module details" }),
          el("p", { class: "small muted", text: workspace.description || "—" }),
          el("div", { style: "display:flex;gap:.4rem;flex-wrap:wrap;margin-top:.5rem" }, [
            workspace.supplementary_enabled ? el("span", { class: "badge badge-info", text: "supplementary enabled" }) : null,
            el("span", { class: "badge", text: "created " + formatDateTime(workspace.created_at) }),
          ]),
        ]);
        card.addEventListener("click", function () { openWorkspace(workspace.id); });
        grid.appendChild(card);
      });
      container.appendChild(grid);
    }
    root().appendChild(container);
  }

  function openCreateDialog() {
    const name = el("input", { type: "text", placeholder: "e.g. Data Structures and Algorithms" });
    const code = el("input", { type: "text", placeholder: "e.g. CS201" });
    const module_ = el("input", { type: "text", placeholder: "e.g. Module 3 — Algorithms" });
    const institution = el("input", { type: "text", placeholder: "e.g. University of Example" });
    const qualification = el("input", { type: "text", placeholder: "e.g. BSc Computer Science" });
    const description = el("textarea", { rows: 2, placeholder: "Optional notes about this subject or module" });
    const dialog = modal("Create a subject workspace", [
      el("p", { class: "muted small", text: "Name the individual subject or module. Only coursework for this selection should be uploaded." }),
      el("label", { class: "field" }, [el("span", { text: "Subject / module name *" }), name]),
      el("div", { class: "inline-fields" }, [
        el("label", { class: "field" }, [el("span", { text: "Subject code" }), code]),
        el("label", { class: "field" }, [el("span", { text: "Module" }), module_]),
      ]),
      el("div", { class: "inline-fields" }, [
        el("label", { class: "field" }, [el("span", { text: "Institution" }), institution]),
        el("label", { class: "field" }, [el("span", { text: "Qualification" }), qualification]),
      ]),
      el("label", { class: "field" }, [el("span", { text: "Description" }), description]),
    ], async function (button) {
      if (!name.value.trim()) { toast("Enter a subject name", "warn"); return false; }
      await withButtonState(button, async function () {
        const workspace = await api.post("/api/workspaces", {
          name: name.value.trim(), code: code.value.trim(), module: module_.value.trim(),
          institution: institution.value.trim(), qualification: qualification.value.trim(),
          description: description.value.trim(),
        });
        await loadWorkspaces();
        dialog.remove();
        toast("Subject workspace created", "ok");
        openWorkspace(workspace.id);
      });
      return true;
    }, "Create subject");
  }

  async function openWorkspace(workspaceId) {
    api.store.workspaceId = workspaceId;
    state.workspace = state.workspaces.find((w) => w.id === workspaceId) ||
      await api.get("/api/workspaces/" + workspaceId);
    renderShell();
    await refreshWorkspace();
    renderWorkspace();
  }

  async function refreshWorkspace() {
    const id = state.workspace.id;
    const results = await Promise.allSettled([
      api.get("/api/workspaces/" + id + "/documents"),
      api.get("/api/workspaces/" + id + "/topics"),
      api.get("/api/workspaces/" + id + "/visuals"),
      api.get("/api/workspaces/" + id + "/examinations"),
      api.get("/api/workspaces/" + id + "/summary"),
      api.get("/api/workspaces/" + id + "/analytics"),
      api.get("/api/workspaces/" + id + "/blueprints"),
    ]);
    state.documents = value(results[0], []);
    state.topics = value(results[1], []);
    state.visuals = value(results[2], []);
    state.examinations = value(results[3], []);
    state.summary = value(results[4], null);
    state.analytics = value(results[5], null);
    state.blueprints = value(results[6], []);
    try { state.sufficiency = await api.get("/api/workspaces/" + id + "/sufficiency"); }
    catch (_) { state.sufficiency = null; }
  }

  function value(result, fallback) {
    return result.status === "fulfilled" && result.value !== undefined && result.value !== null
      ? result.value : fallback;
  }

  function selectTab(name) {
    state.tab = name;
    if (window.history && window.history.replaceState && state.workspace) {
      const query = "?workspace=" + encodeURIComponent(state.workspace.id) + "&view=" + name;
      window.history.replaceState(null, "", window.location.pathname + query);
    }
    renderWorkspace();
  }

  function renderWorkspace() {
    clear(root());
    const container = el("div", { class: "container" });
    container.appendChild(el("div", { class: "section-head" }, [
      el("div", {}, [
        el("h1", { text: state.workspace.name }),
        el("p", { class: "muted", text: [state.workspace.code, state.workspace.module,
          state.workspace.institution].filter(Boolean).join(" · ") || "Subject workspace" }),
      ]),
      el("div", { class: "spacer" }),
      state.summary ? el("span", { class: "badge badge-info",
        text: state.summary.topic_count + " topics · " + state.summary.document_count + " documents" }) : null,
    ]));

    const tabs = el("div", { class: "tabs", role: "tablist" });
    [["resources", "1 · Resources"], ["classification", "2 · Topics & gaps"],
     ["visuals", "3 · Visuals"], ["examinations", "4 · Examinations"],
     ["results", "Results & mastery"]].forEach(function (entry) {
      const button = el("button", { class: "tab", role: "tab", type: "button",
        "aria-selected": String(state.tab === entry[0]), text: entry[1],
        onclick: function () { selectTab(entry[0]); } });
      tabs.appendChild(button);
    });
    container.appendChild(tabs);

    const body = el("div", { id: "workspace-body" });
    container.appendChild(body);
    root().appendChild(container);

    const renderers = { resources: renderResources, classification: renderClassification,
      visuals: renderVisuals, examinations: renderExaminations, results: renderResults };
    (renderers[state.tab] || renderResources)(body);
  }

  /* ---------------------------------------------------------------- 1. resources */

  function renderResources(host) {
    const card = el("div", { class: "card" }, [
      el("div", { class: "card-head" }, [
        el("h2", { text: "Upload coursework for this subject" }),
        el("div", { class: "spacer" }),
        el("span", { class: "badge", text: state.documents.length + " document(s)" }),
      ]),
      el("p", { class: "muted small",
        text: "Upload only the resources for this subject or module: lecture notes, slides, " +
              "workbooks, study guides, previous tests and memoranda. Other subjects must not be " +
              "uploaded here — each subject keeps its own isolated workspace." }),
    ]);

    const fileInput = el("input", { type: "file", multiple: true,
      accept: ".pdf,.docx,.pptx,.xlsx,.csv,.txt,.md,.html,.png,.jpg,.jpeg" });
    const uploadBtn = el("button", { class: "btn btn-primary", type: "button", text: "Upload files" });
    uploadBtn.addEventListener("click", async function () {
      const files = Array.from(fileInput.files || []);
      if (!files.length) { toast("Choose one or more files first", "warn"); return; }
      await withButtonState(uploadBtn, async function () {
        let ok = 0; const errors = [];
        for (const file of files) {
          const form = new FormData();
          form.append("file", file);
          try {
            await api.upload("/api/workspaces/" + state.workspace.id + "/documents", form);
            ok += 1;
          } catch (error) { errors.push(file.name + ": " + error.message); }
        }
        toast(ok + " file(s) uploaded" + (errors.length ? ", " + errors.length + " failed" : ""),
          errors.length ? "warn" : "ok");
        errors.forEach((message) => toast(message, "danger"));
        await refreshWorkspace();
        renderWorkspace();
      });
    });

    card.appendChild(el("div", { class: "inline-fields" }, [
      el("label", { class: "field", style: "flex:2 1 320px" }, [
        el("span", { text: "Files", class: "hint" }), fileInput]),
      uploadBtn,
      el("button", { class: "btn", type: "button", text: "Reclassify subject",
        onclick: async function (event) {
          await withButtonState(event.currentTarget, async function () {
            try {
              await api.post("/api/workspaces/" + state.workspace.id + "/classify", {});
              toast("Subject reclassified", "ok");
              await refreshWorkspace();
              renderWorkspace();
            } catch (error) { toast(error.message, "danger"); }
          });
        } }),
    ]));
    host.appendChild(card);

    const listCard = el("div", { class: "card" }, [el("h2", { text: "Uploaded documents" })]);
    if (!state.documents.length) {
      listCard.appendChild(el("div", { class: "empty" }, [
        el("strong", { text: "No documents yet" }),
        el("p", { class: "muted small", text: "Upload the coursework for this subject to begin." })]));
    } else {
      const table = el("table", { class: "data" }, [
        el("thead", {}, [el("tr", {}, ["Document", "Type", "Version", "Status", "Extracted", ""]
          .map((h) => el("th", { text: h })))]),
      ]);
      const tbody = el("tbody");
      state.documents.forEach(function (document) {
        const row = el("tr", {}, [
          el("td", {}, [el("div", { text: document.filename }),
            document.processing_notes ? el("div", { class: "tiny muted", text: document.processing_notes }) : null]),
          el("td", {}, [el("span", { class: "badge", text: document.kind.replace(/_/g, " ") })]),
          el("td", { text: "v" + document.version }),
          el("td", {}, [statusBadge(document.status)]),
          el("td", { class: "small", text: document.extracted_chars.toLocaleString() + " chars" }),
          el("td", {}, [el("button", { class: "btn btn-sm btn-ghost", type: "button", text: "Delete",
            onclick: async function () {
              if (!window.confirm("Delete " + document.filename + "?")) return;
              await api.del("/api/workspaces/" + state.workspace.id + "/documents/" + document.id);
              await refreshWorkspace(); renderWorkspace();
            } })]),
        ]);
        tbody.appendChild(row);
      });
      table.appendChild(tbody);
      listCard.appendChild(el("div", { class: "table-wrap" }, [table]));
    }
    host.appendChild(listCard);
    host.appendChild(renderSufficiencyCard());
  }

  function renderSufficiencyCard() {
    const card = el("div", { class: "card" }, [el("h2", { text: "Resource sufficiency assessment" })]);
    const report = state.sufficiency;
    if (!report) {
      card.appendChild(el("p", { class: "muted small",
        text: "Upload documents and reclassify to generate a coverage assessment." }));
      return card;
    }
    const verdictKind = { sufficient: "ok", partial: "warn", insufficient: "danger" }[report.verdict] || "";
    card.appendChild(el("p", {}, [
      el("span", { class: "badge badge-" + verdictKind, text: "Verdict: " + report.verdict }),
      el("span", { class: "muted small", style: "margin-left:.6rem",
        text: report.document_count + " document(s) · " + report.total_chars.toLocaleString() + " characters of source material" }),
    ]));
    const groups = [
      ["Adequately covered topics", report.adequate, "ok"],
      ["Partially covered topics", report.partial, "warn"],
      ["Content referenced in previous assessments but missing from coursework", report.missing, "danger"],
      ["Topics without explicit learning outcomes", report.missing_outcomes, "warn"],
      ["Conflicting material across documents", (report.conflicts || []).map(
        (c) => c.message || JSON.stringify(c)), "danger"],
      ["Question types the material cannot support", report.insufficient_types, "warn"],
      ["Points requiring clarification", report.clarifications, "info"],
    ];
    const grid = el("div", { class: "grid grid-2" });
    groups.forEach(function (group) {
      const items = group[1] || [];
      if (!items.length) return;
      const box = el("div", { class: "card", style: "box-shadow:none;background:var(--surface-2)" }, [
        el("h3", { text: group[0] + " (" + items.length + ")" }),
      ]);
      const list = el("ul", { class: "list-plain" });
      items.slice(0, 12).forEach(function (item) {
        list.appendChild(el("li", {}, [el("span", { class: "grow small",
          text: typeof item === "string" ? item : JSON.stringify(item) })]));
      });
      box.appendChild(list);
      grid.appendChild(box);
    });
    card.appendChild(grid);
    card.appendChild(el("p", { class: "small muted", style: "margin-top:.75rem",
      text: "Missing content is reported rather than fabricated. Where coverage is incomplete, " +
            "upload the additional material indicated above to improve examination quality." }));
    return card;
  }

  /* ---------------------------------------------------------------- 2. classification */

  function renderClassification(host) {
    const card = el("div", { class: "card" }, [
      el("div", { class: "card-head" }, [
        el("h2", { text: "Identified topics and learning outcomes" }),
        el("div", { class: "spacer" }),
        el("button", { class: "btn btn-sm", type: "button", text: "Reclassify",
          onclick: async function (event) {
            await withButtonState(event.currentTarget, async function () {
              await api.post("/api/workspaces/" + state.workspace.id + "/classify", {});
              await refreshWorkspace(); renderWorkspace();
              toast("Reclassified", "ok");
            });
          } }),
      ]),
      el("p", { class: "muted small",
        text: "Review the classification and correct anything that is wrong. Your corrections are " +
              "preserved when the subject is reclassified." }),
    ]);
    host.appendChild(card);

    if (!state.topics.length) {
      host.appendChild(el("div", { class: "card empty" }, [
        el("strong", { text: "No topics identified yet" }),
        el("p", { class: "muted small", text: "Upload coursework, then classify the subject." })]));
      return;
    }

    state.topics.forEach(function (topic) {
      const visualBadge = { essential: "danger", beneficial: "warn", unnecessary: "" }[topic.needs_visual];
      const topicCard = el("div", { class: "card" }, [
        el("div", { class: "card-head" }, [
          el("h2", { text: topic.name }),
          el("div", { class: "spacer" }),
          statusBadge(topic.coverage),
          el("span", { class: "badge" + (visualBadge ? " badge-" + visualBadge : ""),
            text: "visual: " + topic.needs_visual }),
          el("span", { class: "badge", text: "confidence " + Math.round(topic.confidence * 100) + "%" }),
          topic.reviewed_by_student ? el("span", { class: "badge badge-ok", text: "reviewed" }) : null,
        ]),
      ]);
      if (topic.coverage_notes) {
        topicCard.appendChild(el("p", { class: "small muted", text: topic.coverage_notes }));
      }
      if (topic.visual_rationale) {
        topicCard.appendChild(el("p", { class: "small muted", text: topic.visual_rationale }));
      }

      const nameInput = el("input", { type: "text", value: topic.name });
      const summaryInput = el("textarea", { rows: 2 }, [document.createTextNode(topic.summary || "")]);
      const visualSelect = el("select", {}, ["essential", "beneficial", "unnecessary"].map(
        (option) => el("option", { value: option, text: option, selected: topic.needs_visual === option })));
      topicCard.appendChild(el("details", {}, [
        el("summary", { class: "small muted", style: "cursor:pointer", text: "Edit topic details" }),
        el("div", { style: "margin-top:.6rem" }, [
          el("label", { class: "field" }, [el("span", { text: "Topic name" }), nameInput]),
          el("label", { class: "field" }, [el("span", { text: "Summary" }), summaryInput]),
          el("label", { class: "field" }, [el("span", { text: "Visual requirement" }), visualSelect]),
          el("button", { class: "btn btn-sm btn-primary", type: "button", text: "Save topic",
            onclick: async function (event) {
              await withButtonState(event.currentTarget, async function () {
                await api.patch("/api/workspaces/" + state.workspace.id + "/topics/" + topic.id, {
                  name: nameInput.value.trim() || topic.name,
                  summary: summaryInput.value.trim(),
                  needs_visual: visualSelect.value,
                });
                await refreshWorkspace(); renderWorkspace();
                toast("Topic updated", "ok");
              });
            } }),
        ]),
      ]));

      const subtopics = el("div", { class: "grid grid-2", style: "margin-top:.75rem" });
      (topic.subtopics || []).forEach(function (subtopic) {
        const sub = el("div", { style: "background:var(--surface-2);border-radius:8px;padding:.7rem .8rem" }, [
          el("div", { style: "display:flex;gap:.5rem;align-items:center" }, [
            el("strong", { class: "small", text: subtopic.name }),
            statusBadge(subtopic.coverage),
          ]),
        ]);
        if (subtopic.summary) {
          sub.appendChild(el("p", { class: "tiny muted", style: "margin:.35rem 0",
            text: subtopic.summary }));
        }
        if ((subtopic.outcomes || []).length) {
          const list = el("ul", { class: "list-plain" });
          subtopic.outcomes.forEach(function (outcome) {
            list.appendChild(el("li", {}, [
              el("span", { class: "grow tiny", text: outcome.statement }),
              el("span", { class: "badge", text: outcome.bloom }),
            ]));
          });
          sub.appendChild(list);
        } else {
          sub.appendChild(el("p", { class: "tiny muted", text: "No explicit learning outcomes stated in the source material." }));
        }
        subtopics.appendChild(sub);
      });
      topicCard.appendChild(subtopics);
      host.appendChild(topicCard);
    });
  }

  /* ---------------------------------------------------------------- 3. visuals */

  function renderVisuals(host) {
    const proposed = state.visuals.filter((v) => v.status === "proposed").length;
    const card = el("div", { class: "card" }, [
      el("div", { class: "card-head" }, [
        el("h2", { text: "Visual assessment assets" }),
        el("div", { class: "spacer" }),
        el("span", { class: "badge", text: proposed + " awaiting approval" }),
        el("button", { class: "btn btn-sm btn-primary", type: "button", text: "Analyse visual requirements",
          onclick: async function (event) {
            await withButtonState(event.currentTarget, async function () {
              const result = await api.post("/api/workspaces/" + state.workspace.id + "/visuals/propose", {});
              toast(result.created + " visual asset(s) proposed", "ok");
              await refreshWorkspace(); renderWorkspace();
            });
          } }),
      ]),
      el("p", { class: "muted small",
        text: "Visual requirements are assessed before the examination blueprint is created. " +
              "Diagrams are constructed as editable vector assets, versioned, and must be " +
              "approved before any question may reference them." }),
    ]);
    host.appendChild(card);

    if (!state.visuals.length) {
      host.appendChild(el("div", { class: "card empty" }, [
        el("strong", { text: "No visual assets yet" }),
        el("p", { class: "muted small",
          text: "Classify the subject, then analyse visual requirements to detect topics that need diagrams." })]));
      return;
    }

    const grid = el("div", { class: "grid grid-2" });
    state.visuals.forEach(function (visual) {
      const cardNode = el("div", { class: "card" }, [
        el("div", { class: "card-head" }, [
          el("h3", { text: visual.title }),
          el("div", { class: "spacer" }),
          statusBadge(visual.status),
          el("span", { class: "badge", text: "v" + visual.version }),
          el("span", { class: "badge", text: visual.requirement }),
        ]),
        el("div", { class: "visual-figure", html: visual.svg }),
        el("p", { class: "small muted", text: visual.intended_use || "" }),
        el("p", { class: "tiny muted", text: "Diagram type: " +
          visual.diagram_type.replace(/_/g, " ") + " · key: " + visual.key }),
      ]);
      const actions = el("div", { style: "display:flex;gap:.5rem;flex-wrap:wrap;margin-top:.5rem" });
      actions.appendChild(el("button", { class: "btn btn-sm btn-ok", type: "button", text: "Approve",
        onclick: async function (event) {
          await withButtonState(event.currentTarget, async function () {
            await api.post("/api/workspaces/" + state.workspace.id + "/visuals/" + visual.id + "/decision",
              { decision: "approve" });
            await refreshWorkspace(); renderWorkspace();
            toast("Visual approved", "ok");
          });
        } }));
      actions.appendChild(el("button", { class: "btn btn-sm btn-danger", type: "button", text: "Reject",
        onclick: async function (event) {
          await withButtonState(event.currentTarget, async function () {
            await api.post("/api/workspaces/" + state.workspace.id + "/visuals/" + visual.id + "/decision",
              { decision: "reject" });
            await refreshWorkspace(); renderWorkspace();
          });
        } }));
      actions.appendChild(el("button", { class: "btn btn-sm", type: "button", text: "Edit labels",
        onclick: function () { openVisualEdit(visual); } }));
      cardNode.appendChild(actions);
      grid.appendChild(cardNode);
    });
    host.appendChild(grid);
  }

  function openVisualEdit(visual) {
    const input = el("textarea", { rows: 3 },
      [document.createTextNode((visual.labels || []).join("\n"))]);
    const dialog = modal("Revise diagram labels", [
      el("p", { class: "muted small",
        text: "One label per line. Saving creates a new version of this asset, which must be approved again." }),
      el("label", { class: "field" }, [el("span", { text: "Labels" }), input]),
    ], async function (button) {
      await withButtonState(button, async function () {
        const labels = input.value.split("\n").map((s) => s.trim()).filter(Boolean);
        await api.post("/api/workspaces/" + state.workspace.id + "/visuals/" + visual.id + "/revise",
          { labels: labels });
        await refreshWorkspace(); renderWorkspace();
        dialog.remove();
        toast("New visual version created", "ok");
      });
      return true;
    }, "Save new version");
  }

  /* ---------------------------------------------------------------- 4. examinations */

  function renderExaminations(host) {
    const approvedVisuals = state.visuals.filter((v) => v.status === "approved");
    const card = el("div", { class: "card" }, [
      el("div", { class: "card-head" }, [
        el("h2", { text: "Examination blueprint" }),
        el("div", { class: "spacer" }),
        el("span", { class: "badge badge-info", text: approvedVisuals.length + " approved visual(s)" }),
        el("span", { class: "badge", text: state.topics.length + " topic(s) available" }),
      ]),
      el("p", { class: "muted small",
        text: "Configure the paper, validate it against the blueprint, then generate. Every paper is " +
              "moderated before publication; a paper with unresolved critical errors cannot be published." }),
    ]);
    host.appendChild(card);

    const title = el("input", { type: "text",
      value: (state.workspace.name || "Examination") + " — Examination" });
    const duration = el("input", { type: "number", value: "60", min: "5", max: "600" });
    const totalMarks = el("input", { type: "number", value: "100", min: "5", max: "1000" });
    const count = el("input", { type: "number", value: "12", min: "1", max: "200" });
    const difficulty = el("select", {}, ["beginner", "basic", "intermediate", "advanced", "expert"]
      .map((d) => el("option", { value: d, text: d, selected: d === "intermediate" })));
    const mode = el("select", {}, [
      el("option", { value: "practice", text: "Practice — immediate feedback and explanations" }),
      el("option", { value: "formal", text: "Formal simulation — controlled feedback release" }),
    ]);
    const instructions = el("textarea", { rows: 3,
      placeholder: "Optional instructions shown to the student at the start of the paper." });

    const topicBoxes = el("div", { class: "grid grid-2", style: "margin-top:.4rem" });
    state.topics.forEach(function (topic) {
      const box = el("input", { type: "checkbox", value: topic.id, checked: true });
      topicBoxes.appendChild(el("label", { style: "display:flex;gap:.5rem;align-items:flex-start;padding:.3rem 0;cursor:pointer" },
        [box, el("span", { class: "small", text: topic.name + " (" + topic.coverage + ")" })]));
    });

    const visualBoxes = el("div", {}, []);
    approvedVisuals.forEach(function (visual) {
      const box = el("input", { type: "checkbox", value: visual.key });
      visualBoxes.appendChild(el("label", { style: "display:flex;gap:.5rem;align-items:center;padding:.25rem 0;cursor:pointer" },
        [box, el("span", { class: "small", text: visual.title })]));
    });

    const form = el("div", { class: "card" }, [
      el("h2", { text: "Configure the examination" }),
      el("label", { class: "field" }, [el("span", { text: "Examination title" }), title]),
      el("div", { class: "inline-fields" }, [
        el("label", { class: "field" }, [el("span", { text: "Duration (minutes)" }), duration]),
        el("label", { class: "field" }, [el("span", { text: "Total marks" }), totalMarks]),
        el("label", { class: "field" }, [el("span", { text: "Number of questions" }), count]),
        el("label", { class: "field" }, [el("span", { text: "Difficulty" }), difficulty]),
        el("label", { class: "field" }, [el("span", { text: "Mode" }), mode]),
      ]),
      el("label", { class: "field" }, [el("span", { text: "Instructions" }), instructions]),
      el("h3", { text: "Topics to assess" }), topicBoxes,
      approvedVisuals.length ? el("div", {}, [el("h3", { text: "Required visual assets" }),
        el("p", { class: "tiny muted", text: "Select visuals that must be assessed in this paper." }),
        visualBoxes]) : null,
      el("div", { style: "display:flex;gap:.6rem;flex-wrap:wrap;margin-top:1rem" }, [
        el("button", { class: "btn", type: "button", text: "Save and validate blueprint",
          onclick: async function (event) {
            await withButtonState(event.currentTarget, async function () {
              try {
                const blueprint = await api.post("/api/workspaces/" + state.workspace.id + "/blueprints",
                  collectBlueprint());
                const validation = await api.get("/api/workspaces/" + state.workspace.id +
                  "/blueprints/" + blueprint.id + "/validate");
                showValidation(validation);
                await refreshWorkspace();
              } catch (error) { toast(error.message, "danger"); }
            });
          } }),
        el("button", { class: "btn btn-primary", type: "button", text: "Generate examination",
          onclick: async function (event) {
            await withButtonState(event.currentTarget, async function () {
              try {
                const blueprint = await api.post("/api/workspaces/" + state.workspace.id + "/blueprints",
                  collectBlueprint());
                const examination = await api.post("/api/workspaces/" + state.workspace.id +
                  "/blueprints/" + blueprint.id + "/generate", { mode: mode.value });
                toast("Examination generated — moderation: " +
                  examination.moderation_status.replace(/_/g, " "),
                  examination.status === "published" ? "ok" : "warn");
                await refreshWorkspace();
                state.tab = "examinations";
                renderWorkspace();
              } catch (error) { toast(error.message, "danger"); }
            });
          } }),
      ]),
      el("div", { id: "validation-host" }),
    ]);
    host.appendChild(form);

    function collectBlueprint() {
      return {
        title: title.value.trim() || "Examination",
        duration_minutes: Number(duration.value) || 60,
        total_marks: Number(totalMarks.value) || 100,
        question_count: Number(count.value) || 10,
        difficulty: difficulty.value,
        mode: mode.value,
        instructions: instructions.value.trim(),
        topic_ids: Array.from(topicBoxes.querySelectorAll("input:checked")).map((i) => i.value),
        required_visual_keys: Array.from(visualBoxes.querySelectorAll("input:checked")).map((i) => i.value),
      };
    }

    function showValidation(validation) {
      const hostNode = form.querySelector("#validation-host");
      clear(hostNode);
      const box = el("div", { style: "margin-top:1rem" }, [
        alertBox(validation.valid ? "ok" : "danger",
          validation.valid ? "Blueprint is valid and ready for generation."
            : "Blueprint cannot be used yet."),
      ]);
      if (validation.issues && validation.issues.length) {
        box.appendChild(el("ul", { class: "list-plain" }, validation.issues.map(
          (issue) => el("li", {}, [el("span", { class: "grow small", text: "✖ " + issue })]))));
      }
      if (validation.warnings && validation.warnings.length) {
        box.appendChild(el("ul", { class: "list-plain" }, validation.warnings.map(
          (warning) => el("li", {}, [el("span", { class: "grow small", text: "⚠ " + warning })]))));
      }
      box.appendChild(el("p", { class: "small muted",
        text: "Average " + validation.average_marks_per_question + " marks per question · " +
              validation.minutes_per_mark + " minutes per mark · " +
              validation.topic_count + " topics in scope." }));
      hostNode.appendChild(box);
    }

    host.appendChild(renderExaminationList());
  }

  function renderExaminationList() {
    const card = el("div", { class: "card" }, [el("h2", { text: "Examinations in this subject" })]);
    if (!state.examinations.length) {
      card.appendChild(el("div", { class: "empty" }, [
        el("strong", { text: "No examinations yet" }),
        el("p", { class: "muted small", text: "Configure and generate your first paper above." })]));
      return card;
    }
    state.examinations.forEach(function (examination) {
      const entry = el("div", { class: "card", style: "box-shadow:none;background:var(--surface-2)" }, [
        el("div", { class: "card-head" }, [
          el("h3", { text: examination.title }),
          el("div", { class: "spacer" }),
          el("span", { class: "badge", text: "v" + examination.version }),
          el("span", { class: "badge", text: examination.mode }),
          statusBadge(examination.status),
          statusBadge(examination.moderation_status),
        ]),
        el("p", { class: "small muted",
          text: examination.total_marks + " marks · " + examination.duration_minutes +
                " minutes · published " + formatDateTime(examination.published_at) }),
      ]);
      if (examination.moderation_findings && examination.moderation_findings.length) {
        const details = el("details", {}, [
          el("summary", { class: "small muted", style: "cursor:pointer",
            text: examination.moderation_findings.length + " moderation finding(s)" }),
        ]);
        const list = el("ul", { class: "list-plain" });
        examination.moderation_findings.forEach(function (finding) {
          list.appendChild(el("li", {}, [
            el("span", { class: "grow small", text: "[" + finding.severity + "] " + finding.message })]));
        });
        details.appendChild(list);
        entry.appendChild(details);
      }
      const actions = el("div", { style: "display:flex;gap:.5rem;flex-wrap:wrap;margin-top:.6rem" });
      if (examination.status === "published") {
        actions.appendChild(el("button", { class: "btn btn-sm btn-primary", type: "button",
          text: "Sit examination", onclick: function () { startAttempt(examination); } }));
      } else {
        actions.appendChild(el("button", { class: "btn btn-sm btn-primary", type: "button",
          text: "Re-moderate & publish", onclick: async function (event) {
            await withButtonState(event.currentTarget, async function () {
              try {
                await api.post("/api/workspaces/" + state.workspace.id + "/examinations/" +
                  examination.id + "/publish", {});
                toast("Examination published", "ok");
              } catch (error) { toast(error.message, "danger"); }
              await refreshWorkspace(); renderWorkspace();
            });
          } }));
      }
      actions.appendChild(el("button", { class: "btn btn-sm", type: "button", text: "Preview questions",
        onclick: function () { previewExamination(examination); } }));
      actions.appendChild(el("button", { class: "btn btn-sm", type: "button", text: "Generate PDFs",
        onclick: async function (event) {
          await withButtonState(event.currentTarget, async function () {
            try {
              await api.post("/api/workspaces/" + state.workspace.id + "/examinations/" +
                examination.id + "/deliverables", {});
              toast("Memorandum and mastery guide generated", "ok");
              openDeliverableDialog(examination);
            } catch (error) { toast(error.message, "danger"); }
          });
        } }));
      actions.appendChild(el("button", { class: "btn btn-sm", type: "button", text: "Downloads",
        onclick: function () { openDeliverableDialog(examination); } }));
      if (examination.mode === "formal") {
        actions.appendChild(el("button", { class: "btn btn-sm btn-ok", type: "button",
          text: "Release feedback", onclick: async function (event) {
            await withButtonState(event.currentTarget, async function () {
              const result = await api.post("/api/workspaces/" + state.workspace.id +
                "/examinations/" + examination.id + "/release-feedback", {});
              toast(result.released_attempts + " attempt(s) released", "ok");
            });
          } }));
      }
      entry.appendChild(actions);
      card.appendChild(entry);
    });
    return card;
  }

  async function startAttempt(examination) {
    try {
      const attempt = await api.post("/api/workspaces/" + state.workspace.id +
        "/examinations/" + examination.id + "/attempts",
        { student_name: state.user.display_name, student_number: "" });
      window.location.href = "/exam/" + examination.id + "?attempt=" + attempt.id +
        "&workspace=" + state.workspace.id;
    } catch (error) {
      toast(error.message, "danger");
    }
  }

  async function previewExamination(examination) {
    try {
      const detail = await api.get("/api/workspaces/" + state.workspace.id +
        "/examinations/" + examination.id);
      const body = el("div", {});
      body.appendChild(el("p", { class: "small muted",
        text: detail.total_marks + " marks · " + detail.duration_minutes + " minutes · " +
              detail.questions.length + " questions · moderation: " +
              detail.moderation_status.replace(/_/g, " ") }));
      detail.questions.forEach(function (question) {
        const block = el("div", { style: "border-top:1px solid var(--line);padding:.7rem 0" }, [
          el("div", { style: "display:flex;gap:.4rem;flex-wrap:wrap;align-items:center" }, [
            el("strong", { class: "small", text: "Q" + question.ordinal }),
            el("span", { class: "badge", text: question.qtype.replace(/_/g, " ") }),
            el("span", { class: "badge", text: question.marks + " marks" }),
            el("span", { class: "badge", text: question.difficulty }),
            el("span", { class: "badge", text: question.bloom }),
            question.visual ? el("span", { class: "badge badge-info",
              text: "visual v" + question.visual.version }) : null,
          ]),
          el("p", { class: "small", style: "white-space:pre-wrap", text: question.prompt }),
        ]);
        if (question.visual) block.appendChild(el("div", { class: "visual-figure", html: question.visual.svg }));
        if (question.options && question.options.length) {
          block.appendChild(el("ul", { class: "list-plain" }, question.options.map(
            (option) => el("li", {}, [el("span", { class: "grow small", text: "• " + option })]))));
        }
        body.appendChild(block);
      });
      modal("Preview — " + examination.title, [body], async function () { return true; }, "Close", true);
    } catch (error) { toast(error.message, "danger"); }
  }

  async function openDeliverableDialog(examination) {
    try {
      const deliverables = await api.get("/api/workspaces/" + state.workspace.id +
        "/examinations/" + examination.id + "/deliverables");
      const body = el("div", {});
      if (!deliverables.length) {
        body.appendChild(el("p", { class: "muted small",
          text: "No deliverables generated yet. Use “Generate PDFs” first." }));
      }
      deliverables.forEach(function (deliverable) {
        const label = deliverable.kind === "memorandum"
          ? "PDF 1 — Examination Memorandum & Marking Guide"
          : "PDF 2 — Subject Mastery & Examination Preparation Guide";
        const row = el("div", { style: "border-top:1px solid var(--line);padding:.6rem 0" }, [
          el("strong", { class: "small", text: label }),
          el("p", { class: "tiny muted", text: "Version " + deliverable.version +
            " · generated " + formatDateTime(deliverable.created_at) +
            (deliverable.released ? "" : " · protected until released") }),
        ]);
        if (deliverable.released || deliverable.kind === "mastery_guide") {
          row.appendChild(el("a", { class: "btn btn-sm btn-primary",
            href: "/api/workspaces/" + state.workspace.id + "/examinations/" + examination.id +
              "/deliverables/" + deliverable.kind + "/download",
            text: "Download PDF" }));
        } else {
          row.appendChild(el("span", { class: "badge badge-warn",
            text: "Memorandum protected — release feedback to unlock" }));
        }
        body.appendChild(row);
      });
      body.appendChild(el("p", { class: "small muted", style: "margin-top:.75rem",
        text: "Both documents reference examination " + examination.id.slice(0, 12) +
              " version " + examination.version + ", the same version as the examination website." }));
      modal("Deliverables — " + examination.title, [body], async function () { return true; }, "Close", true);
    } catch (error) { toast(error.message, "danger"); }
  }

  /* ---------------------------------------------------------------- results */

  function renderResults(host) {
    const analytics = state.analytics;
    const card = el("div", { class: "card" }, [el("h2", { text: "Performance intelligence" })]);
    if (!analytics) {
      card.appendChild(el("p", { class: "muted small", text: "Analytics are unavailable." }));
      host.appendChild(card);
      return;
    }
    const stats = el("div", { class: "grid grid-4" }, [
      statBox(String(analytics.attempts), "Marked attempts"),
      statBox(analytics.average_percentage !== null ? analytics.average_percentage + "%" : "—",
        "Average score"),
      statBox(String(analytics.mastery.overall || "not assessed").replace(/_/g, " "), "Overall mastery"),
      statBox(String((analytics.by_topic || []).length), "Topics assessed"),
    ]);
    card.appendChild(stats);
    host.appendChild(card);

    if (!analytics.attempts) {
      host.appendChild(el("div", { class: "card empty" }, [
        el("strong", { text: "No marked attempts yet" }),
        el("p", { class: "muted small",
          text: "Sit a practice examination to generate personalised topic mastery and revision priorities." })]));
      return;
    }

    host.appendChild(renderBreakdown("Performance by topic", analytics.by_topic));
    host.appendChild(renderBreakdown("Performance by learning outcome", analytics.by_outcome));
    host.appendChild(renderBreakdown("Performance by difficulty", analytics.by_difficulty));
    host.appendChild(renderBreakdown("Performance by Bloom level", analytics.by_bloom));

    if (analytics.repeated_mistakes && analytics.repeated_mistakes.length) {
      const cardNode = el("div", { class: "card" }, [el("h2", { text: "Repeated mistakes" })]);
      const list = el("ul", { class: "list-plain" });
      analytics.repeated_mistakes.forEach(function (mistake) {
        list.appendChild(el("li", {}, [
          el("span", { class: "grow small", text: mistake.text }),
          el("span", { class: "badge badge-danger", text: mistake.count + "× incorrect" }),
        ]));
      });
      cardNode.appendChild(list);
      host.appendChild(cardNode);
    }

    const recCard = el("div", { class: "card" }, [el("h2", { text: "Revision recommendations" })]);
    const recList = el("ul", { class: "list-plain" });
    (analytics.recommendations || []).forEach(function (recommendation) {
      recList.appendChild(el("li", {}, [el("span", { class: "grow small", text: recommendation })]));
    });
    recCard.appendChild(recList);
    host.appendChild(recCard);

    const historyCard = el("div", { class: "card" }, [el("h2", { text: "Attempt history" })]);
    const table = el("table", { class: "data" }, [
      el("thead", {}, [el("tr", {}, ["Examination", "Version", "Mode", "Submitted", "Score", "Result", ""]
        .map((h) => el("th", { text: h })))]),
    ]);
    const tbody = el("tbody");
    analytics.history.slice().reverse().forEach(function (entry) {
      tbody.appendChild(el("tr", {}, [
        el("td", { text: entry.title }),
        el("td", { text: "v" + entry.version }),
        el("td", { text: entry.mode }),
        el("td", { class: "small", text: formatDateTime(entry.submitted_at) }),
        el("td", { text: entry.percentage !== null ? entry.percentage + "%" : "—" }),
        el("td", {}, [statusBadge(entry.percentage >= 70 ? "competent" :
          entry.percentage >= 50 ? "developing" : "requires_improvement")]),
        el("td", {}, [el("button", { class: "btn btn-sm", type: "button", text: "View result",
          onclick: function () { showAttemptResult(entry.attempt_id); } })]),
      ]));
    });
    table.appendChild(tbody);
    historyCard.appendChild(el("div", { class: "table-wrap" }, [table]));
    host.appendChild(historyCard);
  }

  function statBox(value, label) {
    return el("div", { class: "stat" }, [
      el("div", { class: "value", text: value }),
      el("div", { class: "label", text: label }),
    ]);
  }

  function renderBreakdown(title, rows) {
    const card = el("div", { class: "card" }, [el("h2", { text: title })]);
    if (!rows || !rows.length) {
      card.appendChild(el("p", { class: "muted small", text: "No data recorded yet." }));
      return card;
    }
    const table = el("table", { class: "data" }, [
      el("thead", {}, [el("tr", {}, ["Item", "Score", "Mastery", "Progress"]
        .map((h) => el("th", { text: h })))]),
    ]);
    const tbody = el("tbody");
    rows.forEach(function (row) {
      const kind = row.percentage >= 70 ? "is-ok" : row.percentage >= 50 ? "is-warn" : "is-danger";
      const progress = el("div", { class: "progress " + kind });
      progress.appendChild(el("i", { style: "width:" + Math.max(2, Math.min(100, row.percentage)) + "%" }));
      tbody.appendChild(el("tr", {}, [
        el("td", { text: row.name }),
        el("td", { class: "nowrap", text: row.percentage + "% (" + row.awarded + "/" + row.max + ")" }),
        el("td", {}, [statusBadge(row.mastery)]),
        el("td", { style: "min-width:110px" }, [progress]),
      ]));
    });
    table.appendChild(tbody);
    card.appendChild(el("div", { class: "table-wrap" }, [table]));
    return card;
  }

  async function showAttemptResult(attemptId) {
    try {
      const result = await api.get("/api/workspaces/" + state.workspace.id +
        "/attempts/" + attemptId + "/result");
      const body = el("div", {});
      if (result.feedback_released) {
        body.appendChild(el("div", { class: "result-score" }, [
          el("div", { class: "pct", text: result.attempt.percentage + "%" }),
          el("div", { class: "fraction",
            text: result.attempt.score + " / " + result.attempt.max_score + " marks" }),
        ]));
      } else {
        body.appendChild(alertBox("info",
          "This is a formal simulation. Feedback and the memorandum are released by your lecturer."));
      }
      body.appendChild(el("h3", { text: "Topic mastery for this attempt" }));
      (result.analytics.by_topic || []).forEach(function (row) {
        body.appendChild(el("div", { style: "margin-bottom:.5rem" }, [
          el("div", { style: "display:flex;gap:.5rem;align-items:center" }, [
            el("span", { class: "small grow", text: row.name }),
            el("span", { class: "badge", text: row.percentage + "%" }),
            statusBadge(row.mastery),
          ]),
        ]));
      });
      if (result.memorandum) {
        body.appendChild(el("h3", { text: "Question-by-question feedback" }));
        result.memorandum.forEach(function (entry, index) {
          const ratio = entry.max_marks ? entry.awarded / entry.max_marks : 0;
          const kind = ratio >= 0.99 ? "correct" : ratio > 0 ? "partial" : "incorrect";
          const block = el("div", { class: "mark-row " + kind }, [
            el("div", { class: "mark-head" }, [
              el("strong", { class: "small", text: "Q" + (index + 1) }),
              el("span", { class: "badge", text: entry.awarded + "/" + entry.max_marks }),
            ]),
            el("p", { class: "small", style: "white-space:pre-wrap", text: entry.prompt }),
            el("p", { class: "small", text: "Model answer: " + entry.expected_answer }),
            el("p", { class: "tiny muted", text: entry.rationale }),
          ]);
          if (entry.explanation) {
            block.appendChild(el("p", { class: "tiny muted", text: "Explanation: " + entry.explanation }));
          }
          body.appendChild(block);
        });
      }
      modal("Result — " + result.attempt.student_name, [body],
        async function () { return true; }, "Close", true);
    } catch (error) { toast(error.message, "danger"); }
  }

  /* ---------------------------------------------------------------- modal */

  function modal(title, children, onConfirm, confirmLabel, dismissOnly) {
    const backdrop = el("div", { class: "modal-backdrop", role: "dialog", "aria-modal": "true",
      "aria-label": title });
    const box = el("div", { class: "modal" }, [el("h2", { text: title })]);
    children.forEach(function (child) { if (child) box.appendChild(child); });
    const actions = el("div", { class: "modal-actions" });
    if (!dismissOnly) {
      actions.appendChild(el("button", { class: "btn", type: "button", text: "Cancel",
        onclick: function () { backdrop.remove(); } }));
      const confirm = el("button", { class: "btn btn-primary", type: "button",
        text: confirmLabel || "Confirm" });
      confirm.addEventListener("click", async function () {
        const keep = await onConfirm(confirm);
        if (keep !== false) backdrop.remove();
      });
      actions.appendChild(confirm);
    } else {
      actions.appendChild(el("button", { class: "btn btn-primary", type: "button",
        text: confirmLabel || "Close", onclick: function () { backdrop.remove(); } }));
    }
    box.appendChild(actions);
    backdrop.appendChild(box);
    backdrop.addEventListener("click", function (event) {
      if (event.target === backdrop) backdrop.remove();
    });
    document.body.appendChild(backdrop);
    const focusable = box.querySelector("input, textarea, select, button");
    if (focusable) focusable.focus();
    return backdrop;
  }
})();
