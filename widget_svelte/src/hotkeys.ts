import { writable, type Writable } from "svelte/store";

/**
 * The widget (identified by its scope) that currently has keyboard shortcuts enabled.
 *
 * Stored on `globalThis` because anywidget loads a separate copy of the frontend
 * module for each widget, so module-level state is not shared between instances.
 */

const KEY = Symbol.for("sd_toolkit.tagger.enabled_hotkeys");

type HotkeysGlobal = typeof globalThis & Record<symbol, Writable<string | null> | undefined>;

export const enabledHotkeys: Writable<string | null> =
  ((globalThis as HotkeysGlobal)[KEY] ??= writable<string | null>(null));
