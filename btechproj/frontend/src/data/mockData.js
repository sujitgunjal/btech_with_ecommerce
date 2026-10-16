/**
 * Mock data fallback for the DevOps Incident Investigation System Dashboard
 * Retained for fallback when backend/observability services are offline
 */

export const dashboardStats = [
  {
    id: 'active-incidents',
    title: 'Active Incidents',
    value: '1',
    subtitle: '1 Critical incident',
    iconName: 'AlertTriangle',
    variant: 'danger',
    change: 'Active status',
  },
  {
    id: 'healthy-services',
    title: 'Healthy Services',
    value: '3/3',
    subtitle: 'All services operational',
    iconName: 'Server',
    variant: 'success',
    change: '100% operational',
  },
  {
    id: 'error-rate',
    title: 'Error Rate',
    value: '0.0%',
    subtitle: 'Nominal traffic',
    iconName: 'Activity',
    variant: 'success',
    change: 'Threshold: < 1.0%',
  },
  {
    id: 'avg-latency',
    title: 'Average Latency',
    value: '10 ms',
    subtitle: 'p95: 25 ms',
    iconName: 'Clock',
    variant: 'info',
    change: 'Nominal bounds',
  },
];

export const servicesHealthData = [
  {
    id: 'user-service',
    name: 'user-service',
    status: 'Healthy',
    requestCount: '1,200 req/min',
    avgLatency: '15 ms',
    uptime: '99.99%',
  },
  {
    id: 'product-service',
    name: 'product-service',
    status: 'Healthy',
    requestCount: '1,500 req/min',
    avgLatency: '12 ms',
    uptime: '99.99%',
  },
  {
    id: 'order-service',
    name: 'order-service',
    status: 'Healthy',
    requestCount: '800 req/min',
    avgLatency: '22 ms',
    uptime: '99.95%',
  },
];

export const recentIncidentsData = [
  {
    id: 'INC-0001',
    affectedService: 'order-service',
    severity: 'Critical',
    status: 'Active',
    startTime: '2026-08-23 14:15:00',
    description: 'High rate of HTTP 500 responses and connection timeouts in checkout API.',
  },
  {
    id: 'INC-0002',
    affectedService: 'user-service',
    severity: 'High',
    status: 'Investigating',
    startTime: '2026-08-23 15:02:00',
    description: 'Elevated p99 auth token validation latency following cache node failover.',
  },
  {
    id: 'INC-0003',
    affectedService: 'product-service',
    severity: 'Medium',
    status: 'Resolved',
    startTime: '2026-08-23 12:30:00',
    description: 'Catalog indexing delay resolved after background queue consumer restart.',
  },
];

export const incidentsListData = [
  {
    id: 'INC-0001',
    affectedService: 'order-service',
    severity: 'Critical',
    status: 'Active',
    startTime: '2026-08-23 14:15:00',
    description: 'High rate of HTTP 500 responses and connection timeouts in checkout API.',
  },
  {
    id: 'INC-0002',
    affectedService: 'user-service',
    severity: 'High',
    status: 'Investigating',
    startTime: '2026-08-23 15:02:00',
    description: 'Elevated p99 auth token validation latency following cache node failover.',
  },
  {
    id: 'INC-0003',
    affectedService: 'product-service',
    severity: 'Medium',
    status: 'Resolved',
    startTime: '2026-08-23 12:30:00',
    description: 'Catalog indexing delay resolved after background queue consumer restart.',
  },
  {
    id: 'INC-0004',
    affectedService: 'order-service',
    severity: 'Low',
    status: 'Resolved',
    startTime: '2026-08-23 09:10:00',
    description: 'Minor latency spike during TLS certificate auto-renewal cycle.',
  },
  {
    id: 'INC-0005',
    affectedService: 'order-service',
    severity: 'High',
    status: 'Active',
    startTime: '2026-08-23 16:05:00',
    description: 'Payment gateway API timeouts causing cart checkout retries.',
  },
  {
    id: 'INC-0006',
    affectedService: 'user-service',
    severity: 'Medium',
    status: 'Investigating',
    startTime: '2026-08-23 13:45:00',
    description: 'Slow session validation queries impacting user login latency.',
  },
  {
    id: 'INC-0007',
    affectedService: 'product-service',
    severity: 'Low',
    status: 'Resolved',
    startTime: '2026-08-22 21:15:00',
    description: 'Product thumbnail image cache miss rate temporary spike.',
  },
];

/**
 * Get detailed mock incident object by ID
 */
