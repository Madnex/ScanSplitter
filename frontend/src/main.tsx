import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { BenchmarkPage } from './components/BenchmarkPage.tsx'

const isBenchmarkPage = window.location.pathname.replace(/\/+$/, '') === '/benchmark'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {isBenchmarkPage ? <BenchmarkPage /> : <App />}
  </StrictMode>,
)
