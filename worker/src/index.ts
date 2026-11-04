export interface Env {
  ALLOWED_ORIGIN?: string;
}

const jsonHeaders = {
  "Content-Type": "application/json",
  "Cache-Control": "no-store",
  "X-Content-Type-Options": "nosniff",
};

function response(body: unknown, status = 200, origin = "", allowed = ""): Response {
  const headers = new Headers(jsonHeaders);
  headers.set("Vary", "Origin");
  if (origin && origin === allowed) headers.set("Access-Control-Allow-Origin", origin);
  return new Response(JSON.stringify(body), { status, headers });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const origin = request.headers.get("Origin") ?? "";
    const allowed = env.ALLOWED_ORIGIN ?? "https://omendi-atlan.github.io";
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      if (origin !== allowed) return response({ error: "Origin not allowed." }, 403);
      const headers = new Headers();
      headers.set("Access-Control-Allow-Origin", origin);
      headers.set("Access-Control-Allow-Methods", "GET, OPTIONS");
      headers.set("Access-Control-Allow-Headers", "Content-Type");
      headers.set("Vary", "Origin");
      return new Response(null, { status: 204, headers });
    }

    if (origin !== allowed) return response({ error: "Origin not allowed." }, 403);
    if (url.pathname === "/health" && request.method === "GET") {
      return response({ status: "ok", service: "examgen-ai-transition-worker" }, 200, origin, allowed);
    }
    if (url.pathname === "/api/examinations/generate") {
      return response(
        { error: "This legacy generation endpoint is retired. Use the authenticated Python API and an approved blueprint." },
        410,
        origin,
        allowed,
      );
    }
    return response({ error: "Not found." }, 404, origin, allowed);
  },
};
