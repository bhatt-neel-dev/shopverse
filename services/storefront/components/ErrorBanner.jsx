// Every failed gateway call surfaces its trace_id on purpose — paste it into
// Motadata to jump from the broken page straight to the trace/logs.
export default function ErrorBanner({ error }) {
  if (!error) return null;
  const message = typeof error === "string" ? error : error.message;
  const traceId = typeof error === "object" ? error.traceId : null;
  return (
    <div className="error-banner" role="alert">
      <strong>Something went wrong:</strong> {message}
      {traceId && (
        <div className="trace">
          trace_id: <code>{traceId}</code>
        </div>
      )}
    </div>
  );
}
