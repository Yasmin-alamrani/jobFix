import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import Dashboard from './Dashboard';
import { SAMPLE } from './sample';
import './styles.css';

/* Preview the dashboard with sample data -- no API key, no spend. */
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <div className="shell">
      <header className="masthead">
        <h1>jobFix</h1>
        <p>
          Sample report. Senior Backend Engineer, fintech — showing how a real result renders.
        </p>
      </header>
      <Dashboard result={SAMPLE} />
    </div>
  </StrictMode>,
);
