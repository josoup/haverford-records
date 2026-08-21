import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";

// Single-file output: the dashboard has to be openable as one self-contained
// page (emailed, dropped on a laptop in a coach's office) with no server.
export default defineConfig({
  plugins: [react(), viteSingleFile()],
  build: { outDir: "dist", assetsInlineLimit: 100000000, cssCodeSplit: false },
});
