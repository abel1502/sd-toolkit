import { defineConfig } from "rolldown";
import svelte from "rollup-plugin-svelte";

export default defineConfig({
  input: "./src/index.ts",
  output: {
    dir: "../src/sd_toolkit/static",
  },
  plugins: [svelte({ compilerOptions: { runes: true } })],
});
