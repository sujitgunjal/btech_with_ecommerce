import React from 'react';
import { AlertTriangle, Server, Activity, Clock } from 'lucide-react';

const iconMap = {
  AlertTriangle,
  Server,
  Activity,
  Clock,
};

/**
 * StatCard component - Light modern SaaS metric card
 */
const StatCard = ({
  title,
  value,
  subtitle,
  change,
  icon,
  iconName,
  variant = 'info',
  className = '',
}) => {
  let IconComponent = icon;
  if (!IconComponent && iconName && iconMap[iconName]) {
    IconComponent = iconMap[iconName];
  }
  if (!IconComponent) {
    IconComponent = Activity;
  }

  return (
    <div
      className={`bg-white border border-slate-200 rounded-xl p-5 shadow-xs transition-all duration-200 ${className}`}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">
          {title}
        </span>
        <div className="p-2 rounded-lg bg-slate-100 text-[#384959]">
          <IconComponent className="h-4 w-4" />
        </div>
      </div>

      <div className="mt-3">
        <div className="text-2xl font-bold text-slate-800 font-mono tracking-tight">
          {value}
        </div>

        <div className="flex items-center justify-between mt-2 pt-2 border-t border-slate-100 text-[11px]">
          {subtitle && <span className="text-slate-500 font-medium truncate">{subtitle}</span>}
          {change && (
            <span className="font-medium px-1.5 py-0.5 rounded text-[11px] bg-slate-100 text-slate-700">
              {change}
            </span>
          )}
        </div>
      </div>
    </div>
  );
};

export default StatCard;
