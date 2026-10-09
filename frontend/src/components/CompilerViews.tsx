import clsx from 'clsx';
import { ChevronDown, ChevronRight, Lightbulb } from 'lucide-react';
import { useState } from 'react';
import type { CompilerError, ParseNode, Token } from '../api/types';
import { Badge, Empty, Table, Td } from './ui';
import { stringify } from '../utils/format';

const TOKEN_TONES: Record<string, string> = {
  INCIDENT_TYPE: 'text-red-300', LOCATION: 'text-emerald-300', NUMBER: 'text-yellow-300', RESOURCE: 'text-sky-300',
  SEVERITY: 'text-orange-300', TIME: 'text-teal-300', PERSON_COUNT: 'text-amber-300', ACTION: 'text-violet-300',
  QUANTITY: 'text-yellow-200', HAZARD: 'text-rose-300', CONDITION: 'text-pink-300', PREPOSITION: 'text-slate-400',
  CONNECTOR: 'text-slate-400', WORD: 'text-slate-500', PUNCT: 'text-slate-600', EOF: 'text-slate-600',
};

export function TokenTable({ tokens }: { tokens: Token[] }) {
  if (!tokens.length) return <Empty>No tokens.</Empty>;
  return (
    <Table head={['#', 'Type', 'Lexeme', 'Value', 'Pos', 'Len']}>
      {tokens.map((t, i) => (
        <tr key={i}>
          <Td className="text-slate-500">{i}</Td>
          <Td><span className={clsx('font-mono text-xs font-semibold', TOKEN_TONES[t.type] ?? 'text-slate-300')}>{t.type}</span></Td>
          <Td className="font-mono">{t.lexeme}</Td>
          <Td className="font-mono text-xs text-slate-300">{stringify(t.value)}</Td>
          <Td className="tabular-nums text-slate-400">{t.position}</Td>
          <Td className="tabular-nums text-slate-400">{t.length}</Td>
        </tr>
      ))}
    </Table>
  );
}

/** Highlights each token inline in the source text. */
export function TokenStrip({ tokens }: { tokens: Token[] }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {tokens.filter((t) => t.type !== 'EOF').map((t, i) => (
        <span key={i} className="rounded border border-navy-600 bg-navy-900 px-1.5 py-0.5 font-mono text-xs" title={`${t.type} @${t.position}`}>
          <span className={TOKEN_TONES[t.type] ?? 'text-slate-300'}>{t.lexeme}</span>
          <span className="ml-1 text-[9px] uppercase text-slate-500">{t.type}</span>
        </span>
      ))}
    </div>
  );
}

function TreeNode({ node, depth }: { node: ParseNode; depth: number }) {
  const [open, setOpen] = useState(depth < 4);
  const hasKids = node.children && node.children.length > 0;
  const terminal = node.kind === 'terminal';
  return (
    <li>
      <div className="group flex items-start gap-1 py-0.5">
        <button
          type="button"
          onClick={() => setOpen(!open)}
          className={clsx('mt-0.5 h-4 w-4 shrink-0 text-slate-500', !hasKids && 'invisible')}
          aria-label={open ? 'Collapse' : 'Expand'}
        >
          {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </button>
        <span className={clsx('font-mono text-xs', terminal ? 'rounded bg-emerald-500/10 px-1 text-emerald-300' : 'font-semibold text-sky-300')}>
          {node.label}
        </span>
        {node.value !== undefined && node.value !== null && node.value !== '' && (
          <span className="font-mono text-xs text-yellow-200">= {String(node.value)}</span>
        )}
        {node.meaning && <span className="text-xs text-slate-500">— {node.meaning}</span>}
      </div>
      {hasKids && open && (
        <ul className="ml-4 border-l border-navy-600 pl-2">
          {node.children.map((c, i) => <TreeNode key={c.id ?? i} node={c} depth={depth + 1} />)}
        </ul>
      )}
    </li>
  );
}

export function ParseTreeView({ tree }: { tree: ParseNode | null | undefined }) {
  if (!tree) return <Empty>No parse tree (parsing failed or not run).</Empty>;
  return (
    <ul className="overflow-x-auto text-sm">
      <TreeNode node={tree} depth={0} />
    </ul>
  );
}

export function CompilerErrorList({ errors, source }: { errors: CompilerError[]; source?: string }) {
  if (!errors.length) return null;
  return (
    <ul className="space-y-2">
      {errors.map((e, i) => (
        <li key={i} className={clsx('rounded-lg border px-3 py-2 text-sm',
          e.severity === 'WARNING' ? 'border-yellow-500/40 bg-yellow-500/10' : 'border-red-500/40 bg-red-500/10')}>
          <div className="flex flex-wrap items-center gap-2">
            <Badge value={e.severity} />
            <Badge tone="purple">{e.phase}</Badge>
            {e.position !== undefined && e.position !== null && <span className="text-xs text-slate-400">at position {e.position}</span>}
          </div>
          <div className="mt-1 text-slate-100">{e.message}</div>
          {source && e.position !== undefined && e.position !== null && (
            <pre className="mt-1 overflow-x-auto font-mono text-xs text-slate-400">
              {source}{'\n'}{' '.repeat(Math.max(0, Math.min(e.position, source.length)))}^
            </pre>
          )}
          {(e.found || (e.expected && e.expected.length > 0)) && (
            <div className="mt-1 text-xs text-slate-300">
              {e.found && <>Found <code className="text-red-300">{e.found}</code>. </>}
              {e.expected && e.expected.length > 0 && <>Expected: <code className="text-emerald-300">{e.expected.join(' | ')}</code></>}
            </div>
          )}
          {e.suggestion && (
            <div className="mt-1 flex items-start gap-1 text-xs text-sky-200">
              <Lightbulb className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {e.suggestion}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

export function JsonBlock({ value, className }: { value: unknown; className?: string }) {
  return (
    <pre className={clsx('max-h-96 overflow-auto rounded-lg bg-navy-950 p-3 font-mono text-xs text-slate-300', className)}>
      {typeof value === 'string' ? value : JSON.stringify(value, null, 2)}
    </pre>
  );
}
