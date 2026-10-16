import React from 'react';
import { Database } from 'lucide-react';

/**
 * DemoDataBadge - Displays a visible indicator when mock/demo data is in use
 */
const DemoDataBadge = ({ className = '' }) => {
  return (
    <span
      title="Using demo data fallback. Backend API is not currently connected."
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-amber-50 text-amber-700 text-xs font-semibold border border-amber-200 shadow-2xs ${className}`}
    >
      <Database className="h-3.5 w-3.5 text-amber-600" />
      <span>Demo Data</span>
    </span>
  );
};

export default DemoDataBadge;
