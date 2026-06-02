import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/viewer/",
  plugins: [react()],
  server: {
    proxy: {
      "/viewer": "http://127.0.0.1:8080",
      "/static": "http://127.0.0.1:8080"
    }
  }
});
