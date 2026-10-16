import React from 'react';
import { Server, CheckCircle2, AlertTriangle, AlertOctagon, Zap, Clock } from 'lucide-react';
import StatusBadge from './StatusBadge';

/**
 * ServiceStatus component - Render individual microservice health card
 */
const ServiceStatus = ({
  name,
  status,
  requestCount,
  avgLatency,
  uptime,
  className = '',
}) => {
  return (
    <div
      className={`bg-white border border-slate-200 rounded-xl p-4 transition-all duration-200 shadow-xs flex flex-col justify-between ${className}`}
    >
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <Server className="h-4 w-4 text-[#6A89A7] shrink-0" />
          <h3 className="text-sm font-semibold text-slate-800 truncate font-sans">{name}</h3>
        </div>
        <StatusBadge status={status} size="xs" />
      </div>

      <div className="grid grid-cols-2 gap-3 pt-3 border-t border-slate-100 text-xs">
        <div className="bg-slate-50 p-2.5 rounded-lg border border-slate-200/80">
          <div className="flex items-center gap-1 text-[11px] text-slate-500 mb-0.5">
            <Zap className="h-3 w-3 text-slate-400" />
            <span>Requests</span>
          </div>
          <div className="font-mono font-bold text-slate-800 text-xs">{requestCount}</div>
        </div>

        <div className="bg-slate-50 p-2.5 rounded-lg border border-slate-200/80">
          <div className="flex items-center gap-1 text-[11px] text-slate-500 mb-0.5">
            <Clock className="h-3 w-3 text-slate-400" />
            <span>Avg Latency</span>
          </div>
          <div className="font-mono font-bold text-xs text-slate-800">{avgLatency}</div>
        </div>
      </div>
    </div>
  );
};

export default ServiceStatus;
