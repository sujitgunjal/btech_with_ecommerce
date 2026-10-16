import React, { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  RefreshCw,
  ArrowRight,
  ArrowUpRight,
  Loader2,
  AlertCircle,
  Inbox,
  CheckCircle2,
  Info,
} from 'lucide-react';
import Sparkline from '../components/Sparkline';
import SeverityBadge from '../components/SeverityBadge';
import StatusBadge from '../components/StatusBadge';
import DemoDataBadge from '../components/DemoDataBadge';
import { getIncidents } from '../services/incidentService';
import { getServices, getDashboardOverview } from '../services/serviceService';

const DashboardPage = () => {
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isMock, setIsMock] = useState(false);
  const [services, setServices] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [overview, setOverview] = useState({
    system_health: 92,
    active_incidents: 2,
    error_rate: 7.2,
    average_latency_ms: 284,
    healthy_services: 3,
    total_services: 4,
    requests_per_minute: 102400,
  });

  const loadDashboardData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [servicesRes, incidentsRes, overviewRes] = await Promise.all([
        getServices(),
        getIncidents(),
        getDashboardOverview(),
      ]);

      setServices(servicesRes.data || []);
      setIncidents(incidentsRes.data || []);
      if (overviewRes.data) {
        setOverview(overviewRes.data);
      }
      setIsMock(Boolean(servicesRes.isMock || incidentsRes.isMock || overviewRes.isMock));
    } catch (err) {
      console.error('[DashboardPage] Failed to load dashboard data:', err);
      setError('Failed to fetch infrastructure telemetry data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDashboardData();
  }, [loadDashboardData]);

  // Dynamic calculation safeguards: ensure Healthy Services summary metric matches the services array 100%
  const healthyServicesCount = services.length > 0
    ? services.filter((s) => s.status?.toLowerCase() === 'healthy').length
    : overview.healthy_services;
  const totalServicesCount = services.length > 0
    ? services.length
    : overview.total_services;
  const unhealthyServicesCount = Math.max(0, totalServicesCount - healthyServicesCount);

  // Metrics strip data derived from dynamic overview API state
  const metrics = [
    {
      title: 'Error Rate',
      value: `${overview.error_rate}%`,
      trend: overview.error_rate > 1.0 ? '+2.1%' : '0.0%',
      isBad: overview.error_rate > 1.0,
      sub: 'Threshold < 1.0%',
    },
    {
      title: 'Average Latency',
      value: `${Math.round(overview.average_latency_ms)} ms`,
      trend: '-12 ms',
      isBad: overview.average_latency_ms > 300,
      sub: 'p95: 540 ms',
    },
    {
      title: 'Healthy Services',
      value: `${healthyServicesCount} / ${totalServicesCount}`,
      trend: `${Math.round((healthyServicesCount / (totalServicesCount || 1)) * 100)}%`,
      isBad: healthyServicesCount < totalServicesCount,
      sub: `${unhealthyServicesCount} Degraded/Critical`,
    },
    {
      title: 'Requests',
      value: overview.requests_per_minute >= 1000
        ? `${(overview.requests_per_minute / 1000).toFixed(1)}k`
        : `${Math.round(overview.requests_per_minute)}`,
      trend: '+14%',
      isBad: false,
      sub: 'per minute',
    },
  ];

  const criticalIncident = incidents.find(
    (inc) => inc.severity?.toLowerCase() === 'critical' && inc.status?.toLowerCase() !== 'resolved'
  ) || incidents[0];

  return (
    <div className="space-y-8">
      {/* 1. Header Greeting */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-2xl font-bold text-slate-800 tracking-tight">
              Good morning, DevOps team
            </h1>
            {isMock && <DemoDataBadge />}
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Here is the current state of your production environment.
          </p>
        </div>
        <div className="flex items-center gap-3 self-start sm:self-auto">
          <span className="text-xs text-slate-500 font-medium">Last updated: Just now</span>
          <button
            onClick={loadDashboardData}
            disabled={loading}
            className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 transition-all shadow-xs flex items-center gap-1.5 disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 text-slate-500 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Global Error Banner */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-800 p-4 rounded-xl flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-red-600" />
            <span>{error}</span>
          </div>
          <button
            onClick={loadDashboardData}
            className="px-3 py-1 bg-red-100 hover:bg-red-200 text-red-900 rounded font-semibold text-xs"
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading Overlay State */}
      {loading ? (
        <div className="bg-white border border-slate-200 rounded-xl p-12 flex flex-col items-center justify-center gap-3 text-slate-500 shadow-xs">
          <Loader2 className="h-8 w-8 text-[#384959] animate-spin" />
          <p className="text-xs font-medium">Fetching environment status telemetry...</p>
        </div>
      ) : (
        <>
          {/* 2. Primary Overview Section (Asymmetric Editorial Layout) */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Left Side: Large System Health Panel */}
            <div className="lg:col-span-7 bg-white border border-slate-200 rounded-xl p-6 shadow-xs flex flex-col space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-base font-semibold text-slate-800">System Health</h2>
                  <p className="text-xs text-slate-500 mt-0.5">Overall infrastructure stability index</p>
                </div>
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-50 text-emerald-700 text-xs font-medium border border-emerald-200">
                  <span className="h-2 w-2 rounded-full bg-emerald-500" />
                  Operational
                </span>
              </div>

              <div className="flex flex-col sm:flex-row items-center gap-8 pt-1">
                {/* Semi-circular / Donut Gauge */}
                <div className="relative flex items-center justify-center shrink-0">
                  <svg className="w-36 h-36 transform -rotate-90">
                    <circle
                      cx="72"
                      cy="72"
                      r="60"
                      stroke="#E2E8F0"
                      strokeWidth="10"
                      fill="transparent"
                    />
                    <circle
                      cx="72"
                      cy="72"
                      r="60"
                      stroke="#6A89A7"
                      strokeWidth="10"
                      strokeDasharray={376.8}
                      strokeDashoffset={376.8 * (1 - (overview.system_health / 100))}
                      strokeLinecap="round"
                      fill="transparent"
                      className="transition-all duration-1000"
                    />
                  </svg>
                  <div className="absolute text-center">
                    <span className="text-3xl font-bold text-slate-800 block leading-none font-mono">
                      {overview.system_health}
                    </span>
                    <span className="text-[11px] font-medium text-slate-500 block mt-1">/ 100</span>
                  </div>
                </div>

                <div className="space-y-3 flex-1 text-center sm:text-left">
                  <div>
                    <h3 className="text-sm font-semibold text-slate-800">
                      All systems are operating with {overview.total_services - overview.healthy_services} degraded/critical service(s).
                    </h3>
                    <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                      {overview.total_services - overview.healthy_services === 0
                        ? 'All registered microservices are operating optimally within healthy latency and error rate bounds.'
                        : `${services.filter(s => s.status?.toLowerCase() === 'healthy').map(s => s.name).join(', ')} functioning within latency bounds. ${services.filter(s => s.status?.toLowerCase() !== 'healthy').map(s => s.name).join(', ')} require(s) attention.`}
                    </p>

                  </div>

                  {/* Subtle trend chart preview */}
                  <div className="pt-2 border-t border-slate-100 flex items-center justify-between gap-4">
                    <span className="text-xs text-slate-500">24-hour health score stability:</span>
                    <Sparkline data={[85, 88, 94, 95, 90, 89, overview.system_health]} color="#6A89A7" width={110} height={24} />
                  </div>
                </div>
              </div>
            </div>

            {/* Right Side: Active Incidents Overview */}
            <div className="lg:col-span-5 bg-white border border-slate-200 rounded-xl p-6 shadow-xs flex flex-col justify-between space-y-4">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                <div>
                  <h2 className="text-base font-semibold text-slate-800">Active Incidents</h2>
                  <p className="text-xs text-slate-500 mt-0.5">High priority system alerts</p>
                </div>
                <div className="text-right">
                  <span className="text-2xl font-bold text-red-600 font-mono">{overview.active_incidents}</span>
                  <span className="text-xs text-slate-500 block font-medium">Active incidents</span>
                </div>
              </div>

              {/* Critical Highlight Box */}
              {criticalIncident ? (
                (() => {
                  const activeIncidentService = criticalIncident?.affectedService || criticalIncident?.service;
                  const liveServiceObj = services.find(
                    (s) => s.name?.toLowerCase() === activeIncidentService?.toLowerCase()
                  );
                  const liveServiceStatus = liveServiceObj?.status
                    ? liveServiceObj.status.charAt(0).toUpperCase() + liveServiceObj.status.slice(1)
                    : 'Healthy';
                  const isServiceRecovered =
                    liveServiceStatus.toLowerCase() === 'healthy' &&
                    criticalIncident?.status?.toLowerCase() !== 'resolved';

                  return (
                    <div className="bg-red-50/70 border border-red-200 rounded-lg p-4 space-y-3">
                      <div className="flex items-center justify-between flex-wrap gap-2">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-red-100 text-red-800 border border-red-200">
                            {criticalIncident.severity?.toUpperCase() || 'CRITICAL'}
                          </span>
                          <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-amber-100 text-amber-800 border border-amber-200">
                            {criticalIncident.status?.toUpperCase() || 'INVESTIGATING'}
                          </span>
                          {isServiceRecovered && (
                            <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-100 text-emerald-800 border border-emerald-300 flex items-center gap-1">
                              <CheckCircle2 className="h-3 w-3 text-emerald-600" />
                              RECOVERED
                            </span>
                          )}
                        </div>
                        <span className="text-xs text-slate-500 font-mono font-bold">{criticalIncident.id}</span>
                      </div>

                      <div>
                        <div className="flex items-center justify-between text-xs mb-1">
                          <h4 className="text-sm font-semibold text-slate-800">
                            Affected Service: <span className="font-mono">{activeIncidentService}</span>
                          </h4>
                          <span className="text-[11px] text-slate-500 font-medium">
                            Current Service Status:{' '}
                            <span className="text-emerald-700 font-bold">{liveServiceStatus}</span>
                          </span>
                        </div>
                        <p className="text-xs text-slate-600 mt-1">{criticalIncident.description}</p>
                      </div>

                      {isServiceRecovered && (
                        <div className="p-2.5 bg-emerald-50/90 border border-emerald-200 rounded text-[11px] text-emerald-900 flex items-start gap-2">
                          <Info className="h-3.5 w-3.5 text-emerald-600 shrink-0 mt-0.5" />
                          <span>The affected service has recovered, but the incident remains under investigation.</span>
                        </div>
                      )}

                      <div className="pt-2 flex justify-end">
                        <Link
                          to={`/incidents/${criticalIncident.id}/investigate`}
                          className="px-3 py-1.5 text-xs font-semibold text-white bg-[#384959] hover:bg-[#2b3844] rounded-md transition-colors inline-flex items-center gap-1.5 shadow-xs"
                        >
                          <span>Investigate</span>
                          <ArrowRight className="h-3.5 w-3.5" />
                        </Link>
                      </div>
                    </div>
                  );
                })()
              ) : (
                <div className="p-4 bg-slate-50 rounded-lg text-xs text-slate-500 text-center">
                  No active critical incidents.
                </div>
              )}
            </div>
          </div>

          {/* 3. Compact Metrics Strip */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {metrics.map((m, idx) => (
              <div key={idx} className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs space-y-2">
                <div className="flex items-center justify-between text-xs text-slate-500">
                  <span className="font-medium">{m.title}</span>
                  <span
                    className={`text-[11px] font-medium px-1.5 py-0.5 rounded ${
                      m.isBad ? 'bg-red-50 text-red-700' : 'bg-emerald-50 text-emerald-700'
                    }`}
                  >
                    {m.trend}
                  </span>
                </div>
                <div className="text-2xl font-bold text-slate-800 font-mono tracking-tight">{m.value}</div>
                <div className="text-[11px] text-slate-500">{m.sub}</div>
              </div>
            ))}
          </div>

          {/* 4. Service Health List / Table */}
          <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-xs space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div>
                <h2 className="text-base font-semibold text-slate-800">Service Health</h2>
                <p className="text-xs text-slate-500 mt-0.5">Monitored environment microservices telemetry</p>
              </div>
              <Link to="/services" className="text-xs font-semibold text-[#6A89A7] hover:text-[#384959] flex items-center gap-1">
                <span>View Catalog</span>
                <ArrowUpRight className="h-3.5 w-3.5" />
              </Link>
            </div>

            {services.length === 0 ? (
              <div className="py-8 text-center text-slate-500 text-xs flex flex-col items-center gap-2">
                <Inbox className="h-8 w-8 text-slate-400" />
                <p>No services registered in environment telemetry.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-500 font-medium text-[11px] uppercase tracking-wider">
                      <th className="py-3 px-4">Service</th>
                      <th className="py-3 px-4">Status</th>
                      <th className="py-3 px-4">Requests</th>
                      <th className="py-3 px-4">Latency</th>
                      <th className="py-3 px-4 text-right">Trend</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {services.map((srv) => (
                      <tr
                        key={srv.id || srv.name}
                        onClick={() => navigate('/services')}
                        className="hover:bg-slate-50 transition-colors cursor-pointer"
                      >
                        <td className="py-3.5 px-4 font-semibold text-slate-800 hover:text-[#6A89A7]">
                          {srv.name}
                        </td>
                        <td className="py-3.5 px-4">
                          <StatusBadge status={srv.status} size="xs" />
                        </td>
                        <td className="py-3.5 px-4 text-slate-600 font-mono">
                          {typeof srv.requests_per_minute === 'number'
                            ? `${srv.requests_per_minute.toLocaleString()} req/min`
                            : srv.requestCount}
                        </td>
                        <td className="py-3.5 px-4 text-slate-600 font-mono">
                          {typeof srv.average_latency_ms === 'number'
                            ? `${srv.average_latency_ms} ms`
                            : srv.avgLatency}
                        </td>
                        <td className="py-3.5 px-4 text-right">
                          <Sparkline
                            data={
                              srv.status?.toUpperCase() === 'CRITICAL'
                                ? [40, 80, 150, 320, 840]
                                : srv.status?.toUpperCase() === 'DEGRADED'
                                ? [30, 45, 90, 210, 310]
                                : [40, 42, 45, 41, 42]
                            }
                            color={
                              srv.status?.toUpperCase() === 'CRITICAL'
                                ? '#DC2626'
                                : srv.status?.toUpperCase() === 'DEGRADED'
                                ? '#D97706'
                                : '#166534'
                            }
                            width={80}
                            height={20}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* 5. Incident Activity List */}
          <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-xs space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div>
                <h2 className="text-base font-semibold text-slate-800">Incident Activity</h2>
                <p className="text-xs text-slate-500 mt-0.5">Recent system triage feed</p>
              </div>
              <Link to="/incidents" className="text-[#6A89A7] text-xs font-semibold hover:text-[#384959] flex items-center gap-1">
                <span>All Incidents</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </div>

            {incidents.length === 0 ? (
              <div className="py-8 text-center text-slate-500 text-xs flex flex-col items-center gap-2">
                <Inbox className="h-8 w-8 text-slate-400" />
                <p>No recent incidents recorded.</p>
              </div>
            ) : (
              <div className="space-y-2">
                {incidents.slice(0, 3).map((inc) => {
                  const isCritical = inc.severity?.toLowerCase() === 'critical';
                  return (
                    <div
                      key={inc.id}
                      className={`p-4 rounded-lg border transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                        isCritical
                          ? 'bg-red-50/40 border-red-100 hover:bg-red-50/70'
                          : 'bg-slate-50/60 border-slate-200/80 hover:bg-slate-100/60'
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <span
                          className={`h-2.5 w-2.5 rounded-full mt-1.5 shrink-0 ${
                            isCritical ? 'bg-red-500' : inc.severity === 'High' ? 'bg-amber-500' : 'bg-yellow-500'
                          }`}
                        />
                        <div>
                          <div className="flex items-center gap-2 text-xs">
                            <span className="font-mono font-semibold text-slate-800">{inc.id}</span>
                            <span className="text-slate-400">•</span>
                            <span className="font-semibold text-slate-800">{inc.affectedService}</span>
                            <SeverityBadge severity={inc.severity} size="xs" />
                          </div>
                          <p className="text-xs text-slate-600 mt-1 leading-relaxed">{inc.description}</p>
                          <span className="text-[11px] text-slate-400 font-medium block mt-1">{inc.startTime}</span>
                        </div>
                      </div>

                      <div className="self-end sm:self-center shrink-0">
                        <Link
                          to={`/incidents/${inc.id}`}
                          className="text-xs font-semibold text-[#6A89A7] hover:text-[#384959] inline-flex items-center gap-1"
                        >
                          <span>View details</span>
                          <ArrowRight className="h-3 w-3" />
                        </Link>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
};

export default DashboardPage;
