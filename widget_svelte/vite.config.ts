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
    outDir: "../src/sd_toolkit/static",
    lib: {
      entry: "./src/index.ts",
      fileName: "index",
      cssFileName: "styles",
      formats: ["es"],
    },
    emptyOutDir: true,
    cssCodeSplit: false,
  },
});
