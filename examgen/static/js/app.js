/* EXAMGEN AI — shared API client and UI helpers. */
(function (global) {
  "use strict";

  const TOKEN_KEY = "examgen.token";

  const store = {
    get token() { return localStorage.getItem(TOKEN_KEY) || ""; },
    set token(value) {
      if (value) localStorage.setItem(TOKEN_KEY, value);
      else localStorage.removeItem(TOKEN_KEY);
    },
    get workspaceId() { return localStorage.getItem("examgen.workspace") || ""; },
    set workspaceId(value) {
      if (value) localStorage.setItem("examgen.workspace", value);
      else localStorage.removeItem("examgen.workspace");
    },
  };

  class ApiError extends Error {
    constructor(message, status, detail) {
      super(message);
      this.name = "ApiError";
      this.status = status;
      this.detail = detail;
    }
  }

  async function request(path, options) {
    const opts = Object.assign({ headers: {} }, options || {});
    opts.headers = Object.assign({}, opts.headers);
    if (store.token) opts.headers["Authorization"] = "Bearer " + store.token;
    if (opts.body && !(opts.body instanceof FormData)) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(opts.body);
    }
    const response = await fetch(path, opts);
    if (response.status === 204) return null;
    const text = await response.text();
    let payload = null;
    if (text) {
      try { payload = JSON.parse(text); } catch (_) { payload = { detail: text }; }
    }
    if (!response.ok) {
      const detail = payload && payload.detail ? payload.detail : response.statusText;
      throw new ApiError(
        typeof detail === "string" ? detail : JSON.stringify(detail),
        response.status, payload);
    }
    return payload;
  }

  const api = {
    store,
    ApiError,
    get: (path) => request(path),
    post: (path, body) => request(path, { method: "POST", body: body || {} }),
    put: (path, body) => request(path, { method: "PUT", body: body || {} }),
    patch: (path, body) => request(path, { method: "PATCH", body: body || {} }),
    del: (path) => request(path, { method: "DELETE" }),
    upload: (path, formData) => request(path, { method: "POST", body: formData }),
  };

  /* ------------------------------------------------------------ UI helpers */

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (key) {
        const value = attrs[key];
        if (value === null || value === undefined || value === false) return;
        if (key === "class") node.className = value;
        else if (key === "text") node.textContent = value;
        else if (key === "html") node.innerHTML = value;
        else if (key === "dataset") Object.assign(node.dataset, value);
        else if (key.startsWith("on") && typeof value === "function") {
          node.addEventListener(key.slice(2).toLowerCase(), value);
        } else if (value === true) node.setAttribute(key, "");
        else node.setAttribute(key, value);
      });
    }
    (children || []).forEach(function (child) {
      if (child === null || child === undefined || child === false) return;
      node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    });
    return node;
  }

  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

  function escapeHtml(text) {
    return String(text === null || text === undefined ? "" : text)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function badge(text, kind) {
    return el("span", { class: "badge" + (kind ? " badge-" + kind : ""), text: text });
  }

  function statusBadge(status) {
    const map = {
      approved: "ok", sufficient: "ok", ok: "ok", marked: "ok", published: "ok",
      strong_mastery: "ok", competent: "ok",
      requires_review: "warn", partial: "warn", developing: "warn", warning: "warn",
      expired: "warn", draft: "warn", proposed: "warn",
      rejected: "danger", failed: "danger", insufficient: "danger",
      requires_improvement: "danger", error: "danger",
      pending: "info", in_progress: "info", submitted: "info", uploaded: "info",
      extracted: "info", classified: "info", processing: "info",
      not_assessed: "",
    };
    const label = String(status || "").replace(/_/g, " ");
    return badge(label, map[status] !== undefined ? map[status] : "");
  }

  function alertBox(kind, message) {
    return el("div", { class: "alert alert-" + kind, role: "status", text: message });
  }

  function spinner(dark) {
    return el("span", { class: "spinner" + (dark ? " spinner-dark" : ""), "aria-hidden": "true" });
  }

  async function withButtonState(button, task) {
    const original = button.innerHTML;
    button.disabled = true;
    clear(button);
    button.appendChild(spinner());
    button.appendChild(document.createTextNode(" Working…"));
    try {
      return await task();
    } finally {
      button.disabled = false;
      button.innerHTML = original;
    }
  }

  function toast(message, kind) {
    let host = document.getElementById("toast-host");
    if (!host) {
      host = el("div", { id: "toast-host", "aria-live": "polite",
        style: "position:fixed;right:1rem;bottom:1rem;z-index:200;display:flex;flex-direction:column;gap:.5rem;max-width:340px;" });
      document.body.appendChild(host);
    }
    const node = el("div", { class: "alert alert-" + (kind || "info"),
      style: "margin:0;box-shadow:var(--shadow);background:#fff;", text: message });
    host.appendChild(node);
    setTimeout(function () { node.remove(); }, kind === "danger" ? 8000 : 4200);
  }

  function requireAuth() {
    if (!store.token) {
      window.location.href = "/";
      return false;
    }
    return true;
  }

  function formatDateTime(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (isNaN(date.getTime())) return "—";
    return date.toLocaleString(undefined, {
      year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  }

  function formatDuration(seconds) {
    if (seconds === null || seconds === undefined) return "—";
    const safe = Math.max(0, Math.floor(seconds));
    const h = Math.floor(safe / 3600);
    const m = Math.floor((safe % 3600) / 60);
    const s = safe % 60;
    const pad = (n) => String(n).padStart(2, "0");
    return (h > 0 ? h + ":" : "") + pad(m) + ":" + pad(s);
  }

  global.EXAMGEN = {
    api, el, clear, escapeHtml, badge, statusBadge, alertBox, spinner,
    withButtonState, toast, requireAuth, formatDateTime, formatDuration, store,
  };
})(window);
