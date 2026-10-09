import { Plus, RefreshCw, X } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import type { IncidentCreate, IncidentType, Severity } from '../api/types';
import { INCIDENT_TYPES, SEVERITIES } from '../api/types';
import { Async, Badge, Button, Card, ErrorBox, Field, Input, PageHeader, Select, Table, Td, Textarea } from '../components/ui';
import { useAction, useApi } from '../hooks/useApi';
import { useAuth } from '../store/auth';
import { fmtDateTime, fmtSeconds, humanize } from '../utils/format';

export default function IncidentsPage() {
  const { hasRole } = useAuth();
  const canWrite = hasRole('ADMIN', 'OPERATOR');
  const [status, setStatus] = useState('');
  const [type, setType] = useState('');
  const [severity, setSeverity] = useState('');
  const [q, setQ] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');
  const [showForm, setShowForm] = useState(false);
  const list = useApi(() => api.incidents({ status, type, severity, q: debouncedQ, limit: 200 }), [status, type, severity, debouncedQ]);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Incidents"
        subtitle="All reported emergencies, newest first"
        actions={(
          <>
            <Button variant="secondary" onClick={list.reload}><RefreshCw className="h-4 w-4" /> Refresh</Button>
            {canWrite && <Button onClick={() => setShowForm((s) => !s)}>{showForm ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />} New incident</Button>}
          </>
        )}
      />

      {showForm && <NewIncidentForm onCreated={() => { setShowForm(false); void list.reload(); }} />}

      <Card>
        <form
          className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5"
          onSubmit={(e) => { e.preventDefault(); setDebouncedQ(q); }}
        >
          <Field label="Status">
            <Select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All</option>
              {['ACTIVE', 'RESOLVED', 'CANCELLED'].map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
            </Select>
          </Field>
          <Field label="Type">
            <Select value={type} onChange={(e) => setType(e.target.value)}>
              <option value="">All</option>
              {INCIDENT_TYPES.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
            </Select>
          </Field>
          <Field label="Severity">
            <Select value={severity} onChange={(e) => setSeverity(e.target.value)}>
              <option value="">All</option>
              {SEVERITIES.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
            </Select>
          </Field>
          <Field label="Search" className="lg:col-span-2">
            <div className="flex gap-2">
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Title, location, ID…" />
              <Button type="submit" variant="secondary">Search</Button>
            </div>
          </Field>
        </form>
        <Async loading={list.loading} error={list.error} data={list.data} onRetry={list.reload}>
          {(rows) => rows.length === 0 ? <div className="py-6 text-center text-sm text-slate-500">No incidents match these filters.</div> : (
            <Table head={['ID', 'Title', 'Type', 'Severity', 'Location', 'People', 'State', 'Status', 'Created', 'Response']}>
              {rows.map((i) => (
                <tr key={i.id} className="hover:bg-navy-800/50">
                  <Td><Link className="font-mono text-xs text-sky-300 hover:underline" to={`/incidents/${encodeURIComponent(i.id)}`}>{i.id}</Link></Td>
                  <Td className="max-w-[260px] truncate">{i.title}</Td>
                  <Td>{humanize(i.type)}</Td>
                  <Td><Badge value={i.severity} /> <span className="text-[10px] text-slate-500">{i.severity_source}</span></Td>
                  <Td>{i.location_name}</Td>
                  <Td className="tabular-nums">{i.people_affected}</Td>
                  <Td><Badge tone="purple">{i.state}</Badge></Td>
                  <Td><Badge value={i.status} /></Td>
                  <Td className="text-xs text-slate-400">{fmtDateTime(i.created_at)}</Td>
                  <Td className="tabular-nums">{fmtSeconds(i.response_time_s)}</Td>
                </tr>
              ))}
            </Table>
          )}
        </Async>
      </Card>
    </div>
  );
}

function NewIncidentForm({ onCreated }: { onCreated: () => void }) {
  const nav = useNavigate();
  const [form, setForm] = useState({
    type: 'FIRE' as IncidentType, location_name: '', lat: '', lon: '', people_affected: '10',
    severity_estimate: '' as Severity | '', description: '', exits_available: '', exits_blocked: '', hazards: '', additional_info: '',
  });
  const create = useAction((body: IncidentCreate) => api.createIncident(body));
  const set = (k: keyof typeof form, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const body: IncidentCreate = {
      type: form.type,
      location_name: form.location_name.trim(),
      people_affected: Number(form.people_affected) || 0,
    };
    if (form.lat && form.lon) { body.lat = Number(form.lat); body.lon = Number(form.lon); }
    if (form.severity_estimate) body.severity_estimate = form.severity_estimate;
    if (form.description) body.description = form.description;
    if (form.exits_available) body.exits_available = Number(form.exits_available);
    if (form.exits_blocked) body.exits_blocked = Number(form.exits_blocked);
    if (form.hazards.trim()) body.hazards = form.hazards.split(',').map((h) => h.trim()).filter(Boolean);
    if (form.additional_info) body.additional_info = form.additional_info;
    const inc = await create.run(body);
    if (inc) { onCreated(); nav(`/incidents/${encodeURIComponent(inc.id)}`); }
  };

  return (
    <Card title="New incident">
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="Type">
          <Select value={form.type} onChange={(e) => set('type', e.target.value)}>
            {INCIDENT_TYPES.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
          </Select>
        </Field>
        <Field label="Location name *">
          <Input required value={form.location_name} onChange={(e) => set('location_name', e.target.value)} placeholder="e.g. Vijay Nagar" />
        </Field>
        <Field label="Latitude (optional)"><Input type="number" step="any" value={form.lat} onChange={(e) => set('lat', e.target.value)} /></Field>
        <Field label="Longitude (optional)"><Input type="number" step="any" value={form.lon} onChange={(e) => set('lon', e.target.value)} /></Field>
        <Field label="People affected *"><Input required type="number" min={0} value={form.people_affected} onChange={(e) => set('people_affected', e.target.value)} /></Field>
        <Field label="Severity estimate">
          <Select value={form.severity_estimate} onChange={(e) => set('severity_estimate', e.target.value)}>
            <option value="">Let the system decide</option>
            {SEVERITIES.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
          </Select>
        </Field>
        <Field label="Exits available"><Input type="number" min={0} value={form.exits_available} onChange={(e) => set('exits_available', e.target.value)} /></Field>
        <Field label="Exits blocked"><Input type="number" min={0} value={form.exits_blocked} onChange={(e) => set('exits_blocked', e.target.value)} /></Field>
        <Field label="Hazards (comma separated)" className="sm:col-span-2"><Input value={form.hazards} onChange={(e) => set('hazards', e.target.value)} placeholder="smoke, gas leak" /></Field>
        <Field label="Additional info" className="sm:col-span-2"><Input value={form.additional_info} onChange={(e) => set('additional_info', e.target.value)} /></Field>
        <Field label="Description" className="sm:col-span-2 lg:col-span-4"><Textarea rows={2} value={form.description} onChange={(e) => set('description', e.target.value)} /></Field>
        <div className="flex items-center gap-3 sm:col-span-2 lg:col-span-4">
          <Button type="submit" loading={create.busy}>Create incident</Button>
          <div className="flex-1"><ErrorBox error={create.error} /></div>
        </div>
      </form>
    </Card>
  );
}
