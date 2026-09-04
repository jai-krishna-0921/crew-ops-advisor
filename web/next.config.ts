import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Pin the workspace root so Turbopack does not walk up past the repository
  // looking for a lockfile.
  turbopack: {
    root: path.join(__dirname),
  },
};

export default nextConfig;
