import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Browser /api/... likhega, Vite use backend (127.0.0.1:8000) par bhej dega.
// Isse CORS ki dikkat nahi aati aur backend mein kuch badalna nahi padta.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});