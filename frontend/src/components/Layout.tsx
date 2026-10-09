import clsx from 'clsx';
import {
  Activity, BarChart3, Brain, Building2, Cpu, FlaskConical, GitBranch, KanbanSquare, LayoutDashboard,
  LogOut, Menu, Network, Play, Route, Shield, Siren, Truck, X,
} from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../store/auth';
import { useLive } from '../store/live';
import type { Role } from '../api/types';
import { Badge } from './ui';

interface NavItem { to: string; label: string; icon: ReactNode; roles?: Role[] }

export const NAV: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: <LayoutDashboard className="h-4 w-4" /> },
  { to: '/command', label: 'Command Center', icon: <Siren className="h-4 w-4" /> },
  { to: '/incidents', label: 'Incidents', icon: <Activity className="h-4 w-4" /> },
  { to: '/compiler', label: 'Compiler Lab', icon: <Cpu className="h-4 w-4" /> },
  { to: '/toc', label: 'TOC Lab', icon: <GitBranch className="h-4 w-4" /> },
  { to: '/routing', label: 'Routing & Traffic', icon: <Route className="h-4 w-4" /> },
  { to: '/resources', label: 'Resources', icon: <Truck className="h-4 w-4" /> },
  { to: '/hospitals', label: 'Hospitals', icon: <Building2 className="h-4 w-4" /> },
  { to: '/ml', label: 'ML Models', icon: <Brain className="h-4 w-4" /> },
  { to: '/simulation', label: 'Simulation', icon: <Play className="h-4 w-4" /> },
  { to: '/analytics', label: 'Analytics', icon: <BarChart3 className="h-4 w-4" /> },
  { to: '/agile', label: 'Agile Board', icon: <KanbanSquare className="h-4 w-4" /> },
  { to: '/admin', label: 'Admin', icon: <Shield className="h-4 w-4" />, roles: ['ADMIN'] },
];

export function Layout() {
  const { user, logout } = useAuth();
  const { status } = useLive();
  const [open, setOpen] = useState(false);
  const items = NAV.filter((n) => !n.roles || (user && n.roles.includes(user.role)));

  return (
    <div className="flex min-h-screen bg-navy-950 text-slate-200">
      {open && <div className="fixed inset-0 z-[1100] bg-black/60 lg:hidden" onClick={() => setOpen(false)} />}
      <aside className={clsx(
        'fixed inset-y-0 left-0 z-[1200] flex w-60 flex-col border-r border-navy-700 bg-navy-900 transition-transform lg:static lg:translate-x-0',
        open ? 'translate-x-0' : '-translate-x-full',
      )}>
        <div className="flex items-center justify-between gap-2 px-4 py-4">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-red-600 shadow-lg shadow-red-600/30">
              <Network className="h-5 w-5 text-white" />
            </div>
            <div>
              <div className="text-sm font-bold tracking-wider text-white">RESQ-AI</div>
              <div className="text-[10px] uppercase tracking-widest text-slate-500">Command System</div>
            </div>
          </div>
          <button type="button" className="text-slate-400 lg:hidden" onClick={() => setOpen(false)} aria-label="Close menu"><X className="h-5 w-5" /></button>
        </div>
        <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-4">
          {items.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === '/'}
              onClick={() => setOpen(false)}
              className={({ isActive }) => clsx(
                'flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition',
                isActive ? 'bg-sky-500/15 text-sky-300' : 'text-slate-400 hover:bg-navy-800 hover:text-slate-200',
              )}
            >
              {n.icon}{n.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-navy-700 px-4 py-3 text-[11px] text-slate-500">
          <FlaskConical className="mr-1 inline h-3 w-3" /> Simulation data is clearly labelled.
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-[1000] flex items-center justify-between gap-3 border-b border-navy-700 bg-navy-900/90 px-4 py-2.5 backdrop-blur">
          <div className="flex items-center gap-3">
            <button type="button" className="text-slate-300 lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu"><Menu className="h-5 w-5" /></button>
            <span className="flex items-center gap-1.5 text-xs text-slate-400" title={`WebSocket: ${status}`}>
              <span className={clsx('h-2 w-2 rounded-full', status === 'open' ? 'animate-pulsedot bg-emerald-400' : status === 'connecting' ? 'bg-yellow-400' : 'bg-red-500')} />
              {status === 'open' ? 'Live' : status === 'connecting' ? 'Connecting…' : 'Offline'}
            </span>
          </div>
          {user && (
            <div className="flex items-center gap-3">
              <div className="text-right">
                <div className="text-sm font-medium text-slate-100">{user.full_name || user.username}</div>
                <div className="text-[11px] text-slate-500">@{user.username}</div>
              </div>
              <Badge tone={user.role === 'ADMIN' ? 'red' : user.role === 'OPERATOR' ? 'orange' : user.role === 'ANALYST' ? 'purple' : 'neutral'}>{user.role}</Badge>
              <button type="button" onClick={logout} className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm text-slate-400 hover:bg-navy-800 hover:text-slate-100">
                <LogOut className="h-4 w-4" /><span className="hidden sm:inline">Logout</span>
              </button>
            </div>
          )}
        </header>
        <main className="min-w-0 flex-1 p-4 md:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
