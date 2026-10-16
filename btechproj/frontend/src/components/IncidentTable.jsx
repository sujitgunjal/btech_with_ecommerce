import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Eye, ArrowRight, Server, AlertCircle } from 'lucide-react';
import SeverityBadge from './SeverityBadge';
import StatusBadge from './StatusBadge';

/**
 * IncidentTable component - Clean, professional light SaaS table for system incidents
 */
const IncidentTable = ({ incidents = [] }) => {
  const navigate = useNavigate();

  if (!incidents || incidents.length === 0) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-12 text-center space-y-3 shadow-xs">
        <AlertCircle className="h-10 w-10 text-slate-400 mx-auto" />
        <h3 className="text-base font-semibold text-slate-800">No Incidents Found</h3>
        <p className="text-xs text-slate-500 max-w-sm mx-auto">
          No incident records matched your search query or filter criteria. Try clearing filters or altering your search text.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-xs">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          {/* Table Header */}
          <thead className="bg-slate-50 text-slate-500 uppercase tracking-wider text-[11px] font-medium border-b border-slate-200">
            <tr>
              <th className="py-3 px-4">Incident ID</th>
              <th className="py-3 px-4">Affected Service</th>
              <th className="py-3 px-4">Severity</th>
              <th className="py-3 px-4">Status</th>
              <th className="py-3 px-4">Start Time</th>
              <th className="py-3 px-4 text-right">Action</th>
            </tr>
          </thead>

          {/* Table Body */}
          <tbody className="divide-y divide-slate-100">
            {incidents.map((incident) => {
              const isCritical = incident.severity?.toLowerCase() === 'critical';
              return (
                <tr
                  key={incident.id}
                  className={`transition-colors cursor-pointer ${
                    isCritical ? 'bg-red-50/30 hover:bg-red-50/60' : 'hover:bg-slate-50'
                  }`}
                  onClick={() => navigate(`/incidents/${incident.id}`)}
                >
                  {/* Incident ID */}
                  <td className="py-3.5 px-4 font-mono font-bold text-slate-800 whitespace-nowrap">
                    <span className="bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                      {incident.id}
                    </span>
                  </td>

                  {/* Affected Service */}
                  <td className="py-3.5 px-4 font-semibold text-slate-800 whitespace-nowrap">
                    <div className="flex items-center gap-2">
                      <Server className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                      <span>{incident.affectedService}</span>
                    </div>
                  </td>

                  {/* Severity */}
                  <td className="py-3.5 px-4 whitespace-nowrap">
                    <SeverityBadge severity={incident.severity} size="xs" />
                  </td>

                  {/* Status */}
                  <td className="py-3.5 px-4 whitespace-nowrap">
                    <StatusBadge status={incident.status} size="xs" />
                  </td>

                  {/* Start Time */}
                  <td className="py-3.5 px-4 text-slate-500 font-mono whitespace-nowrap">
                    {incident.startTime}
                  </td>

                  {/* Action */}
                  <td
                    className="py-3.5 px-4 text-right whitespace-nowrap"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => navigate(`/incidents/${incident.id}`)}
                        className="px-3 py-1.5 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-md border border-slate-200 transition-colors inline-flex items-center gap-1"
                      >
                        <Eye className="h-3.5 w-3.5 text-slate-500" />
                        <span>View</span>
                      </button>
                      <button
                        onClick={() => navigate(`/incidents/${incident.id}/investigate`)}
                        className="px-2 py-1.5 text-xs font-semibold text-white bg-[#384959] hover:bg-[#2b3844] rounded-md border border-[#384959] transition-colors inline-flex items-center gap-1 shadow-xs"
                        title="Investigate"
                      >
                        <ArrowRight className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default IncidentTable;
