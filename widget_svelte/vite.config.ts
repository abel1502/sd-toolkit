import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [
    svelte({
      compilerOptions: {
        runes: true,
      },
    }),
    tailwindcss(),
  ],
  build: {
    lib: {
      entry: "./src/index.ts",
      fileName: "index",
      cssFileName: "styles",
      formats: ["es"],
    },
    outDir: "../src/sd_toolkit/static",
    emptyOutDir: true,
    cssCodeSplit: false,
  },
});
