// `defineConfig` is a helper from drizzle-kit (the CLI/migration toolkit that
// ships alongside the Drizzle ORM). It gives us type-checking and editor
// autocomplete for the config object below.
import { defineConfig } from "drizzle-kit";
// Importing "dotenv/config" runs dotenv immediately as a side effect: it reads
// a `.env` file and loads its key/value pairs into `process.env`. We need this
// so that `process.env.DATABASE_URL` is populated when drizzle-kit runs.
import "dotenv/config";

// This is the configuration drizzle-kit reads when you run commands like
// `db:push` (apply schema to the DB) or `db:generate` (create migration files).
// `export default` makes this config the module's main export.
export default defineConfig({
  // Path to the file that defines our tables/columns. drizzle-kit reads this to
  // know the desired shape of the database.
  schema: "./src/db/schema.ts",
  // Folder where drizzle-kit writes generated SQL migration files.
  out: "./drizzle",
  // Which SQL flavor we target. "postgresql" tells drizzle-kit to emit Postgres
  // syntax (matching the postgres-js client used at runtime).
  dialect: "postgresql",
  // How drizzle-kit connects to the database.
  dbCredentials: {
    // The Postgres connection string. `?? ""` falls back to an empty string when
    // DATABASE_URL is missing, so the config object is always well-formed (the
    // command itself will fail clearly later if the URL is actually empty).
    url: process.env.DATABASE_URL ?? "",
  },
  // Print detailed output of the SQL statements drizzle-kit plans to run.
  verbose: true,
  // Ask for confirmation before running potentially destructive changes, and be
  // stricter about schema diffs — safer for real databases.
  strict: true,
});
