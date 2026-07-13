import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import tailwindcss from "@tailwindcss/vite";
import { resolve } from "node:path";

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
    outDir: resolve(__dirname, "../src/sd_toolkit/widgets/static"),
    lib: {
      entry: {
        tagger: resolve(__dirname, "./src/_tagger.ts"),
      },
      fileName: (_format, entryName) => `${entryName}.js`,
      cssFileName: "styles",
      formats: ["es"],
    },
    emptyOutDir: true,
    cssCodeSplit: false,
  },
});
