// Server-side gateway fetch for server components. Generates a fresh uuid4
// trace id per request (contract: every service generates one when absent)
// and never throws — pages render an ErrorBanner from the result instead.

import { randomUUID } from "crypto";

const GATEWAY_URL = process.env.GATEWAY_URL || "http://gateway:8080";

export async function gatewayFetch(path) {
  const traceId = randomUUID();
  try {
    const res = await fetch(`${GATEWAY_URL}${path}`, {
      cache: "no-store",
      headers: { "X-Trace-Id": traceId },
    });
    let data = null;
    try {
      data = await res.json();
    } catch {
      // non-JSON upstream body
    }
    if (!res.ok) {
      return {
        ok: false,
        status: res.status,
        error: (data && data.error) || `upstream returned ${res.status}`,
        traceId: (data && data.trace_id) || traceId,
      };
    }
    return { ok: true, status: res.status, data, traceId: (data && data.trace_id) || traceId };
  } catch (err) {
    return { ok: false, status: 0, error: `gateway unreachable: ${err.message}`, traceId };
  }
}
