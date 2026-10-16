import React, { useState } from 'react';
import {
  CheckCircle2,
  Brain,
  ShieldCheck,
  FileSearch,
  History,
  Lightbulb,
  AlertCircle,
  Loader2,
  Server,
} from 'lucide-react';

const DISPLAY_LIMIT = 40;

function parseReport(report) {
  if (!report) return null;
  if (typeof report === 'string') {
    try {
      return JSON.parse(report);
    } catch {
      return null;
    }
  }
  return report;
}

function formatConfidence(value) {
  if (typeof value !== 'number' || Number.isNaN(value)) return null;
  const fraction = value <= 1 ? value : value / 100;
  return `${Math.round(fraction * 100)}% (${fraction.toFixed(2)})`;
}

function formatTimestamp(value) {
  if (!value) return '—';
  return String(value).replace('T', ' ').replace('+00:00', 'Z');
}

function formatValue(value) {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(4);
  return String(value);
}

function EmptyNote({ children }) {
  return (
    <p className="text-xs text-slate-500 bg-white border border-slate-200 rounded-lg p-3">
      {children}
    </p>
  );
}

function BulletList({ items }) {
  if (!items?.length) return <EmptyNote>None returned by the backend.</EmptyNote>;
  return (
    <ul className="space-y-2">
      {items.map((item, idx) => (
        <li key={idx} className="text-xs text-slate-700 leading-relaxed bg-white border border-slate-200 rounded-lg p-3">
          {typeof item === 'string' ? item : JSON.stringify(item)}
        </li>
      ))}
    </ul>
  );
}

function TelemetryRows({ rows, emptyLabel, renderRow }) {
  if (!rows?.length) return <EmptyNote>{emptyLabel}</EmptyNote>;
  const visible = rows.slice(0, DISPLAY_LIMIT);
  return (
    <div className="space-y-2">
      <p className="text-[11px] text-slate-500">
        Showing {visible.length} of {rows.length} returned by the backend.
      </p>
      <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
        {visible.map(renderRow)}
      </div>
    </div>
  );
}

const TABS = [
  { id: 'logs', label: 'Logs' },
  { id: 'metrics', label: 'Metrics' },
  { id: 'traces', label: 'Traces' },
];

