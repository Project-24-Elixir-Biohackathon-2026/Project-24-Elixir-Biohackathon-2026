// Runs once when the Next.js server starts (also in the standalone server.js).
export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  const { installShutdown } = await import("./lib/shutdown.ts");
  installShutdown();
}
