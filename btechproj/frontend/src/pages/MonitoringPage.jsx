import React, { useState, useEffect, useCallback } from 'react';
import { Activity, RefreshCw, AlertCircle, Loader2, Inbox } from 'lucide-react';
import Sparkline from '../components/Sparkline';
import { getMonitoringData } from '../services/serviceService';

const MonitoringPage = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);

  const fetchMonitoring = useCallback(async (isManual = false) => {
    if (isManual) setRefreshing(true);
    setError(null);
    try {
      const res = await getMonitoringData();
      setData(res.data || null);
    } catch (err) {
      console.error('[MonitoringPage] Error fetching live telemetry:', err);
      setError('Prometheus server is unreachable or failed to fetch live observability metrics.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchMonitoring();
    const intervalId = setInterval(() => {
      fetchMonitoring();
    }, 15000);

    return () => clearInterval(intervalId);
  }, [fetchMonitoring]);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-200 pb-5">
          <div>
            <h1 className="text-2xl font-bold text-slate-800 tracking-tight flex items-center gap-2.5">
              <Activity className="h-6 w-6 text-[#384959]" />
              Infrastructure & Alert Monitoring
            </h1>
            <p className="text-sm text-slate-500 mt-1">
              Live Prometheus alert rule evaluation, cluster telemetry, and observability stream.
            </p>
          </div>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-12 flex flex-col items-center justify-center gap-3 text-slate-500 shadow-xs">
          <Loader2 className="h-8 w-8 text-[#384959] animate-spin" />
          <p className="text-xs font-medium">Fetching live Prometheus telemetry...</p>
        </div>
      </div>
    );
  }

  const cpu = data?.cpu_utilization;
  const memory = data?.memory_usage;
  const network = data?.network_throughput;
  const alertRules = data?.alert_rules || [];
  const isPrometheusUp = Boolean(data?.prometheus_up);

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 tracking-tight flex items-center gap-2.5">
            <Activity className="h-6 w-6 text-[#384959]" />
            Infrastructure & Alert Monitoring
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Live Prometheus alert rule evaluation, cluster telemetry, and observability stream.
          </p>
        </div>

        <button
          onClick={() => fetchMonitoring(true)}
          disabled={refreshing}
          className="flex items-center gap-2 text-xs font-medium text-slate-600 bg-white border border-slate-200 px-3 py-1.5 rounded-lg shadow-xs hover:bg-slate-50 transition-all disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 text-slate-500 ${refreshing ? 'animate-spin' : ''}`} />
          <span>Auto-refresh: 15s</span>
        </button>
      </div>

      {/* Error State Banner */}
      {(error || !isPrometheusUp) && (
        <div className="bg-red-50 border border-red-200 text-red-800 p-4 rounded-xl flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-red-600 shrink-0" />
            <span>{error || 'Prometheus server is unreachable. Observability metrics stream offline.'}</span>
          </div>
          <button
            onClick={() => fetchMonitoring(true)}
            className="px-3 py-1 bg-red-100 hover:bg-red-200 text-red-900 rounded font-semibold text-xs"
          >
            Retry
          </button>
        </div>
      )}

      {/* Cluster Resource Telemetry Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* CPU utilization card */}
        <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-3 shadow-xs">
          <div className="flex items-center justify-between text-xs text-slate-500 font-medium">
            <span>{cpu?.name || 'Cluster CPU Utilization'}</span>
            <span className={`font-bold font-mono ${cpu?.is_available ? 'text-slate-800' : 'text-slate-400'}`}>
              {cpu?.display_value || 'Not available'}
            </span>
          </div>
          <div className="h-20 bg-slate-50 rounded-lg p-3 border border-slate-200 flex items-center justify-between">
            <span className="text-xs text-slate-500 font-mono">Telemetry stream</span>
            {cpu?.sparkline && cpu.sparkline.length > 0 ? (
              <Sparkline data={cpu.sparkline} color="#6A89A7" width={140} height={32} />
            ) : (
              <span className="text-[11px] text-slate-400 italic">No history</span>
            )}
          </div>
        </div>

        {/* RAM usage card */}
        <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-3 shadow-xs">
          <div className="flex items-center justify-between text-xs text-slate-500 font-medium">
            <span>{memory?.name || 'Cluster RAM Usage'}</span>
            <span className={`font-bold font-mono ${memory?.is_available ? 'text-amber-700' : 'text-slate-400'}`}>
              {memory?.display_value || 'Not available'}
            </span>
          </div>
          <div className="h-20 bg-slate-50 rounded-lg p-3 border border-slate-200 flex items-center justify-between">
            <span className="text-xs text-slate-500 font-mono">Memory pressure</span>
            {memory?.sparkline && memory.sparkline.length > 0 ? (
              <Sparkline data={memory.sparkline} color="#D97706" width={140} height={32} />
            ) : (
              <span className="text-[11px] text-slate-400 italic">No history</span>
            )}
          </div>
        </div>

        {/* Network throughput card */}
        <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-3 shadow-xs">
          <div className="flex items-center justify-between text-xs text-slate-500 font-medium">
            <span>{network?.name || 'Ingress Network Throughput'}</span>
            <span className={`font-bold font-mono ${network?.is_available ? 'text-emerald-700' : 'text-slate-400'}`}>
              {network?.display_value || 'Not available'}
            </span>
          </div>
          <div className="h-20 bg-slate-50 rounded-lg p-3 border border-slate-200 flex items-center justify-between">
            <span className="text-xs text-slate-500 font-mono">Network I/O</span>
            {network?.sparkline && network.sparkline.length > 0 ? (
              <Sparkline data={network.sparkline} color="#166534" width={140} height={32} />
            ) : (
              <span className="text-[11px] text-slate-400 italic">No history</span>
            )}
          </div>
        </div>
      </div>

      {/* Alert Rules Evaluation Table */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4 shadow-xs">
        <h2 className="text-sm font-semibold text-slate-800 flex items-center gap-2">
          <AlertCircle className="h-4 w-4 text-[#384959]" />
          Prometheus Alert Rules Evaluation
        </h2>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-500 font-medium uppercase tracking-wider text-[11px] border-b border-slate-200">
              <tr>
                <th className="py-3 px-4">Rule Name</th>
                <th className="py-3 px-4">PromQL Expression</th>
                <th className="py-3 px-4">Severity</th>
                <th className="py-3 px-4">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-mono">
              {alertRules.length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-8 text-center text-slate-500 font-sans text-xs">
                    <div className="flex flex-col items-center gap-2">
                      <Inbox className="h-6 w-6 text-slate-400" />
                      <p>No alert rules are currently configured in Prometheus.</p>
                    </div>
                  </td>
                </tr>
              ) : (
                alertRules.map((rule, idx) => (
                  <tr key={idx} className="hover:bg-slate-50">
                    <td className="py-3 px-4 font-bold text-slate-800 font-sans">{rule.name}</td>
                    <td className="py-3 px-4 text-slate-500 text-[11px] truncate max-w-xs">{rule.query}</td>
                    <td className="py-3 px-4 font-sans">
                      <span className="px-2 py-0.5 rounded text-[11px] bg-slate-100 text-slate-700 border border-slate-200">
                        {rule.severity}
                      </span>
                    </td>
                    <td className="py-3 px-4 font-sans">
                      <span
                        className={`px-2 py-0.5 rounded text-[11px] font-semibold ${
                          rule.status === 'FIRING'
                            ? 'bg-red-50 text-red-700 border border-red-200'
                            : rule.status === 'PENDING'
                            ? 'bg-amber-50 text-amber-700 border border-amber-200'
                            : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                        }`}
                      >
                        {rule.status}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default MonitoringPage;
