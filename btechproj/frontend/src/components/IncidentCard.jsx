import React from 'react';
import { Link } from 'react-router-dom';
import { Clock, ArrowRight, Server } from 'lucide-react';
import SeverityBadge from './SeverityBadge';
import StatusBadge from './StatusBadge';

/**
 * IncidentCard component - Light-themed incident card
 */
const IncidentCard = ({
  id,
  affectedService,
  severity,
  status,
  startTime,
  description,
  className = '',
}) => {
  const isCritical = severity?.toLowerCase() === 'critical';

  return (
    <div
      className={`bg-white border ${
        isCritical ? 'border-red-200 bg-red-50/30' : 'border-slate-200'
      } rounded-xl p-4 sm:p-5 transition-all duration-200 shadow-xs flex flex-col md:flex-row md:items-center md:justify-between gap-4 ${className}`}
    >
      <div className="space-y-2 min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-xs font-bold text-slate-800 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
            {id}
          </span>
          <SeverityBadge severity={severity} size="xs" />
          <StatusBadge status={status} size="xs" />
        </div>

        <div>
          <div className="flex items-center gap-1.5 text-sm font-semibold text-slate-800">
            <Server className="h-3.5 w-3.5 text-slate-500 shrink-0" />
            <span>{affectedService}</span>
          </div>
          {description && (
            <p className="text-xs text-slate-600 mt-1 line-clamp-2 leading-relaxed">
              {description}
            </p>
          )}
        </div>

        <div className="flex items-center gap-1 text-[11px] text-slate-500 pt-0.5">
          <Clock className="h-3 w-3 text-slate-400" />
          <span>Started: {startTime}</span>
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0 border-t md:border-t-0 pt-3 md:pt-0 border-slate-100">
        <Link
          to={`/incidents/${id}`}
          className="px-3 py-1.5 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg border border-slate-200 transition-colors"
        >
          Details
        </Link>
        <Link
          to={`/incidents/${id}/investigate`}
          className="px-3 py-1.5 text-xs font-semibold text-white bg-[#384959] hover:bg-[#2b3844] rounded-lg border border-[#384959] transition-colors flex items-center gap-1 shadow-xs"
        >
          <span>Investigate</span>
          <ArrowRight className="h-3 w-3" />
        </Link>
      </div>
    </div>
  );
};

export default IncidentCard;
