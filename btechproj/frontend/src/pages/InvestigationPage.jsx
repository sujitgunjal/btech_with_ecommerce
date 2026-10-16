import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  Terminal,
  Play,
  CheckCircle2,
  Loader2,
  Clock,
  Server,
  AlertCircle,
} from 'lucide-react';
import InvestigationResult from '../components/InvestigationResult';
import SeverityBadge from '../components/SeverityBadge';
import DemoDataBadge from '../components/DemoDataBadge';
import {
  getIncidentById,
  getIncidentEvidence,
  investigateIncident,
} from '../services/incidentService';

function requestErrorMessage(err, fallback) {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string' && detail) return detail;
  if (err?.message) return err.message;
  return fallback;
}

function statusPresentation(status, isInvestigating) {
  if (isInvestigating) {
    return {
      className: 'text-amber-700',
      icon: <Loader2 className="h-4 w-4 text-amber-600 animate-spin" />,
      label: 'In Progress',
    };
  }
  if (status === 'completed') {
    return {
      className: 'text-emerald-700',
      icon: <CheckCircle2 className="h-4 w-4 text-emerald-600" />,
      label: 'Investigation Completed',
    };
  }
  if (status === 'completed_partial') {
    return {
      className: 'text-amber-700',
      icon: <AlertCircle className="h-4 w-4 text-amber-600" />,
      label: 'Completed (partial)',
    };
  }
  if (status === 'failed') {
    return {
      className: 'text-red-700',
      icon: <AlertCircle className="h-4 w-4 text-red-600" />,
      label: 'Investigation Failed',
    };
  }
  return {
    className: 'text-slate-600',
    icon: <Clock className="h-4 w-4 text-slate-400" />,
    label: 'Investigation Pending',
  };
}