const InvestigationResult = ({
  investigation = null,
  telemetry = null,
  telemetryLoading = false,
  telemetryError = null,
}) => {
  const [tab, setTab] = useState('logs');

  if (!investigation && !telemetry && !telemetryLoading && !telemetryError) {
    return null;
  }

  const report = parseReport(investigation?.report);
  const status = investigation?.status || '';
  const confidence = formatConfidence(
    typeof investigation?.confidence === 'number' ? investigation.confidence : report?.confidence
  );
  const isFailed = status === 'failed';
  const isPartial = status === 'completed_partial';
  const bannerClass = isFailed
    ? 'bg-red-50 border-red-200'
    : isPartial
    ? 'bg-amber-50 border-amber-200'
    : 'bg-emerald-50 border-emerald-200';
  const bannerText = isFailed
    ? 'text-red-900'
    : isPartial
    ? 'text-amber-900'
    : 'text-emerald-900';
  const bannerIcon = isFailed
    ? 'bg-red-100 text-red-700'
    : isPartial
    ? 'bg-amber-100 text-amber-700'
    : 'bg-emerald-100 text-emerald-700';

  const logs = telemetry?.logs || [];
  const metrics = telemetry?.metrics || [];
  const traces = telemetry?.traces || [];
  const counts = { logs: logs.length, metrics: metrics.length, traces: traces.length };

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-6 shadow-xs">
      {investigation && (
        <div className={`border rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4 ${bannerClass}`}>
          <div className="flex items-start gap-3">
            <div className={`p-2 rounded-lg shrink-0 mt-0.5 ${bannerIcon}`}>
              {isFailed ? <AlertCircle className="h-5 w-5" /> : <CheckCircle2 className="h-5 w-5" />}
            </div>
            <div>
              <h3 className={`text-sm font-semibold font-sans ${bannerText}`}>
                {isFailed
                  ? 'Investigation failed'
                  : isPartial
                  ? 'Investigation completed with partial results'
                  : 'Investigation completed'}
              </h3>
              <p className={`text-xs mt-0.5 leading-relaxed ${bannerText}`}>
                Status from the backend: {status || 'unknown'}. Evidence items used: {investigation.evidence_count ?? 0}.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1.5 bg-white px-3 py-1.5 rounded-lg border border-slate-200 shrink-0 text-slate-700 font-medium text-xs shadow-xs">
            <FileSearch className="h-4 w-4 text-[#384959]" />
            <span>{investigation.evidence_count ?? 0} evidence items</span>
          </div>
        </div>
      )}

      {investigation && (
        <div className="space-y-4">
          <h4 className="text-xs font-semibold text-slate-800 uppercase tracking-wider flex items-center gap-2">
            <Brain className="h-4 w-4 text-[#384959]" />
            Root Cause Analysis
          </h4>

          {!report ? (
            <EmptyNote>The backend did not return a root cause report.</EmptyNote>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-2 md:col-span-2">
                <span className="flex items-center gap-1.5 text-slate-800 font-semibold text-xs">
                  <Brain className="h-3.5 w-3.5 text-[#384959]" />
                  Root cause
                </span>
                <p className="text-xs text-slate-700 leading-relaxed">{report.root_cause || 'None returned by the backend.'}</p>
              </div>

              <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-2">
                <span className="flex items-center gap-1.5 text-slate-800 font-semibold text-xs">
                  <ShieldCheck className="h-3.5 w-3.5 text-amber-600" />
                  Confidence
                </span>
                <div className="text-lg font-bold font-mono text-slate-800">
                  {confidence || 'None returned by the backend.'}
                </div>
              </div>

              <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-2">
                <span className="flex items-center gap-1.5 text-slate-800 font-semibold text-xs">
                  <Server className="h-3.5 w-3.5 text-[#6A89A7]" />
                  Affected services
                </span>
                {report.affected_services?.length ? (
                  <div className="flex flex-wrap gap-2">
                    {report.affected_services.map((service) => (
                      <span key={service} className="text-xs font-medium bg-white border border-slate-200 text-slate-700 px-2 py-1 rounded-lg">
                        {service}
                      </span>
                    ))}
                  </div>
                ) : (
                  <EmptyNote>None returned by the backend.</EmptyNote>
                )}
              </div>

              <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-2 md:col-span-2">
                <span className="flex items-center gap-1.5 text-slate-800 font-semibold text-xs">
                  <FileSearch className="h-3.5 w-3.5 text-[#6A89A7]" />
                  Supporting evidence
                </span>
                <BulletList items={report.supporting_evidence} />
              </div>

              <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-2">
                <span className="flex items-center gap-1.5 text-slate-800 font-semibold text-xs">
                  <History className="h-3.5 w-3.5 text-blue-600" />
                  Timeline
                </span>
                {report.timeline?.length ? (
                  <div className="space-y-2">
                    {report.timeline.map((entry, idx) => (
                      <div key={idx} className="text-xs bg-white border border-slate-200 rounded-lg p-3">
                        <div className="font-mono text-slate-500">{formatTimestamp(entry.timestamp)}</div>
                        <div className="text-slate-700 mt-1">{entry.event}</div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyNote>None returned by the backend.</EmptyNote>
                )}
              </div>

              <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-2">
                <span className="flex items-center gap-1.5 text-slate-800 font-semibold text-xs">
                  <Lightbulb className="h-3.5 w-3.5 text-yellow-600" />
                  Recommended actions
                </span>
                <BulletList items={report.recommended_actions} />
              </div>

              <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-2 md:col-span-2">
                <span className="text-slate-800 font-semibold text-xs">Alternative explanations</span>
                <BulletList items={report.alternative_explanations} />
              </div>

              <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-2 md:col-span-2">
                <span className="flex items-center gap-1.5 text-slate-800 font-semibold text-xs">
                  <History className="h-3.5 w-3.5 text-[#384959]" />
                  RAG / historical context
                </span>
                <p className="text-[11px] text-slate-500">
                  Similar past incidents retrieved as context. They are not proof of this incident&apos;s root cause.
                  These are historical scenario ids, not live incident ids, and they do not open another incident.
                </p>
                {report.relevant_historical_incidents?.length ? (
                  <div className="space-y-2">
                    {report.relevant_historical_incidents.map((item, idx) => (
                      <div key={`${item.incident_id}-${idx}`} className="text-xs bg-white border border-slate-200 rounded-lg p-3 space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono font-semibold text-slate-800">{item.incident_id}</span>
                          {item.incident_type && (
                            <span className="px-2 py-0.5 rounded border border-slate-200 bg-slate-50 text-slate-600">
                              {item.incident_type}
                            </span>
                          )}
                          <span className="text-slate-500">similarity {formatValue(item.similarity_score)}</span>
                        </div>
                        {item.relevance && <p className="text-slate-700 leading-relaxed">{item.relevance}</p>}
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyNote>No historical incidents were returned.</EmptyNote>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="space-y-4 pt-2 border-t border-slate-100">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <h4 className="text-xs font-semibold text-slate-800 uppercase tracking-wider flex items-center gap-2">
            <FileSearch className="h-4 w-4 text-[#384959]" />
            Telemetry evidence
          </h4>
          {telemetry?.time_window && (
            <span className="text-[11px] font-mono text-slate-500">
              {formatTimestamp(telemetry.time_window.start)} — {formatTimestamp(telemetry.time_window.end)}
            </span>
          )}
        </div>

        {telemetryLoading && (
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin text-[#384959]" />
            Loading logs, metrics, and traces from the backend.
          </div>
        )}

        {telemetryError && (
          <div className="bg-red-50 border border-red-200 text-red-800 p-3 rounded-lg text-xs flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-red-600 shrink-0" />
            <span>{telemetryError}</span>
          </div>
        )}

        {!telemetryLoading && !telemetryError && telemetry && (
          <>
            <div className="flex items-center gap-2">
              {TABS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setTab(item.id)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
                    tab === item.id
                      ? 'bg-[#384959] text-white border-[#384959]'
                      : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
                  }`}
                >
                  {item.label} ({counts[item.id]})
                </button>
              ))}
            </div>

            {tab === 'logs' && (
              <TelemetryRows
                rows={logs}
                emptyLabel="No logs were returned for this incident window."
                renderRow={(log, idx) => (
                  <div key={idx} className="text-xs bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-1">
                    <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                      <span className="font-mono">{formatTimestamp(log.timestamp)}</span>
                      <span className="font-semibold text-slate-700">{log.level || '—'}</span>
                      <span>{log.service || '—'}</span>
                      <span className="uppercase tracking-wide">{log.source || 'loki'}</span>
                    </div>
                    <p className="text-slate-800 font-mono whitespace-pre-wrap break-words">{log.message || '—'}</p>
                  </div>
                )}
              />
            )}

            {tab === 'metrics' && (
              <TelemetryRows
                rows={metrics}
                emptyLabel="No metrics were returned for this incident window."
                renderRow={(metric, idx) => (
                  <div key={idx} className="text-xs bg-slate-50 border border-slate-200 rounded-lg p-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                    <div>
                      <div className="font-semibold text-slate-800">{metric.metric_name || '—'}</div>
                      <div className="text-[11px] text-slate-500 mt-0.5">
                        {metric.service || '—'} · {formatTimestamp(metric.timestamp)} · {metric.source || 'prometheus'}
                      </div>
                    </div>
                    <div className="font-mono font-bold text-slate-800">{formatValue(metric.value)}</div>
                  </div>
                )}
              />
            )}

            {tab === 'traces' && (
              <TelemetryRows
                rows={traces}
                emptyLabel="No traces were returned for this incident window."
                renderRow={(trace, idx) => (
                  <div key={idx} className="text-xs bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-slate-800">{trace.operation || '—'}</span>
                      <span className={`px-1.5 py-0.5 rounded border text-[10px] font-semibold ${
                        String(trace.status).toLowerCase() === 'error'
                          ? 'bg-red-50 text-red-700 border-red-200'
                          : 'bg-emerald-50 text-emerald-700 border-emerald-200'
                      }`}>
                        {trace.status || '—'}
                      </span>
                    </div>
                    <div className="text-[11px] text-slate-500">
                      {trace.service || '—'} · {formatValue(trace.duration_ms)} ms · {formatTimestamp(trace.timestamp)} · {trace.source || 'jaeger'}
                    </div>
                    {trace.trace_id && (
                      <div className="font-mono text-[11px] text-slate-500 break-all">trace {trace.trace_id}</div>
                    )}
                  </div>
                )}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default InvestigationResult;
