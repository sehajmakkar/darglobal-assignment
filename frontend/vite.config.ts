import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev: `npm run dev` on :5173 proxies /api to the FastAPI server on :7860.
// Build: static files in dist/, served by FastAPI at "/" (single container, D-012).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: { "/api": "http://localhost:7860" } },
  build: { outDir: "dist", sourcemap: false },
});
