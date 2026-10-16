import React from 'react';
import { Activity, Search, CheckCircle2, AlertCircle } from 'lucide-react';

/**
 * StatusBadge component - Clean restrained status badge for modern SaaS UI
 */
const StatusBadge = ({ status, showIcon = true, size = 'sm', className = '' }) => {
  const normalized = status?.toString().toLowerCase() || 'unknown';

  let config = {
    label: status || 'Unknown',
    style: 'bg-slate-100 text-slate-600 border-slate-200',
    indicator: 'bg-slate-400',
    icon: AlertCircle,
  };

  switch (normalized) {
    case 'active':
    case 'firing':
    case 'critical':
      config = {
        label: 'Active',
        style: 'bg-red-50 text-red-700 border-red-200 font-semibold',
        indicator: 'bg-red-600',
        icon: Activity,
      };
      break;
    case 'investigating':
    case 'acknowledged':
    case 'degraded':
      config = {
        label: normalized === 'degraded' ? 'Degraded' : 'Investigating',
        style: 'bg-amber-50 text-amber-700 border-amber-200 font-semibold',
        indicator: 'bg-amber-500',
        icon: Search,
      };
      break;
    case 'resolved':
    case 'closed':
    case 'healthy':
    case 'operational':
      config = {
        label: normalized === 'healthy' || normalized === 'operational' ? 'Healthy' : 'Resolved',
        style: 'bg-emerald-50 text-emerald-700 border-emerald-200 font-medium',
        indicator: 'bg-emerald-500',
        icon: CheckCircle2,
      };
      break;
    default:
      break;
  }

  const IconComponent = config.icon;

  const sizeClasses =
    size === 'xs'
      ? 'px-1.5 py-0.5 text-[11px] gap-1'
      : size === 'md'
      ? 'px-3 py-1 text-xs gap-1.5'
      : 'px-2.5 py-0.5 text-xs gap-1.5';

  return (
    <span
      className={`inline-flex items-center rounded-md border ${config.style} ${sizeClasses} ${className}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${config.indicator}`} />
      {showIcon && <IconComponent className={size === 'xs' ? 'h-3 w-3' : 'h-3.5 w-3.5'} />}
      <span>{config.label}</span>
    </span>
  );
};

export default StatusBadge;
