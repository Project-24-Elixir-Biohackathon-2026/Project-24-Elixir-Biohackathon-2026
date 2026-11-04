// Exports every session journal in a directory as one Open WebUI-shaped bundle, for the archive (spec §14):
//   node scripts/export-journals.ts <journals dir> <bundle.json> <live|final>
// The archive runs it in the chat-ui image, in a one-off container. It reads the journals and writes only the bundle.
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { bundleJson, exportJournals } from "../lib/export.ts";

export const USAGE = "usage: node scripts/export-journals.ts <journals dir> <bundle.json> <live|final>";

export async function main(argv: string[]): Promise<number> {
  const [dir, out, mode] = argv;
  if (argv.length !== 3 || (mode !== "live" && mode !== "final")) {
    console.error(USAGE);
    return 2;
  }
  const bundle = await exportJournals(dir, mode);
  await fs.writeFile(out, bundleJson(bundle));
  const deleted = bundle.chats.filter((c) => c.meta.spe_deleted_at !== undefined).length;
  const hidden = bundle.chats.filter((c) => c.archived && c.meta.spe_deleted_at === undefined).length;
  console.log(`${bundle.chats.length} sessions (${hidden} hidden, ${deleted} deleted), ${mode} archive`);
  return 0;
}

if (process.argv[1] !== undefined && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main(process.argv.slice(2)).then(
    (code) => { process.exitCode = code; },
    (err: unknown) => { console.error(err instanceof Error ? err.message : String(err)); process.exitCode = 1; },
  );
}
