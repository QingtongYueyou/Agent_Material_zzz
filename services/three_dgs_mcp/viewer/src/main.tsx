import React from "react";
import ReactDOM from "react-dom/client";
import { ViewerApp } from "./ViewerApp";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <ViewerApp />
  </React.StrictMode>,
);
