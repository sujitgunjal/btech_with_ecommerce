import api from './api';

const INVESTIGATE_TIMEOUT_MS = 180000;
const EVIDENCE_TIMEOUT_MS = 60000;

function incidentPathId(id) {
  if (id === null || id === undefined || id === '') {
    throw new Error('Incident id is required.');
  }
  if (typeof id === 'number' && Number.isFinite(id)) {
    return String(id);
  }
  const value = String(id).trim();
  if (/^\d+$/.test(value)) return value;
  return value;
}

function requestMatchesLiveIncident(requested, dbId, externalId) {
  const req = String(requested).trim();
  if (/^\d+$/.test(req)) return Number(req) === Number(dbId);
  return req.toUpperCase() === String(externalId).toUpperCase();
}

/**
 * Fetch all incidents
 * Endpoint: GET /incidents
 */
export const getIncidents = async () => {
  const response = await api.get('/incidents');
  const rawList = Array.isArray(response.data)
    ? response.data
    : response.data.incidents || [];
  const normalized = rawList.map((inc) => ({
    id:
      inc.external_id ||
      (typeof inc.id === 'number'
        ? `INC-${String(inc.id).padStart(4, '0')}`
        : inc.id),
    db_id: inc.id,
    affectedService: inc.service || inc.affectedService || 'Order Service',
    service: inc.service || inc.affectedService || 'Order Service',
    severity: inc.severity
      ? inc.severity.charAt(0).toUpperCase() + inc.severity.slice(1)
      : 'Medium',
    status: inc.status
      ? inc.status.charAt(0).toUpperCase() + inc.status.slice(1)
      : 'Active',
    startTime: inc.start_time
      ? inc.start_time.replace('T', ' ').substring(0, 19)
      : inc.startTime || '',
    p99_latency_ms: inc.p99_latency_ms ?? null,
    error_rate: inc.error_rate ?? null,
    captured_at: inc.captured_at
      ? inc.captured_at.replace('T', ' ').substring(0, 19)
      : inc.start_time
      ? inc.start_time.replace('T', ' ').substring(0, 19)
      : inc.startTime || '',
    description: inc.description || '',
  }));
  return { data: normalized, isMock: false };
};

/**
 * Delete every stored incident, including investigations and evidence.
 * Endpoint: DELETE /incidents
 */
export const deleteAllIncidents = async () => {
  const response = await api.delete('/incidents');
  return { data: response.data, isMock: false };
};

/**
 * Fetch incident details by ID
 * Endpoint: GET /incidents/:id
 */
export const getIncidentById = async (id) => {
  const requested = incidentPathId(id);
  const response = await api.get(`/incidents/${encodeURIComponent(requested)}`);
  const inc = response.data;
  const externalId =
    inc.external_id ||
    (typeof inc.id === 'number'
      ? `INC-${String(inc.id).padStart(4, '0')}`
      : inc.id);
  if (!requestMatchesLiveIncident(requested, inc.id, externalId)) {
    throw new Error(
      `${requested} is a historical scenario id, not live incident ${externalId}. Open the live incident from the incidents list. Historical ids such as INC-004 stay RAG context and are not opened as a different database record.`
    );
  }
  const normalized = {
    id: externalId,
    db_id: inc.id,
    title: inc.title || (inc.service ? `Alert on ${inc.service}` : 'Incident'),
    service: inc.service || inc.affectedService || '',
    affectedService: inc.service || inc.affectedService || '',
    severity: inc.severity
      ? inc.severity.charAt(0).toUpperCase() + inc.severity.slice(1)
      : '',
    status: inc.status
      ? inc.status.charAt(0).toUpperCase() + inc.status.slice(1)
      : '',
    createdAt: inc.start_time
      ? inc.start_time.replace('T', ' ').substring(0, 19)
      : inc.created_at || '',
    startTime: inc.start_time
      ? inc.start_time.replace('T', ' ').substring(0, 19)
      : '',
    endTime: inc.end_time
      ? String(inc.end_time).replace('T', ' ').substring(0, 19)
      : '',
    p99_latency_ms: inc.p99_latency_ms ?? null,
    error_rate: inc.error_rate ?? null,
    captured_at: inc.captured_at
      ? inc.captured_at.replace('T', ' ').substring(0, 19)
      : inc.start_time
      ? inc.start_time.replace('T', ' ').substring(0, 19)
      : inc.created_at || '',
    description: inc.description || '',
    environment: inc.environment || '',
    reporter: inc.reporter || '',
    assignedTeam: inc.assigned_team || inc.assignedTeam || '',
    timeline: Array.isArray(inc.timeline) ? inc.timeline : [],
  };
  return { data: normalized, isMock: false };
};

