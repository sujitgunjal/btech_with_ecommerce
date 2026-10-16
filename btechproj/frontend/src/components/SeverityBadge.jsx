import React from 'react';
import { AlertOctagon, AlertTriangle, AlertCircle, Info } from 'lucide-react';

/**
 * SeverityBadge component - Restrained, modern SaaS severity badge
 */
const SeverityBadge = ({ severity, showIcon = true, size = 'sm', className = '' }) => {
  const normalized = severity?.toString().toUpperCase() || 'UNKNOWN';

  let config = {
    label: normalized,
    style: 'bg-slate-100 text-slate-700 border-slate-200',
    icon: Info,
  };

  switch (normalized) {
    case 'CRITICAL':
    case 'P1':
      config = {
        label: 'Critical',
        style: 'bg-red-50 text-red-700 border-red-200 font-semibold',
        icon: AlertOctagon,
      };
      break;
    case 'HIGH':
    case 'P2':
      config = {
        label: 'High',
        style: 'bg-amber-50 text-amber-700 border-amber-200 font-semibold',
        icon: AlertTriangle,
      };
      break;
    case 'MEDIUM':
    case 'P3':
      config = {
        label: 'Medium',
        style: 'bg-yellow-50 text-yellow-800 border-yellow-200 font-medium',
        icon: AlertCircle,
      };
      break;
    case 'LOW':
    case 'P4':
      config = {
        label: 'Low',
        style: 'bg-blue-50 text-blue-700 border-blue-200 font-medium',
        icon: Info,
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
      : 'px-2 py-0.5 text-xs gap-1';

  return (
    <span
      className={`inline-flex items-center rounded-md border ${config.style} ${sizeClasses} ${className}`}
    >
      {showIcon && <IconComponent className={size === 'xs' ? 'h-3 w-3' : 'h-3.5 w-3.5'} />}
      <span>{config.label}</span>
    </span>
  );
};

export default SeverityBadge;
