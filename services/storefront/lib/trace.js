// One trace id per page-load session: generated lazily on first use in the
// browser bundle and reused for every gateway call until the next full page
// load, so one user journey shows up as one trace family in Motadata.

let traceId = null;

export function getTraceId() {
  if (!traceId) {
    traceId =
      typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
        ? crypto.randomUUID()
        : `sv-${Date.now().toString(16)}-${Math.random().toString(16).slice(2, 10)}`;
  }
  return traceId;
}