/**
 * Fetch unified telemetry evidence for an incident.
 * Endpoint: GET /incidents/:id/evidence
 */
export const getIncidentEvidence = async (id) => {
  const numericId = await resolveLiveDbId(id);
  const response = await api.get(`/incidents/${numericId}/evidence`, {
    timeout: EVIDENCE_TIMEOUT_MS,
  });
  const payload = response.data || {};
  return {
    data: {
      incident_id: payload.incident_id,
      service: payload.service,
      time_window: payload.time_window || null,
      logs: Array.isArray(payload.logs) ? payload.logs : [],
      metrics: Array.isArray(payload.metrics) ? payload.metrics : [],
      traces: Array.isArray(payload.traces) ? payload.traces : [],
    },
    isMock: false,
  };
};

/**
 * Fetch logs related to a specific incident
 * Endpoint: GET /incidents/:id/evidence
 */
export const getIncidentLogs = async (id) => {
  const evidence = await getIncidentEvidence(id);
  return { data: evidence.data.logs, isMock: false };
};

/**
 * Fetch metrics related to a specific incident
 */
export const getIncidentMetrics = async (id) => {
  const evidence = await getIncidentEvidence(id);
  return { data: evidence.data.metrics, isMock: false };
};

/**
 * Fetch traces related to a specific incident
 */
export const getIncidentTraces = async (id) => {
  const evidence = await getIncidentEvidence(id);
  return { data: evidence.data.traces, isMock: false };
};

/**
 * Deployment history is not exposed by the backend.
 */
export const getIncidentDeployments = async () => {
  throw new Error('Deployment history is not available from the backend.');
};

/**
 * Create a new incident record
 * Endpoint: POST /incidents
 */
export const createIncident = async (data) => {
  try {
    const payload = {
      title: data.title || data.description || 'New Incident',
      description: data.description || '',
      service: data.service || data.affectedService || 'order-service',
      severity: (data.severity || 'critical').toLowerCase(),
      start_time: data.start_time || new Date().toISOString(),
    };
    const response = await api.post('/incidents', payload);
    return { data: response.data, isMock: false };
  } catch (error) {
    console.warn(
      '[incidentService] POST /incidents failed. Falling back to mock creation response. Cause:',
      error.message
    );
    const newMockIncident = {
      id: `INC-${Math.floor(100 + Math.random() * 900)}`,
      affectedService: data.affectedService || 'Order Service',
      severity: data.severity || 'Medium',
      status: data.status || 'Active',
      startTime: new Date().toISOString().replace('T', ' ').substring(0, 19),
      description: data.description || 'Newly created incident',
    };
    return { data: newMockIncident, isMock: true };
  }
};

/**
 * Trigger operational investigation workflow for an incident
 * Endpoint: POST /incidents/:id/investigate
 */
async function resolveLiveDbId(id) {
  if (typeof id === 'number' || /^\d+$/.test(String(id).trim())) {
    return String(id);
  }
  const loaded = await getIncidentById(id);
  return String(loaded.data.db_id);
}

export const investigateIncident = async (id) => {
  const numericId = await resolveLiveDbId(id);
  const response = await api.post(`/incidents/${numericId}/investigate`, null, {
    timeout: INVESTIGATE_TIMEOUT_MS,
  });
  return { data: response.data, isMock: false };
};

/**
 * Alias for investigateIncident to match pipeline triggering conventions
 */
export const startInvestigation = investigateIncident;