const InvestigationPage = () => {
  const { id } = useParams();
  const incidentId = id || 'INC-001';

  const [incident, setIncident] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isMock, setIsMock] = useState(false);

  const [isInvestigating, setIsInvestigating] = useState(false);
  const [investigation, setInvestigation] = useState(null);
  const [investigationError, setInvestigationError] = useState(null);
  const [telemetry, setTelemetry] = useState(null);
  const [telemetryLoading, setTelemetryLoading] = useState(false);
  const [telemetryError, setTelemetryError] = useState(null);
  const [hasStarted, setHasStarted] = useState(false);

  const fetchIncidentDetails = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getIncidentById(incidentId);
      setIncident(res.data || null);
      setIsMock(Boolean(res.isMock));
    } catch (err) {
      console.error('[InvestigationPage] Error loading incident details:', err);
      setIncident(null);
      setError(requestErrorMessage(err, 'Failed to fetch target incident for investigation.'));
    } finally {
      setLoading(false);
    }
  }, [incidentId]);

  useEffect(() => {
    fetchIncidentDetails();
  }, [fetchIncidentDetails]);

  const startInvestigation = async () => {
    if (!incident || isInvestigating) return;
    const targetId = incident.db_id ?? incidentId;

    setHasStarted(true);
    setIsInvestigating(true);
    setInvestigation(null);
    setInvestigationError(null);
    setTelemetry(null);
    setTelemetryError(null);
    setTelemetryLoading(true);

    const evidencePromise = getIncidentEvidence(targetId)
      .then((res) => setTelemetry(res.data))
      .catch((err) => {
        console.error('[InvestigationPage] Error loading evidence:', err);
        setTelemetry(null);
        setTelemetryError(requestErrorMessage(err, 'Failed to load incident evidence.'));
      })
      .finally(() => setTelemetryLoading(false));

    try {
      const res = await investigateIncident(targetId);
      setInvestigation(res.data || null);
      if (!res.data) {
        setInvestigationError('The backend returned an empty investigation response.');
      } else if (res.data.status === 'failed') {
        setInvestigationError('The backend marked this investigation as failed.');
      }
    } catch (err) {
      console.error('[InvestigationPage] Error calling investigateIncident service:', err);
      setInvestigation(null);
      setInvestigationError(requestErrorMessage(err, 'Investigation request failed.'));
    } finally {
      setIsInvestigating(false);
    }

    await evidencePromise;
  };

  const affectedService = incident?.affectedService || incident?.service || 'Unknown';
  const severity = incident?.severity || 'Unknown';
  const statusView = statusPresentation(investigation?.status, isInvestigating);
  const showResult = hasStarted && !isInvestigating;

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-2 text-xs text-slate-500 font-sans">
          <Link to="/incidents" className="hover:text-slate-800 font-medium">
            Incidents
          </Link>
          <span>/</span>
          <span className="text-slate-800 font-bold font-mono">{incidentId}</span>
          <span>/</span>
          <span className="text-[#384959] font-medium">investigate</span>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-12 flex flex-col items-center justify-center gap-3 text-slate-500 shadow-xs">
          <Loader2 className="h-8 w-8 text-[#384959] animate-spin" />
          <p className="text-xs font-medium">Preparing investigation workbench...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-2 text-xs text-slate-500 font-sans mb-2">
            <Link to="/incidents" className="hover:text-slate-800 font-medium">
              Incidents
            </Link>
            <span>/</span>
            <span className="text-slate-800 font-bold font-mono">{incidentId}</span>
            <span>/</span>
            <span className="text-[#384959] font-medium">investigate</span>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-2xl font-bold text-slate-800 tracking-tight flex items-center gap-2.5">
              <Terminal className="h-6 w-6 text-[#384959]" />
              Incident Investigation
            </h1>
            {isMock && <DemoDataBadge />}
          </div>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-800 p-4 rounded-xl flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-red-600" />
            <span>{error}</span>
          </div>
          <button
            onClick={fetchIncidentDetails}
            className="px-3 py-1 bg-red-100 hover:bg-red-200 text-red-900 rounded font-semibold text-xs"
          >
            Retry
          </button>
        </div>
      )}

      {investigationError && (
        <div className="bg-red-50 border border-red-200 text-red-800 p-4 rounded-xl flex items-center gap-2 text-xs">
          <AlertCircle className="h-4 w-4 text-red-600 shrink-0" />
          <span>{investigationError}</span>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-1 shadow-xs">
          <span className="text-xs font-medium text-slate-500 block">Incident</span>
          <div className="text-xl font-bold font-mono text-slate-800 flex items-center gap-2">
            <span>{incident?.id || incidentId}</span>
            <SeverityBadge severity={severity} size="xs" />
          </div>
        </div>

        <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-1 shadow-xs">
          <span className="text-xs font-medium text-slate-500 block">Affected Service</span>
          <div className="text-xl font-bold text-slate-800 font-sans flex items-center gap-2">
            <Server className="h-5 w-5 text-[#6A89A7]" />
            <span>{affectedService}</span>
          </div>
        </div>

        <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-1 shadow-xs">
          <span className="text-xs font-medium text-slate-500 block">Investigation Status</span>
          <div className={`text-sm font-bold font-sans flex items-center gap-2 ${statusView.className}`}>
            {statusView.icon}
            <span>{statusView.label}</span>
          </div>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-4 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-slate-800">Operational Data Pipeline</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Run root cause analysis and load logs, metrics, and traces from the backend.
            </p>
          </div>

          <button
            onClick={startInvestigation}
            disabled={isInvestigating || !incident}
            className={`px-5 py-2.5 rounded-xl text-xs font-semibold transition-all flex items-center gap-2 shadow-xs ${
              isInvestigating || !incident
                ? 'bg-slate-100 text-slate-400 cursor-not-allowed border border-slate-200'
                : 'bg-[#384959] text-white hover:bg-[#2b3844] border border-[#384959]'
            }`}
          >
            {isInvestigating ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Running investigation...</span>
              </>
            ) : (
              <>
                <Play className="h-4 w-4 fill-white" />
                <span>{investigation ? 'Re-run Investigation' : 'Start Investigation'}</span>
              </>
            )}
          </button>
        </div>

        {isInvestigating && (
          <div className="flex items-center gap-2 text-xs text-slate-600 bg-slate-50 border border-slate-200 rounded-xl p-3">
            <Loader2 className="h-4 w-4 animate-spin text-[#384959]" />
            <span>Waiting for the backend investigation to finish. This stays here until the request returns.</span>
          </div>
        )}
      </div>

      {showResult && (
        <InvestigationResult
          investigation={investigation}
          telemetry={telemetry}
          telemetryLoading={telemetryLoading}
          telemetryError={telemetryError}
        />
      )}
    </div>
  );
};

export default InvestigationPage;
