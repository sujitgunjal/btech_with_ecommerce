import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { AlertTriangle, Loader2, AlertCircle, RefreshCw, Inbox, Trash2 } from 'lucide-react';
import IncidentFilters from '../components/IncidentFilters';
import IncidentTable from '../components/IncidentTable';
import DemoDataBadge from '../components/DemoDataBadge';
import { deleteAllIncidents, getIncidents } from '../services/incidentService';

/**
 * IncidentsPage Component - Searchable and filterable table of system incidents
 */
const IncidentsPage = () => {
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isMock, setIsMock] = useState(false);

  const [deleting, setDeleting] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedSeverity, setSelectedSeverity] = useState('ALL');
  const [selectedStatus, setSelectedStatus] = useState('ALL');

  const fetchIncidentsData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getIncidents();
      setIncidents(res.data || []);
      setIsMock(Boolean(res.isMock));
    } catch (err) {
      console.error('[IncidentsPage] Error loading incidents:', err);
      setError('Failed to load incident records from service layer.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchIncidentsData();
  }, [fetchIncidentsData]);

  // Filter incidents based on search text, severity, and status
  const filteredIncidents = useMemo(() => {
    return incidents.filter((incident) => {
      // 1. Search Query Filter (ID or Affected Service)
      const query = searchQuery.trim().toLowerCase();
      const matchesQuery =
        !query ||
        incident.id?.toLowerCase().includes(query) ||
        incident.affectedService?.toLowerCase().includes(query) ||
        (incident.description && incident.description.toLowerCase().includes(query));

      // 2. Severity Filter
      const matchesSeverity =
        selectedSeverity === 'ALL' ||
        incident.severity?.toLowerCase() === selectedSeverity.toLowerCase();

      // 3. Status Filter
      const matchesStatus =
        selectedStatus === 'ALL' ||
        incident.status?.toLowerCase() === selectedStatus.toLowerCase();

      return matchesQuery && matchesSeverity && matchesStatus;
    });
  }, [incidents, searchQuery, selectedSeverity, selectedStatus]);

  const handleResetFilters = () => {
    setSearchQuery('');
    setSelectedSeverity('ALL');
    setSelectedStatus('ALL');
  };

  const handleEraseAll = async () => {
    if (deleting || incidents.length === 0) return;
    const confirmed = window.confirm(
      'Erase every stored incident, including saved investigations and evidence? This cannot be undone.'
    );
    if (!confirmed) return;

    setDeleting(true);
    setError(null);
    try {
      await deleteAllIncidents();
      setIncidents([]);
    } catch (err) {
      console.error('[IncidentsPage] Error deleting incidents:', err);
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : err?.message || 'Failed to erase incidents.');
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-2xl font-bold text-slate-800 tracking-tight flex items-center gap-2.5">
              <AlertTriangle className="h-6 w-6 text-[#384959]" />
              Incidents Management
            </h1>
            {isMock && <DemoDataBadge />}
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Monitor, search, and triage system alerts across microservices.
          </p>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-auto">
          <button
            onClick={handleEraseAll}
            disabled={loading || deleting || incidents.length === 0}
            className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-white border border-red-200 text-red-700 hover:bg-red-50 transition-all shadow-xs flex items-center gap-1.5 disabled:opacity-50"
          >
            {deleting ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Trash2 className="h-3.5 w-3.5" />
            )}
            <span>{deleting ? 'Erasing...' : 'Erase all'}</span>
          </button>
          <button
            onClick={fetchIncidentsData}
            disabled={loading || deleting}
            className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 transition-all shadow-xs flex items-center gap-1.5 disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 text-slate-500 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Error State Banner */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-800 p-4 rounded-xl flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-red-600" />
            <span>{error}</span>
          </div>
          <button
            onClick={fetchIncidentsData}
            className="px-3 py-1 bg-red-100 hover:bg-red-200 text-red-900 rounded font-semibold text-xs"
          >
            Retry
          </button>
        </div>
      )}

      {/* Filter and Search Bar */}
      <IncidentFilters
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        selectedSeverity={selectedSeverity}
        onSeverityChange={setSelectedSeverity}
        selectedStatus={selectedStatus}
        onStatusChange={setSelectedStatus}
        onResetFilters={handleResetFilters}
        totalResults={filteredIncidents.length}
      />

      {/* Loading State */}
      {loading ? (
        <div className="bg-white border border-slate-200 rounded-xl p-12 flex flex-col items-center justify-center gap-3 text-slate-500 shadow-xs">
          <Loader2 className="h-8 w-8 text-[#384959] animate-spin" />
          <p className="text-xs font-medium">Loading incident telemetry...</p>
        </div>
      ) : filteredIncidents.length === 0 ? (
        /* Empty State */
        <div className="bg-white border border-slate-200 rounded-xl p-12 text-center text-slate-500 shadow-xs space-y-3">
          <Inbox className="h-10 w-10 text-slate-400 mx-auto" />
          <h3 className="text-sm font-semibold text-slate-700">No incidents match your filter criteria</h3>
          <p className="text-xs text-slate-500">Try adjusting your search terms, severity, or status filter.</p>
          <button
            onClick={handleResetFilters}
            className="px-4 py-2 bg-[#384959] text-white rounded-lg text-xs font-semibold hover:bg-[#2b3844] transition-all"
          >
            Reset Filters
          </button>
        </div>
      ) : (
        /* Incidents Table Component */
        <IncidentTable incidents={filteredIncidents} />
      )}
    </div>
  );
};

export default IncidentsPage;
