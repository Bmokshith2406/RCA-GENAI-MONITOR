import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/",

  plugins: [
    react(),
  ],

  server: {
    host: "localhost",
    port: 5173,

    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        secure: false,
        ws: true,
        timeout: 30_000,
        rewrite: path => path.replace(/^\/api/, "/api"),
      },
    },
  },
});
