// A run's error as the error bar shows it (spec §6 *Errors*): every session's holder reports its own agent's
// errors, open or not, so one from a session that is not open names it first. Pure.

/** `message` for the open session; else `“<title>”: <message>`, "New chat" for a session with no title yet. */
export function runErrorText(title: string | null, message: string, open: boolean): string {
  return open ? message : `“${title || "New chat"}”: ${message}`;
}
