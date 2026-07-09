import { spawnSync } from "node:child_process";
import { rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const nextBin = join(__dirname, "..", "node_modules", "next", "dist", "bin", "next");
const appDir = join(__dirname, "..");

for (const generatedDir of [join(appDir, ".next"), join(appDir, "out")]) {
  rmSync(generatedDir, { recursive: true, force: true });
}

const result = spawnSync(process.execPath, [nextBin, "build"], {
  stdio: "inherit",
  env: {
    ...process.env,
    NEXT_OUTPUT_MODE: "export",
    NEXT_PUBLIC_API_BASE_URL: ""
  }
});

process.exit(result.status ?? 1);
