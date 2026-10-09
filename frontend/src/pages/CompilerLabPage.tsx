import { useState } from 'react';
import { api } from '../api/client';
import type { CompileResult, LexResult, ParseResult, ValidateResult } from '../api/types';
import { CompilerErrorList, JsonBlock, ParseTreeView, TokenStrip, TokenTable } from '../components/CompilerViews';
import { Async, Badge, Button, Card, ErrorBox, PageHeader, Table, Td, Textarea } from '../components/ui';
import { useAction, useApi } from '../hooks/useApi';

type Out =
  | { kind: 'lex'; data: LexResult }
  | { kind: 'parse'; data: ParseResult }
  | { kind: 'validate'; data: ValidateResult }
  | { kind: 'compile'; data: CompileResult };

const SAMPLES = [
  'Fire at School A in Vijay Nagar, 500 students affected, 2 exits blocked, send 3 ambulances and 2 fire trucks, evacuate building',
  'Accident near Rajwada with 12 injured, send 4 ambulances and 2 police',
  'Chemical hazard at Pithampur industrial area, critical, 80 people affected, block road',
  'send ambulances fire at',
];

export default function CompilerLabPage() {
  const [text, setText] = useState(SAMPLES[0]);
  const [out, setOut] = useState<Out | null>(null);
  const grammar = useApi(() => api.grammar());
  const act = useAction(async (kind: Out['kind']): Promise<Out> => {
    switch (kind) {
      case 'lex': return { kind, data: await api.lex(text) };
      case 'parse': return { kind, data: await api.parse(text) };
      case 'validate': return { kind, data: await api.validate(text) };
      default: return { kind: 'compile', data: await api.compile(text) };
    }
  });
  const go = async (k: Out['kind']) => { const r = await act.run(k); if (r) setOut(r); };

  return (
    <div className="space-y-4">
      <PageHeader title="Compiler Lab" subtitle="Lexical → syntax → semantic analysis → intermediate representation" />
      <Card title="Source command">
        <Textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} aria-label="Compiler input" />
        <div className="mt-2 flex flex-wrap gap-1.5">
          {SAMPLES.map((s, i) => (
            <button key={i} type="button" onClick={() => setText(s)} className="rounded border border-navy-600 px-2 py-0.5 text-[11px] text-slate-400 hover:border-sky-500 hover:text-slate-200">
              Sample {i + 1}{i === SAMPLES.length - 1 ? ' (invalid)' : ''}
            </button>
          ))}
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => go('lex')} loading={act.busy && false} disabled={act.busy}>1. Lex</Button>
          <Button variant="secondary" onClick={() => go('parse')} disabled={act.busy}>2. Parse</Button>
          <Button variant="secondary" onClick={() => go('validate')} disabled={act.busy}>3. Validate</Button>
          <Button onClick={() => go('compile')} loading={act.busy}>4. Compile</Button>
        </div>
        <div className="mt-3"><ErrorBox error={act.error} /></div>
      </Card>

      {out && <Output out={out} source={text} />}

      <Card title="Grammar (BNF)">
        <Async loading={grammar.loading} error={grammar.error} data={grammar.data} onRetry={grammar.reload}>
          {(g) => (
            <div className="grid gap-4 xl:grid-cols-2">
              <div>
                <div className="mb-1 text-xs text-slate-400">Start symbol: <span className="font-mono text-sky-300">{g.start}</span></div>
                <pre className="max-h-[480px] overflow-auto rounded-lg bg-navy-950 p-3 font-mono text-xs leading-relaxed text-emerald-200">{g.bnf}</pre>
              </div>
              <div>
                <div className="mb-1 text-xs uppercase tracking-wide text-slate-400">Token specifications (regular languages)</div>
                <Table head={['Token', 'Pattern', 'Description']}>
                  {g.token_specs.map((t) => (
                    <tr key={t.type}>
                      <Td className="font-mono text-xs text-sky-300">{t.type}</Td>
                      <Td className="max-w-[320px] break-all font-mono text-[11px] text-yellow-200">{t.pattern}</Td>
                      <Td className="text-xs text-slate-400">{t.description}</Td>
                    </tr>
                  ))}
                </Table>
              </div>
            </div>
          )}
        </Async>
      </Card>
    </div>
  );
}

