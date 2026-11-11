// The page fetches the session list from several places at once (first load, metadata changes, a New
// chat's title, every session's run end), and their answers can arrive out of order. A list that started
// before another but arrives after it is older: applying it would undo what the newer one showed, and
// mark a session the newer one listed as having left the list (lib/live-sessions.ts, `gone`, is sticky).
// So each fetch is stamped with the order it started in, and only a list newer than the last one applied
// is applied. Pure: no React, no clock.
import type { FetchList } from "./reconcile.ts";

export class ListOrder {
  private started = 0;
  private applied = 0;
  private readonly stamps = new WeakMap<object, number>();

  /** Runs `fetch`, stamping the list it answers (`listOf` picks it out) with when the fetch started. */
  async track<R>(fetch: () => Promise<R>, listOf: (result: R) => object): Promise<R> {
    const stamp = ++this.started;
    const result = await fetch();
    this.stamps.set(listOf(result), stamp);
    return result;
  }

  /** `fetchList`, with every list it answers stamped: for reconcile() and waitListed(). */
  wrap(fetchList: FetchList): FetchList {
    return () => this.track(fetchList, (r) => r.list);
  }

  /** True if `list` should be applied: no fetch started after it has been applied already. It then
   *  becomes the last one applied. A list this did not stamp is always applied. */
  accept(list: object): boolean {
    const stamp = this.stamps.get(list);
    if (stamp === undefined) return true;
    if (stamp < this.applied) return false;
    this.applied = stamp;
    return true;
  }
}
