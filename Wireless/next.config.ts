import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Bundle the SQL migration files with the admin db-setup function, so it can
  // apply them at runtime inside Vercel (where the database secret lives).
  outputFileTracingIncludes: {
    "/api/admin/db-setup": ["./drizzle/**"],
  },
};

export default nextConfig;