function ValidBadge({ valid }: { valid: boolean }) {
  return valid ? <Badge tone="green">VALID</Badge> : <Badge tone="red">INVALID</Badge>;
}

function Output({ out, source }: { out: Out; source: string }) {
  if (out.kind === 'lex') {
    const d = out.data;
    return (
      <Card title={<>Lexical analysis — {d.tokens.length} tokens</>}>
        <CompilerErrorList errors={d.errors} source={source} />
        <div className="my-3"><TokenStrip tokens={d.tokens} /></div>
        <TokenTable tokens={d.tokens} />
      </Card>
    );
  }
  if (out.kind === 'parse') {
    const d = out.data;
    return (
      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Parse tree" actions={<ValidBadge valid={d.valid} />}>
          <CompilerErrorList errors={d.errors} source={source} />
          <div className="mt-2"><ParseTreeView tree={d.tree} /></div>
        </Card>
        <Card title="Tokens"><TokenTable tokens={d.tokens} /></Card>
      </div>
    );
  }
  if (out.kind === 'validate') {
    const d = out.data;
    return (
      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Semantic validation" actions={<ValidBadge valid={d.valid} />}>
          {d.errors.length === 0 && d.warnings.length === 0 && <div className="text-sm text-emerald-300">No semantic errors or warnings.</div>}
          <CompilerErrorList errors={[...d.errors, ...d.warnings]} source={source} />
        </Card>
        <Card title="IR"><JsonBlock value={d.ir} /></Card>
      </div>
    );
  }
  const d = out.data;
  const errs = [...(d.parse?.errors ?? []), ...(d.semantic?.errors ?? []), ...(d.semantic?.warnings ?? [])];
  return (
    <div className="space-y-4">
      <Card title="Compilation result" actions={<ValidBadge valid={d.valid} />}>
        {errs.length > 0 ? <CompilerErrorList errors={errs} source={source} /> : <div className="text-sm text-emerald-300">Compiled successfully.</div>}
      </Card>
      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Intermediate representation">
          <pre className="overflow-x-auto rounded-lg bg-navy-950 p-3 font-mono text-xs leading-relaxed text-emerald-200">{d.ir_text ?? JSON.stringify(d.ir, null, 2)}</pre>
        </Card>
        <Card title="Structured output"><JsonBlock value={d.structured} /></Card>
        <Card title="Execution plan">
          <Table head={['Step', 'Op', 'Args']}>
            {(d.execution_plan ?? []).map((s) => (
              <tr key={s.step}><Td>{s.step}</Td><Td className="font-mono text-sky-300">{s.op}</Td><Td className="font-mono text-xs">{JSON.stringify(s.args)}</Td></tr>
            ))}
          </Table>
        </Card>
        <Card title="Symbol table">
          <Table head={['Name', 'Kind', 'Value', 'Resolved']}>
            {(d.semantic?.symbol_table ?? []).map((s, i) => (
              <tr key={i}><Td className="font-mono">{s.name}</Td><Td>{s.kind}</Td><Td className="font-mono text-xs">{JSON.stringify(s.value)}</Td>
                <Td>{s.resolved ? <Badge tone="green">YES</Badge> : <Badge tone="red">NO</Badge>}</Td></tr>
            ))}
          </Table>
        </Card>
        <Card title="Parse tree"><ParseTreeView tree={d.parse?.tree} /></Card>
        <Card title="Tokens"><TokenTable tokens={d.tokens} /></Card>
      </div>
    </div>
  );
}
