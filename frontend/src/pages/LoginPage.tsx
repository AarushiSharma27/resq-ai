import { Network } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { errorMessage } from '../api/client';
import { Button, ErrorBox, Field, Input } from '../components/ui';
import { useAuth } from '../store/auth';

export const DEMO_USERS = [
  { username: 'admin', password: 'admin123', role: 'ADMIN' },
  { username: 'operator', password: 'operator123', role: 'OPERATOR' },
  { username: 'analyst', password: 'analyst123', role: 'ANALYST' },
  { username: 'viewer', password: 'viewer123', role: 'VIEWER' },
];

export default function LoginPage() {
  const { login, register, token } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [mode, setMode] = useState<'signin' | 'signup'>('signin');
  const [fullName, setFullName] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const from = (loc.state as { from?: string } | null)?.from || '/';

  if (token) return <Navigate to={from} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (mode === 'signup' && password !== confirm) {
      setError('Passwords do not match');
      return;
    }
    setBusy(true);
    try {
      if (mode === 'signup') await register(username, password, fullName);
      else await login(username, password);
      nav(from, { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-navy-950 bg-[radial-gradient(ellipse_at_top,rgba(239,68,68,0.12),transparent_60%)] p-4">
      <div className="w-full max-w-md rounded-2xl border border-navy-700 bg-navy-900/90 p-6 shadow-2xl shadow-black/40">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-red-600 shadow-lg shadow-red-600/40">
            <Network className="h-6 w-6 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-wider text-white">RESQ-AI</h1>
            <p className="text-xs uppercase tracking-widest text-slate-500">Emergency Rescue Command System</p>
          </div>
        </div>
        <form onSubmit={submit} className="space-y-4">
          <Field label="Username">
            <Input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />
          </Field>
          {mode === 'signup' && (
            <Field label="Full name (optional)">
              <Input value={fullName} onChange={(e) => setFullName(e.target.value)} autoComplete="name" />
            </Field>
          )}
          <Field label="Password">
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === 'signup' ? 'new-password' : 'current-password'} minLength={mode === 'signup' ? 6 : undefined} required />
          </Field>
          {mode === 'signup' && (
            <Field label="Confirm password">
              <Input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" required />
            </Field>
          )}
          <ErrorBox error={error} />
          <Button type="submit" loading={busy} className="w-full">{mode === 'signup' ? 'Create account' : 'Sign in'}</Button>
        </form>
        <p className="mt-4 text-center text-sm text-slate-400">
          {mode === 'signup' ? 'Already have an account?' : 'New here?'}{' '}
          <button
            type="button"
            onClick={() => { setMode(mode === 'signup' ? 'signin' : 'signup'); setError(null); setConfirm(''); }}
            className="text-sky-400 hover:underline"
          >
            {mode === 'signup' ? 'Sign in' : 'Create an account'}
          </button>
        </p>
        <div className="mt-6">
          <div className="mb-2 text-xs uppercase tracking-wide text-slate-500">Demo accounts (quick fill)</div>
          <div className="grid grid-cols-2 gap-2">
            {DEMO_USERS.map((u) => (
              <button
                key={u.username}
                type="button"
                onClick={() => { setUsername(u.username); setPassword(u.password); }}
                className="rounded-lg border border-navy-600 bg-navy-850 px-3 py-2 text-left text-sm hover:border-sky-500"
              >
                <div className="font-medium text-slate-200">{u.username}</div>
                <div className="text-[11px] text-slate-500">{u.role} · {u.password}</div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
