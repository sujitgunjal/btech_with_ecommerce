import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  Clock,
  ArrowLeft,
  FileText,
  ChevronRight,
  Activity,
  Terminal,
  Loader2,
  AlertCircle,
  CheckCircle2,
  Info,
  History,
  Server,
} from 'lucide-react';
import SeverityBadge from '../components/SeverityBadge';
import StatusBadge from '../components/StatusBadge';
import DemoDataBadge from '../components/DemoDataBadge';
import { getIncidentById, getIncidentEvidence } from '../services/incidentService';
import { getServices } from '../services/serviceService';

function finiteNumbers(metrics, names) {
  return (metrics || [])
    .filter((metric) => names.includes(metric.metric_name))
    .map((metric) => Number(metric.value))
    .filter((value) => Number.isFinite(value));
}

function percentile(values, p) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil((p / 100) * sorted.length) - 1));
  return sorted[index];
}

function detectionFromEvidence(evidence) {
  const metrics = evidence?.metrics || [];
  const latencySeconds = percentile(finiteNumbers(metrics, ['latency', 'request_latency']), 99);
  const errorRates = finiteNumbers(metrics, ['error_rate']);
  const requestRates = finiteNumbers(metrics, ['request_rate']);
  const errorSum = errorRates.reduce((sum, value) => sum + value, 0);
  const requestSum = requestRates.reduce((sum, value) => sum + value, 0);

  let errorRatePct = null;
  if (requestSum > 0) {
    errorRatePct = (errorSum / requestSum) * 100;
  } else if (errorRates.length > 0 && errorSum === 0) {
    errorRatePct = 0;
  }

  return {
    latencyMs: latencySeconds === null ? null : latencySeconds * 1000,
    errorRatePct,
  };
}

