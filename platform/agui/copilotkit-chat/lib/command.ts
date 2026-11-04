// The chat's one command (spec §15, *What counts as a command*): a run whose only new message is a user message
// whose string content, trimmed, is /compact or /compact followed by whitespace and a focus. Case matters; there
// is no escape. Browser-safe: no Node imports.
import type { Message } from "@ag-ui/client";

export type Command = { name: "compact"; focus: string | null };
export type CommandField = Command & { message_id: string };

const COMPACT = /^\/compact(?:\s+([\s\S]*))?$/;

export function parseCommand(content: unknown): Command | null {
  if (typeof content !== "string") return null;
  const match = COMPACT.exec(content.trim());
  if (!match) return null;
  const focus = (match[1] ?? "").trim();
  return { name: "compact", focus: focus === "" ? null : focus };
}

export function commandOf(newMessages: Message[]): CommandField | null {
  if (newMessages.length !== 1 || newMessages[0].role !== "user") return null;
  const command = parseCommand(newMessages[0].content);
  return command && { ...command, message_id: newMessages[0].id };
}

export function sameCommand(a: Command, b: Command): boolean {
  return a.name === b.name && a.focus === b.focus;
}
