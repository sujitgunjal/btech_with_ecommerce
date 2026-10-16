/**
 * Returns restrained Tailwind CSS color classes for incident severity levels
 */
export const getSeverityBadgeStyle = (severity) => {
  switch (severity?.toUpperCase()) {
    case 'CRITICAL':
    case 'P1':
      return 'bg-red-50 text-red-700 border-red-200';
    case 'HIGH':
    case 'P2':
      return 'bg-amber-50 text-amber-700 border-amber-200';
    case 'MEDIUM':
    case 'P3':
      return 'bg-yellow-50 text-yellow-700 border-yellow-200';
    case 'LOW':
    case 'P4':
      return 'bg-blue-50 text-blue-700 border-blue-200';
    default:
      return 'bg-slate-50 text-slate-600 border-slate-200';
  }
};

/**
 * Returns restrained Tailwind CSS color classes for incident/service statuses
 */
export const getStatusBadgeStyle = (status) => {
  switch (status?.toLowerCase()) {
    case 'active':
    case 'firing':
    case 'critical':
      return 'bg-red-50 text-red-700 border-red-200';
    case 'investigating':
    case 'acknowledged':
    case 'degraded':
      return 'bg-amber-50 text-amber-700 border-amber-200';
    case 'resolved':
    case 'healthy':
    case 'operational':
      return 'bg-emerald-50 text-emerald-700 border-emerald-200';
    default:
      return 'bg-slate-50 text-slate-600 border-slate-200';
  }
};

/**
 * Formats ISO date string to clean human readable timestamp
 */
export const formatDate = (dateString) => {
  if (!dateString) return 'N/A';
  const date = new Date(dateString);
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
};
