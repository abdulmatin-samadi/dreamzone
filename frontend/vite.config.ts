import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const target = loadEnv(mode, process.cwd(), "").VITE_PROXY_TARGET || "http://localhost:8000";
  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      proxy: { "/api": target, "/media": target },
    },
  };
});
