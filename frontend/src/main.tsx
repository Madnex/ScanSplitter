import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
// eslint-disable-next-line react-refresh/only-export-components
const App = lazy(() => import('./App.tsx'))
// eslint-disable-next-line react-refresh/only-export-components
const BenchmarkPage = lazy(() => import('./components/BenchmarkPage.tsx').then(m => ({ default: m.BenchmarkPage })))

const isBenchmarkPage = window.location.pathname.replace(/\/+$/, '') === '/benchmark'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Suspense fallback={<p className="p-6" role="status">Loading ScanSplitter…</p>}>{isBenchmarkPage ? <BenchmarkPage /> : <App />}</Suspense>
  </StrictMode>,
)
