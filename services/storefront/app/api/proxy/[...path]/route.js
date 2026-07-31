// Catch-all proxy: /api/proxy/<path> → ${GATEWAY_URL}/api/<path>.
// The browser only ever talks to the storefront; this handler forwards the
// caller's X-Trace-Id (generating a uuid4 if absent, per the contract) and
// mirrors the upstream status/body back — including injected 500s, whose
// trace_id the UI surfaces on purpose.

export const dynamic = "force-dynamic";

const GATEWAY_URL = process.env.GATEWAY_URL || "http://gateway:8080";

async function forward(request, { params }) {
  const path = (params.path || []).join("/");
  const search = new URL(request.url).search;
  const traceId = request.headers.get("x-trace-id") || crypto.randomUUID();

  const init = {
    method: request.method,
    cache: "no-store",
    headers: { "X-Trace-Id": traceId },
  };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.headers["Content-Type"] =
      request.headers.get("content-type") || "application/json";
    init.body = await request.text();
  }

  let upstream;
  try {
    upstream = await fetch(`${GATEWAY_URL}/api/${path}${search}`, init);
  } catch (err) {
    return Response.json(
      { error: `gateway unreachable: ${err.message}`, trace_id: traceId },
      { status: 502, headers: { "X-Trace-Id": traceId } }
    );
  }

  const body = await upstream.text();
  return new Response(body, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("content-type") || "application/json",
      "X-Trace-Id": upstream.headers.get("x-trace-id") || traceId,
    },
  });
}

export {
  forward as GET,
  forward as POST,
  forward as PUT,
  forward as PATCH,
  forward as DELETE,
};
