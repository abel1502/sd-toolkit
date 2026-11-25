/**
 * Tracks a destructive action (e.g. deleting an item) that requires a second click to confirm.
 */
export class TwoStepConfirm<T> {
  /** The item awaiting confirmation, if any. */
  pending: T | null = $state(null);

  #timeout: ReturnType<typeof setTimeout> | undefined;
  #timeoutMs: number;

  constructor({ timeoutMs = 3000 }: { timeoutMs?: number } = {}) {
    this.#timeoutMs = timeoutMs;
  }

  /**
   * @returns Whether the action is confirmed (i.e. this is the second request for the same item).
   */
  request(item: T): boolean {
    clearTimeout(this.#timeout);

    if (this.pending !== item) {
      this.pending = item;
      this.#timeout = setTimeout(() => { this.pending = null; }, this.#timeoutMs);
      return false;
    }

    this.pending = null;
    return true;
  }

  cancel() {
    clearTimeout(this.#timeout);
    this.pending = null;
  }
}

/**
 * Wraps `func` so that it's called at most once per `ms` milliseconds (extra calls are dropped).
 */
export function throttled(func: () => void, ms: number = 1000): () => void {
  let last = 0;

  return () => {
    if (Date.now() - last < ms) return;
    last = Date.now();
    func();
  };
}
