import React from 'react';
import { NavLink } from 'react-router-dom';
import { LayoutDashboard, AlertTriangle, Server, Activity, ShieldCheck } from 'lucide-react';

const Sidebar = () => {
  const navItems = [
    { path: '/', name: 'Overview', icon: LayoutDashboard },
    { path: '/incidents', name: 'Incidents', icon: AlertTriangle },
    { path: '/services', name: 'Services', icon: Server },
    { path: '/monitoring', name: 'Monitoring', icon: Activity },
  ];

  return (
    <aside className="w-64 bg-[#384959] text-slate-100 flex flex-col justify-between h-screen sticky top-0 shrink-0 select-none shadow-md z-20">
      <div>
        {/* Brand Header */}
        <div className="h-16 flex items-center gap-3 px-5 border-b border-[#6A89A7]/30">
          <div className="h-8 w-8 rounded-md bg-[#88BDF2] text-[#384959] flex items-center justify-center font-bold shadow-sm">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div>
            <h1 className="font-semibold text-white text-sm leading-snug">
              DevOps Incident
            </h1>
            <p className="text-[11px] text-[#BDDCFC] font-medium tracking-wide">
              Investigation System
            </p>
          </div>
        </div>

        {/* Navigation Links */}
        <nav className="p-3 space-y-1 mt-3">
          <div className="px-3 py-1.5 text-[11px] font-medium tracking-wider text-[#BDDCFC]/70 uppercase">
            Main Menu
          </div>
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.path === '/'}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-sm transition-all duration-150 ${
                    isActive
                      ? 'bg-[#6A89A7]/35 text-white font-semibold shadow-sm'
                      : 'text-[#BDDCFC]/80 hover:text-white hover:bg-[#6A89A7]/20 font-normal'
                  }`
                }
              >
                <Icon className="h-4 w-4 shrink-0 text-[#88BDF2]" />
                <span>{item.name}</span>
              </NavLink>
            );
          })}
        </nav>
      </div>

      {/* Environment Footer */}
      <div className="p-4 border-t border-[#6A89A7]/30 bg-[#384959]/50">
        <div className="flex items-center justify-between text-xs">
          <div>
            <span className="text-[11px] text-[#BDDCFC]/70 block font-sans">Environment</span>
            <span className="font-medium text-white text-xs">Production</span>
          </div>
          <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-sm" title="Operational" />
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
