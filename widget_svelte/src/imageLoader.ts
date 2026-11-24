import type { Experimental } from "./anywidget.svelte";
import { invoke } from "./anywidget.svelte";

export interface LoadedImage {
  /** Identifies the version of the file. See `image_key` on the Python side. */
  key: string;
  url: string;
}

export type ImageRequest = { idx: number, thumbnail?: number } | { path: string, thumbnail?: number };

interface Entry {
  promise: Promise<LoadedImage>;
  url?: string;
}

/**
 * Fetches images from Python (as binary buffers) and caches them as object URLs.
 */
export class ImageLoader {
  #experimental: Experimental;
  #maxEntries: number;
  // Map preserves insertion order, which is used for LRU eviction
  #cache = new Map<string, Entry>();

  constructor(experimental: Experimental, { maxEntries = 24 }: { maxEntries?: number } = {}) {
    this.#experimental = experimental;
    this.#maxEntries = maxEntries;
  }

  /**
   * @param expectedKey If specified, a cached image with a different key is considered stale.
   */
  load(request: ImageRequest, expectedKey?: string): Promise<LoadedImage> {
    const cacheKey = JSON.stringify(request);

    const cached = this.#cache.get(cacheKey);
    if (cached) {
      this.#cache.delete(cacheKey);
      this.#cache.set(cacheKey, cached);

      return cached.promise.then(
        (result) => {
          if (expectedKey === undefined || result.key === expectedKey) {
            return result;
          }
          this.#evict(cacheKey, cached);
          return this.load(request, expectedKey);
        },
        () => {
          // Retry failures
          this.#evict(cacheKey, cached);
          return this.load(request, expectedKey);
        },
      );
    }

    const entry: Entry = {
      promise: invoke<{ key: string, mime: string }>(this.#experimental, "get_image", request)
        .then(([{ key, mime }, [buffer]]) => {
          const url = URL.createObjectURL(new Blob([buffer], { type: mime }));
          entry.url = url;
          return { key, url };
        }),
    };

    entry.promise.catch(() => this.#evict(cacheKey, entry));

    this.#cache.set(cacheKey, entry);
    this.#trim();

    return entry.promise;
  }

  /** Loads an image in the background, ignoring errors. */
  prefetch(request: ImageRequest) {
    this.load(request).catch(() => {});
  }

  dispose() {
    for (const [cacheKey, entry] of [...this.#cache]) {
      this.#evict(cacheKey, entry);
    }
  }

  #evict(cacheKey: string, entry: Entry) {
    if (this.#cache.get(cacheKey) === entry) {
      this.#cache.delete(cacheKey);
    }
    if (entry.url) {
      URL.revokeObjectURL(entry.url);
    }
  }

  #trim() {
    while (this.#cache.size > this.#maxEntries) {
      const [cacheKey, entry] = this.#cache.entries().next().value!;
      this.#evict(cacheKey, entry);
    }
  }
}
