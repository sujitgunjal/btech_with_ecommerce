import React, { useState, useEffect, useCallback } from 'react';
import { Server, ArrowUpRight, Loader2, AlertCircle, Inbox, RefreshCw } from 'lucide-react';
import StatusBadge from '../components/StatusBadge';
import DemoDataBadge from '../components/DemoDataBadge';
import { getServices } from '../services/serviceService';

const ServicesPage = () => {
  const [services, setServices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isMock, setIsMock] = useState(false);

  const fetchServicesData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getServices();
      setServices(res.data || []);
      setIsMock(Boolean(res.isMock));
    } catch (err) {
      console.error('[ServicesPage] Error loading services telemetry:', err);
      setError('Failed to load microservice catalog telemetry.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchServicesData();
  }, [fetchServicesData]);

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-2xl font-bold text-slate-800 tracking-tight flex items-center gap-2.5">
              <Server className="h-6 w-6 text-[#384959]" />
              Microservices Catalog
            </h1>
            {isMock && <DemoDataBadge />}
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Real-time health status, versioning, and latency benchmarks for registered system services.
          </p>
        </div>

        <button
          onClick={fetchServicesData}
          disabled={loading}
          className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 transition-all shadow-xs flex items-center gap-1.5 self-start sm:self-auto disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 text-slate-500 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-800 p-4 rounded-xl flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-red-600" />
            <span>{error}</span>
          </div>
          <button
            onClick={fetchServicesData}
            className="px-3 py-1 bg-red-100 hover:bg-red-200 text-red-900 rounded font-semibold text-xs"
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading State */}
      {loading ? (
        <div className="bg-white border border-slate-200 rounded-xl p-12 flex flex-col items-center justify-center gap-3 text-slate-500 shadow-xs">
          <Loader2 className="h-8 w-8 text-[#384959] animate-spin" />
          <p className="text-xs font-medium">Fetching microservices status catalog...</p>
        </div>
      ) : services.length === 0 ? (
        /* Empty State */
        <div className="bg-white border border-slate-200 rounded-xl p-12 text-center text-slate-500 shadow-xs space-y-2">
          <Inbox className="h-10 w-10 text-slate-400 mx-auto" />
          <p className="text-xs font-medium">No registered microservices found.</p>
        </div>
      ) : (
        /* Services Grid */
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {services.map((srv, idx) => (
            <div key={srv.id || idx} className="bg-white border border-slate-200 rounded-xl p-5 hover:border-slate-300 transition-all shadow-xs space-y-4">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-bold text-slate-800 font-mono text-sm">{srv.name}</h3>
                  <p className="text-[11px] text-slate-500 mt-0.5">{srv.type || 'Microservice'} • {srv.version || 'v1.0.0'}</p>
                </div>
                <StatusBadge status={srv.status} size="xs" />
              </div>

              <div className="grid grid-cols-3 gap-2 py-3 border-y border-slate-100 font-mono text-xs text-center">
                <div>
                  <span className="text-[10px] text-slate-500 block font-sans">Avg Latency</span>
                  <span className={`font-semibold ${srv.status?.toUpperCase() === 'DEGRADED' || srv.status?.toUpperCase() === 'CRITICAL' ? 'text-red-700' : 'text-slate-800'}`}>
                    {srv.average_latency_ms == null || srv.average_latency_ms === undefined
                      ? 'N/A'
                      : `${srv.average_latency_ms} ms`}
                  </span>
                </div>
                <div>
                  <span className="text-[10px] text-slate-500 block font-sans">Error Rate</span>
                  <span className={`font-semibold ${srv.status?.toUpperCase() === 'DEGRADED' || srv.status?.toUpperCase() === 'CRITICAL' ? 'text-red-700' : 'text-slate-800'}`}>
                    {srv.error_rate == null || srv.error_rate === undefined
                      ? 'N/A'
                      : `${srv.error_rate}%`}
                  </span>
                </div>
                <div>
                  <span className="text-[10px] text-slate-500 block font-sans">30d Uptime</span>
                  <span className="font-semibold text-slate-700">{srv.uptime || '—'}</span>
                </div>
              </div>

              <div className="flex items-center justify-between text-xs pt-1">
                <span className="text-slate-500 font-mono">Tag: {srv.version || 'v1.0.0'}</span>
                <span className="text-[#6A89A7] hover:text-[#384959] font-medium flex items-center gap-1 cursor-pointer">
                  Telemetry <ArrowUpRight className="h-3 w-3" />
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default ServicesPage;
