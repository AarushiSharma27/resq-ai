import { Link } from 'react-router-dom';

export default function NotFoundPage() {
  return (
    <div className="py-20 text-center">
      <div className="text-5xl font-bold text-slate-600">404</div>
      <p className="mt-2 text-slate-400">This page does not exist.</p>
      <Link to="/" className="mt-4 inline-block text-sky-400 hover:underline">Back to dashboard</Link>
    </div>
  );
}
