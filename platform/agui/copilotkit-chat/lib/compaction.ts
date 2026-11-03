// The agent marks a compaction with an assistant text message whose id has this prefix; its content is the
// summary the model continues from. The agent rewrites only such plain text messages into its cut point.
export const MARKER_PREFIX = "spe-compaction-";

export function isCompactionMarker<M extends {
  id?: string; role?: string; content?: unknown; toolCalls?: unknown[];
}>(message: M): message is M & { content: string } {
  return message.role === "assistant" && typeof message.id === "string" && message.id.startsWith(MARKER_PREFIX)
    && typeof message.content === "string" && !message.toolCalls?.length;
}
