
// src/main.ts - Entry point for Vite + React + TypeScript (Maestro UI)

import './style.css';
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './app';

const rootElement = document.getElementById('app');
if (!rootElement) throw new Error("#app root element not found");

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);