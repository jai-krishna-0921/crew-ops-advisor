import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Pin the workspace root so Turbopack does not walk up past the repository
  // looking for a lockfile.
  turbopack: {
    root: path.join(__dirname),
  },
  // A self-contained server bundle for the container image: nginx fronts it
  // and FastAPI in one process each, so this only needs node and its own
  // node_modules, not the pnpm workspace that built it.
  output: "standalone",
};

export default nextConfig;
