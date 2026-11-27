export type NoticeKind = "pending" | "success" | "error";

export interface Notice {
  text: string;
  kind: NoticeKind;
};

/**
 * A short-lived status message, e.g. confirming that an image was opened in an external application
 * (which otherwise gives no feedback, since the application might not even come to the front).
 */
export class Notifier {
  current: Notice | null = $state(null);

  #timeout: ReturnType<typeof setTimeout> | undefined;

  /**
   * @param ms How long to show the notice for. `0` means until the next notice.
   */
  show(text: string, kind: NoticeKind, ms: number = kind == "error" ? 6000 : 3000) {
    clearTimeout(this.#timeout);
    const notice = { text, kind };
    this.current = notice;

    if (ms > 0) {
      this.#timeout = setTimeout(() => {
        if (this.current === notice) this.current = null;
      }, ms);
    }
  }

  /**
   * Shows `pending` until `promise` settles, then `done` or the error.
   * @returns The result of the promise, or `undefined` if it failed.
   */
  async track<T>(promise: Promise<T>, pending: string, done: string): Promise<T | undefined> {
    this.show(pending, "pending", 0);
    try {
      const result = await promise;
      this.show(done, "success");
      return result;
    } catch (e) {
      this.show(String(e), "error");
      return undefined;
    }
  }
}
