import { sveltekit } from "@sveltejs/kit/vite";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    sveltekit(),
    VitePWA({
      registerType: "autoUpdate",
      manifest: false, // we provide our own at /static/manifest.webmanifest
      workbox: { globPatterns: ["**/*.{js,css,html,svg,png}"] },
    }),
  ],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
  test: {
    include: ["src/**/*.test.ts"],
    environment: "node",
    alias: {
      // $app/* só existe no runtime do SvelteKit; os testes de lógica pura
      // não tocam navegação, mas o grafo de imports passa por aqui.
      "$app/navigation": new URL("./src/test/stubs/navigation.ts", import.meta.url).pathname,
      "$app/stores": new URL("./src/test/stubs/stores.ts", import.meta.url).pathname,
    },
  },
});
