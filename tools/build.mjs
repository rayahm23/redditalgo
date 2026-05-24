import fs from "node:fs";
import esbuild from "esbuild";

const watch = process.argv.includes("--watch");
const minify = process.argv.includes("--minify");

const serverOptions = {
  bundle: true,
  entryPoints: ["src/server/index.ts"],
  format: "cjs",
  logLevel: "info",
  minify,
  outdir: "dist/server",
  platform: "node",
  sourcemap: true,
  target: "node22",
};

fs.mkdirSync("dist", { recursive: true });

if (watch) {
  const context = await esbuild.context(serverOptions);
  await context.watch();
  console.log("Watching Devvit server sources...");
} else {
  await esbuild.build(serverOptions);
}
