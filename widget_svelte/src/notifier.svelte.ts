export type NoticeKind = "pending" | "success" | "error";

export interface Notice {
  text: string;
  kind: NoticeKind;
};

/**
 * A short-lived status message shown over the image (e.g. why an action failed).
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
}

export type ActionState = "idle" | "pending" | "success" | "error";

/**
 * Tracks an asynchronous action for subtle feedback on its button (see the `status` of `Button` and `ImageButton`):
 * a spinner while it's pending, then a short green (or red) flash. E.g. for opening an image in an external
 * application, which otherwise gives no feedback, since the application might not even come to the front.
 */
export class ActionStatus {
  state: ActionState = $state("idle");

  #notifier: Notifier | undefined;
  #timeout: ReturnType<typeof setTimeout> | undefined;

  /**
   * @param notifier If specified, errors are shown in it (they're only logged otherwise).
   */
  constructor(notifier?: Notifier) {
    this.#notifier = notifier;
  }

  /**
   * @returns The result of the promise, or `undefined` if it failed.
   */
  async run<T>(promise: Promise<T>): Promise<T | undefined> {
    clearTimeout(this.#timeout);
    this.state = "pending";

    try {
      const result = await promise;
      this.#finish("success", 900);
      return result;
    } catch (e) {
      console.error(e);
      this.#notifier?.show(String(e), "error");
      this.#finish("error", 1500);
      return undefined;
    }
  }

  #finish(state: ActionState, ms: number) {
    this.state = state;
    this.#timeout = setTimeout(() => { this.state = "idle"; }, ms);
  }
}