const IncidentDetailsPage = () => {
  const { id } = useParams();
  const targetId = id || 'INC-001';

  const [incident, setIncident] = useState(null);
  const [liveServices, setLiveServices] = useState([]);
  const [detection, setDetection] = useState({ latencyMs: null, errorRatePct: null });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isMock, setIsMock] = useState(false);

  const fetchIncidentDetails = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [incidentRes, servicesRes] = await Promise.all([
        getIncidentById(targetId),
        getServices(),
      ]);

      setIncident(incidentRes.data || null);
      setLiveServices(servicesRes.data || []);
      setIsMock(Boolean(incidentRes.isMock || servicesRes.isMock));

      const evidenceId = incidentRes.data?.db_id ?? targetId;
      try {
        const evidenceRes = await getIncidentEvidence(evidenceId);
        setDetection(detectionFromEvidence(evidenceRes.data));
      } catch (evidenceErr) {
        console.error('[IncidentDetailsPage] Error loading detection telemetry:', evidenceErr);
        setDetection({ latencyMs: null, errorRatePct: null });
      }
    } catch (err) {
      console.error('[IncidentDetailsPage] Error fetching incident details:', err);
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : err?.message || 'Failed to load incident details.');
    } finally {
      setLoading(false);
    }
  }, [targetId]);

  useEffect(() => {
    fetchIncidentDetails();
  }, [fetchIncidentDetails]);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-2 text-xs text-slate-500 font-sans">
          <Link to="/incidents" className="hover:text-slate-800 flex items-center gap-1 font-medium">
            <ArrowLeft className="h-3.5 w-3.5" />
            Incidents
          </Link>
          <ChevronRight className="h-3 w-3 text-slate-400" />
          <span className="text-slate-800 font-semibold font-mono">{targetId}</span>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-12 flex flex-col items-center justify-center gap-3 text-slate-500 shadow-xs">
          <Loader2 className="h-8 w-8 text-[#384959] animate-spin" />
          <p className="text-xs font-medium">Fetching incident details and live telemetry...</p>
        </div>
      </div>
    );
  }

  if (error || !incident) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-2 text-xs text-slate-500 font-sans">
          <Link to="/incidents" className="hover:text-slate-800 flex items-center gap-1 font-medium">
            <ArrowLeft className="h-3.5 w-3.5" />
            Incidents
          </Link>
          <ChevronRight className="h-3 w-3 text-slate-400" />
          <span className="text-slate-800 font-semibold font-mono">{targetId}</span>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-8 text-center text-slate-600 shadow-xs space-y-4">
          <AlertCircle className="h-10 w-10 text-red-500 mx-auto" />
          <h2 className="text-base font-semibold text-slate-800">Incident Details Unavailable</h2>
          <p className="text-xs text-slate-500">{error || `Could not find incident record for ${targetId}`}</p>
          <div className="flex items-center justify-center gap-3">
            <button
              onClick={fetchIncidentDetails}
              className="px-4 py-2 bg-[#384959] text-white rounded-lg text-xs font-semibold hover:bg-[#2b3844] transition-all"
            >
              Retry
            </button>
            <Link
              to="/incidents"
              className="px-4 py-2 bg-slate-100 text-slate-700 rounded-lg text-xs font-semibold hover:bg-slate-200 transition-all border border-slate-200"
            >
              Back to Incidents
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const targetServiceName = incident.service || incident.affectedService || 'order-service';
  const liveServiceObj = liveServices.find(
    (s) => s.name?.toLowerCase() === targetServiceName.toLowerCase()
  );
  const liveStatus = liveServiceObj?.status
    ? liveServiceObj.status.charAt(0).toUpperCase() + liveServiceObj.status.slice(1)
    : 'Unknown';
  const isRecovered = liveStatus.toLowerCase() === 'healthy' && incident.status?.toLowerCase() !== 'resolved';

  return (
    <div className="space-y-6">
      {/* Breadcrumb & Demo Badge */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-xs text-slate-500 font-sans">
          <Link to="/incidents" className="hover:text-slate-800 flex items-center gap-1 font-medium">
            <ArrowLeft className="h-3.5 w-3.5" />
            Incidents
          </Link>
          <ChevronRight className="h-3 w-3 text-slate-400" />
          <span className="text-slate-800 font-semibold font-mono">{incident.id}</span>
        </div>
        {isMock && <DemoDataBadge />}
      </div>

      {/* Incident Header */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-4 shadow-xs">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="space-y-2">
            <div className="flex items-center gap-2.5 flex-wrap">
              <span className="font-mono text-sm font-bold text-slate-800 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                {incident.id}
              </span>
              <SeverityBadge severity={incident.severity} size="xs" />
              <StatusBadge status={incident.status} size="xs" />
              {isRecovered && (
                <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-100 text-emerald-800 border border-emerald-300 flex items-center gap-1">
                  <CheckCircle2 className="h-3 w-3 text-emerald-600" />
                  SERVICE RECOVERED
                </span>
              )}
            </div>
            <h1 className="text-xl font-bold text-slate-800">{incident.title}</h1>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            <Link
              to={`/incidents/${incident.id}/investigate`}
              className="px-4 py-2 text-xs font-semibold rounded-lg bg-[#384959] text-white hover:bg-[#2b3844] transition-all flex items-center gap-2 shadow-xs"
            >
              <Terminal className="h-4 w-4" />
              <span>Open Investigation Workbench</span>
            </Link>
          </div>
        </div>

        <p className="text-sm text-slate-700 bg-slate-50 p-4 rounded-lg border border-slate-200 leading-relaxed">
          {incident.description}
        </p>

        {isRecovered && (
          <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-900 flex items-start gap-2">
            <Info className="h-4 w-4 text-emerald-600 shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold">Service Recovered: </span>
              The affected service (<span className="font-mono font-bold">{targetServiceName}</span>) has returned to operational health, but the incident remains under active investigation.
            </div>
          </div>
        )}
      </div>

      {/* Incident Details Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Details & Metadata */}
        <div className="lg:col-span-2 space-y-6">
          {/* Metadata Card */}
          <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4 shadow-xs">
            <h2 className="text-sm font-semibold text-slate-800 flex items-center gap-2 border-b border-slate-100 pb-3">
              <FileText className="h-4 w-4 text-[#384959]" />
              Incident Specifications
            </h2>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
              <div>
                <span className="text-slate-500 block font-medium">Target Microservice</span>
                <span className="text-slate-800 font-semibold">{targetServiceName}</span>
              </div>
              <div>
                <span className="text-slate-500 block font-medium">Environment</span>
                <span className="text-slate-800 font-semibold">{incident.environment || 'Not available'}</span>
              </div>
              <div>
                <span className="text-slate-500 block font-medium">Trigger Source</span>
                <span className="text-slate-800 font-semibold">{incident.reporter || 'Not available'}</span>
              </div>
              <div>
                <span className="text-slate-500 block font-medium">Assigned Team</span>
                <span className="text-slate-800 font-semibold">{incident.assignedTeam || 'Not available'}</span>
              </div>
              <div>
                <span className="text-slate-500 block font-medium">Incident Created At</span>
                <span className="text-slate-800 font-mono font-semibold">{incident.createdAt || incident.startTime}</span>
              </div>
            </div>
          </div>

          {/* Timeline Card */}
          <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4 shadow-xs">
            <h2 className="text-sm font-semibold text-slate-800 flex items-center gap-2 border-b border-slate-100 pb-3">
              <Clock className="h-4 w-4 text-amber-600" />
              Audit Event Timeline
            </h2>

            <div className="space-y-3 font-mono text-xs">
              {(incident.timeline || []).length === 0 ? (
                <p className="text-xs text-slate-500 font-sans">No timeline was returned by the backend.</p>
              ) : (
                incident.timeline.map((item, idx) => (
                  <div key={idx} className="flex items-start gap-3 p-3 bg-slate-50 rounded-lg border border-slate-200">
                    <span className="text-slate-800 font-bold shrink-0">{item.time || item.timestamp}</span>
                    <span className="text-slate-700 font-sans">{item.event}</span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Sidebar Telemetry Panels (Historical Incident Telemetry vs Current Live Data) */}
        <div className="space-y-6">
          {/* Section 1: Incident-Time / Historical Telemetry */}
          <div className="bg-white border border-amber-200 rounded-xl p-5 space-y-4 shadow-xs">
            <div className="border-b border-amber-100 pb-3">
              <h2 className="text-sm font-semibold text-slate-800 flex items-center gap-2">
                <History className="h-4 w-4 text-amber-600" />
                Telemetry at Incident Detection
              </h2>
              <span className="text-[11px] text-slate-500 mt-0.5 block">
                Captured when incident was detected:
              </span>
              <span className="text-[11px] font-mono text-slate-700 font-semibold">
                {incident.captured_at || incident.createdAt || incident.startTime || 'Not available'}
              </span>
            </div>

            <div className="space-y-3 text-xs font-mono">
              <div className="p-3 bg-red-50/70 rounded-lg border border-red-200">
                <div className="text-slate-600 mb-1 font-sans text-[11px] font-medium">P99 Latency at Detection</div>
                <div className="text-xl font-bold text-red-700">
                  {typeof detection.latencyMs === 'number'
                    ? `${Math.round(detection.latencyMs).toLocaleString()} ms`
                    : typeof incident.p99_latency_ms === 'number'
                    ? `${incident.p99_latency_ms.toLocaleString()} ms`
                    : 'Not available'}
                </div>
                <div className="text-[11px] text-slate-500 mt-1 font-sans">Baseline: &lt; 250ms</div>
              </div>

              <div className="p-3 bg-amber-50/70 rounded-lg border border-amber-200">
                <div className="text-slate-600 mb-1 font-sans text-[11px] font-medium">HTTP 5xx Error Rate at Detection</div>
                <div className="text-xl font-bold text-amber-700">
                  {typeof detection.errorRatePct === 'number'
                    ? `${detection.errorRatePct.toFixed(2)}%`
                    : typeof incident.error_rate === 'number'
                    ? `${incident.error_rate}%`
                    : 'Not available'}
                </div>
                <div className="text-[11px] text-slate-500 mt-1 font-sans">Baseline: &lt; 0.1%</div>
              </div>
            </div>
          </div>

          {/* Section 2: Current Live Service Status */}
          <div className="bg-white border border-emerald-200 rounded-xl p-5 space-y-4 shadow-xs">
            <div className="border-b border-emerald-100 pb-3 flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-slate-800 flex items-center gap-2">
                  <Activity className="h-4 w-4 text-emerald-600" />
                  Current Live Service Status
                </h2>
                <span className="text-[11px] text-slate-500 mt-0.5 block">
                  Live Prometheus telemetry
                </span>
              </div>
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-800 border border-emerald-300">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                LIVE
              </span>
            </div>

            <div className="space-y-3 text-xs font-mono">
              <div className="p-3 bg-emerald-50/60 rounded-lg border border-emerald-200 flex items-center justify-between">
                <span className="text-slate-600 font-sans font-medium">Current Status</span>
                <StatusBadge status={liveStatus} size="xs" />
              </div>

              <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
                <div className="text-slate-600 mb-1 font-sans text-[11px] font-medium">Current Latency</div>
                <div className="text-lg font-bold text-slate-800">
                  {typeof liveServiceObj?.average_latency_ms === 'number'
                    ? `${liveServiceObj.average_latency_ms} ms`
                    : 'Not available'}
                </div>
                <div className="text-[11px] text-slate-500 mt-0.5 font-sans">Real-time p95/avg measurement</div>
              </div>

              <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
                <div className="text-slate-600 mb-1 font-sans text-[11px] font-medium">Current Error Rate</div>
                <div className="text-lg font-bold text-slate-800">
                  {typeof liveServiceObj?.error_rate === 'number'
                    ? `${liveServiceObj.error_rate}%`
                    : 'Not available'}
                </div>
                <div className="text-[11px] text-slate-500 mt-0.5 font-sans">HTTP 5xx rate over last 5m</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default IncidentDetailsPage;
