import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import AppErrorBoundary from "./components/common/AppErrorBoundary";
import "./styles/index.css";
import { initTheme } from "./services/theme";
import { registerServiceWorker } from "./services/pwa";

initTheme();
registerServiceWorker();

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <AppErrorBoundary>
      <App />
    </AppErrorBoundary>
  </StrictMode>,
);
