import React from 'react';
import { useLocation, Link } from 'react-router-dom';
import { Clock, RefreshCw, User, ChevronRight } from 'lucide-react';

const Navbar = () => {
  const location = useLocation();

  // Generate breadcrumb info
  const pathParts = location.pathname.split('/').filter(Boolean);
  const breadcrumbItems = pathParts.map((part, idx) => {
    const path = '/' + pathParts.slice(0, idx + 1).join('/');
    let label = part.charAt(0).toUpperCase() + part.slice(1);
    if (part.startsWith('INC-')) label = part;
    return { path, label };
  });

  return (
    <header className="h-14 bg-white border-b border-slate-200 px-6 flex items-center justify-between sticky top-0 z-10 select-none shadow-xs">
      {/* Left: Breadcrumbs / Current Location */}
      <div className="flex items-center gap-2 text-xs text-slate-500 font-sans">
        <Link to="/" className="hover:text-slate-800 font-medium">
          System Overview
        </Link>
        {breadcrumbItems.map((item, idx) => (
          <React.Fragment key={item.path}>
            <ChevronRight className="h-3.5 w-3.5 text-slate-400" />
            {idx === breadcrumbItems.length - 1 ? (
              <span className="font-semibold text-slate-800 font-sans">{item.label}</span>
            ) : (
              <Link to={item.path} className="hover:text-slate-800 font-medium">
                {item.label}
              </Link>
            )}
          </React.Fragment>
        ))}
      </div>

      {/* Right: Controls & User Profile */}
      <div className="flex items-center gap-4">
        {/* Subtle Cluster Status Indicator */}
        <div className="hidden sm:flex items-center gap-2 text-xs text-slate-600 bg-slate-50 px-2.5 py-1 rounded-md border border-slate-200">
          <span className="h-2 w-2 rounded-full bg-emerald-500" />
          <span className="font-medium">Cluster Operational</span>
        </div>

        {/* Time Range Selector */}
        <div className="flex items-center gap-1.5 text-xs text-slate-600 bg-slate-50 border border-slate-200 rounded-md px-2.5 py-1">
          <Clock className="h-3.5 w-3.5 text-slate-400" />
          <select className="bg-transparent text-xs font-medium text-slate-700 focus:outline-none cursor-pointer">
            <option value="1h">Last 1 hour</option>
            <option value="24h">Last 24 hours</option>
            <option value="7d">Last 7 days</option>
          </select>
        </div>

        {/* Refresh Button */}
        <button
          onClick={() => window.location.reload()}
          className="p-1.5 text-slate-500 hover:text-slate-800 hover:bg-slate-100 rounded-md transition-colors border border-slate-200"
          title="Refresh Data"
        >
          <RefreshCw className="h-3.5 w-3.5" />
        </button>

        <div className="h-4 w-px bg-slate-200"></div>

        {/* User Avatar */}
        <div className="flex items-center gap-2.5 text-xs">
          <div className="h-7 w-7 rounded-full bg-[#384959] text-white flex items-center justify-center font-semibold text-xs shadow-xs">
            <User className="h-4 w-4 text-[#BDDCFC]" />
          </div>
          <div className="hidden lg:block text-left">
            <p className="font-semibold text-slate-800 leading-tight">SRE On-Call</p>
            <p className="text-[11px] text-slate-500">DevOps Engineering</p>
          </div>
        </div>
      </div>
    </header>
  );
};

export default Navbar;
