import { relativeAge } from "../lib/aqi";

/**
 * Surfacing ingest health in the product itself, not only in Grafana.
 *
 * This app's most dangerous failure is silent: if the poller stops, the charts
 * keep rendering yesterday's readings and clean air is indistinguishable from
 * a dead pipeline. A user looking at a number needs to know how old it is.
 */
export default function PipelinePanel({ status }) {
  if (!status) return <p className="placeholder">Ingest status unavailable.</p>;

  return (
    <dl className="kv">
      <dt>Last poll</dt>
      <dd className={status.last_run_status === "ok" ? "status-ok" : "status-bad"}>
        {status.last_run_status ?? "never"}
      </dd>

      <dt>Newest reading</dt>
      <dd className={status.stale ? "status-bad" : ""}>
        {relativeAge(status.data_age_minutes)}
      </dd>

      <dt>Rows last run</dt>
      <dd>{status.rows_inserted_last_run ?? "—"}</dd>

      <dt>Readings stored</dt>
      <dd>{status.total_readings.toLocaleString()}</dd>
    </dl>
  );
}
