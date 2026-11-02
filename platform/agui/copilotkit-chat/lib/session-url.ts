// `?session=<id>`: the open session in the page URL.
import { isSessionId } from "./session-id.ts";

export function sessionFromSearch(search: string): string | null {
  const id = new URLSearchParams(search).get("session");
  return isSessionId(id) ? id : null;
}

// The query string with `session` set to `id`, or removed when `id` is null; other parameters kept.
export function searchWith(search: string, id: string | null): string {
  const params = new URLSearchParams(search);
  if (id === null) params.delete("session");
  else params.set("session", id);
  const text = params.toString();
  return text ? `?${text}` : "";
}
