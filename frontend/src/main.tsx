import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { UnitProvider } from "./units";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <UnitProvider>
      <App />
    </UnitProvider>
  </React.StrictMode>,
);
