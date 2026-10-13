import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// In `npm run dev` the browser calls /api/... on this same dev server, and Vite
// forwards it to VITE_API_URL (the Colab/ngrok backend). So the site also works
// when opened from a friend's computer through a tunnel: no CORS, no ngrok page.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = (env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");
  return {
    plugins: [react()],
    server: {
      port: 5173,
      allowedHosts: true, // accept the tunnel's address (e.g. *.trycloudflare.com)
      proxy: {
        "/api": {
          target,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ""),
          headers: { "ngrok-skip-browser-warning": "1" },
        },
      },
    },
  };
});