export const getMockIncidentById = (id) => {
  const incidentId = id || 'INC-0001';
  const found = incidentsListData.find(
    (inc) => inc.id.toLowerCase() === String(incidentId).toLowerCase()
  );

  if (found) {
    return {
      id: found.id,
      title: `${found.severity} Incident: ${found.affectedService} Anomaly`,
      service: found.affectedService,
      affectedService: found.affectedService,
      severity: found.severity,
      status: found.status,
      createdAt: found.startTime,
      description: found.description,
      environment: 'production-us-east',
      reporter: 'Prometheus Alertmanager',
      assignedTeam: 'Platform SRE Team',
      p99_latency_ms: found.id === 'INC-0001' ? 4105.0 : 1850.0,
      error_rate: found.id === 'INC-0001' ? 14.8 : 5.2,
      captured_at: found.startTime,
      timeline: [
        { time: found.startTime.split(' ')[1] || '14:15:02', event: `Alert firing: Metric threshold exceeded on ${found.affectedService}` },
        { time: '14:16:10', event: 'PagerDuty incident created & assigned to SRE On-call' },
        { time: '14:18:45', event: 'Status updated to INVESTIGATING by SRE Engineer' },
      ],
    };
  }

  return {
    id: incidentId,
    title: 'High latency and error rates on Order Service',
    service: 'order-service',
    affectedService: 'order-service',
    severity: 'Critical',
    status: 'Active',
    createdAt: '2026-08-23 14:15:00',
    description:
      'Automated alert triggered due to response latency exceeding threshold over 5 consecutive minutes on order-service.',
    environment: 'production-us-east',
    reporter: 'Prometheus Alertmanager',
    assignedTeam: 'Platform SRE Team',
    p99_latency_ms: 4105.0,
    error_rate: 14.8,
    captured_at: '2026-08-23 14:15:00',
    timeline: [
      { time: '14:15:02', event: 'Alert firing: OrderServiceHighLatency metric threshold' },
      { time: '14:16:10', event: 'PagerDuty incident created & assigned to SRE On-call' },
      { time: '14:18:45', event: 'Status updated to INVESTIGATING by SRE Engineer' },
    ],
  };
};

/**
 * Get detailed mock investigation result object by ID
 */
export const getMockInvestigationResult = (id) => {
  const incidentId = id || 'INC-0001';
  return {
    incidentId: incidentId,
    status: 'COMPLETED',
    summary: 'Operational Data Collection Completed',
    steps: [
      { id: 1, label: 'Collecting logs', detail: 'Fetching container stdout/stderr & system logs...', status: 'Completed' },
      { id: 2, label: 'Collecting metrics', detail: 'Querying Prometheus CPU, memory, and latency metrics...', status: 'Completed' },
      { id: 3, label: 'Collecting traces', detail: 'Analyzing OpenTelemetry distributed trace spans...', status: 'Completed' },
      { id: 4, label: 'Checking deployment history', detail: 'Inspecting deployment events & git commits...', status: 'Completed' },
      { id: 5, label: 'Investigation pending', detail: 'Operational data collection completed.', status: 'Completed' },
    ],
    timestamp: new Date().toISOString(),
  };
};

/**
 * Get mock incident logs by ID
 */
export const getMockIncidentLogs = (id) => [
  { timestamp: '2026-08-23 14:15:02', level: 'ERROR', service: 'order-service', message: 'Connection reset by peer: DB connection pool exhausted' },
  { timestamp: '2026-08-23 14:15:05', level: 'WARN', service: 'order-service', message: 'Retrying connection attempt 3/5 to postgres-db' },
  { timestamp: '2026-08-23 14:15:10', level: 'ERROR', service: 'order-service', message: 'HTTP 500 returned for POST /orders (upstream timeout)' },
];

/**
 * Get mock incident metrics by ID
 */
export const getMockIncidentMetrics = (id) => ({
  latencyP99: '4120 ms',
  errorRate: '14.8%',
  cpuUsage: '92.4%',
  memoryUsage: '88.1%',
  timeSeries: [
    { time: '14:00', latency: 120, errors: 0.1 },
    { time: '14:05', latency: 250, errors: 0.2 },
    { time: '14:10', latency: 1800, errors: 4.5 },
    { time: '14:15', latency: 4120, errors: 14.8 },
  ],
});

/**
 * Get mock incident traces by ID
 */
export const getMockIncidentTraces = (id) => [
  { traceId: 'tr-98f2b1a0', span: 'POST /orders', duration: '4120ms', status: 'ERROR', service: 'order-service' },
  { traceId: 'tr-98f2b1a0', span: 'DB.query.SELECT_users', duration: '3500ms', status: 'TIMEOUT', service: 'order-service' },
];

/**
 * Get mock incident deployments by ID
 */
export const getMockIncidentDeployments = (id) => [
  { timestamp: '2026-08-23 14:00:00', version: 'v2.14.0', deployedBy: 'github-actions', status: 'SUCCESS', service: 'order-service' },
  { timestamp: '2026-08-22 18:30:00', version: 'v2.13.9', deployedBy: 'sre-oncall', status: 'SUCCESS', service: 'order-service' },
];
