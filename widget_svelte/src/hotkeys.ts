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

export type Modifier = "shift" | "ctrl" | "alt";

export interface Shortcut {
  /** A `KeyboardEvent.code`, e.g. `"KeyA"`, `"Digit1"` or `"Space"`. */
  code: string;
  /** The exact set of modifiers that must be held. `"ctrl"` also matches the Meta key. */
  modifiers?: Modifier[];
  callback: (event: KeyboardEvent) => void;
  /** By default, shortcuts are ignored while typing into text fields. */
  allowInInputs?: boolean;
  /** By default, auto-repeated key presses (from holding the key down) are ignored. */
  repeat?: boolean;
}

export interface ShortcutHelp {
  /** Each entry is a key combination, e.g. `["Shift", "Space"]`. */
  keys: string[][];
  text: string;
}

/** Converts a single letter or digit to a `KeyboardEvent.code`. */
export function hotkeyCode(hotkey: string): string {
  const upper = hotkey.toUpperCase();
  return /^[0-9]$/.test(upper) ? `Digit${upper}` : `Key${upper}`;
}

function isTextInput(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  if (target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return true;
  if (target instanceof HTMLInputElement) {
    return !["checkbox", "radio", "button", "range", "submit"].includes(target.type);
  }
  return false;
}

/**
 * Finds and runs the shortcut matching the event, if any.
 *
 * @returns Whether a shortcut was triggered.
 */
export function dispatchShortcut(shortcuts: Shortcut[], event: KeyboardEvent): boolean {
  const pressed = {
    shift: event.shiftKey,
    ctrl: event.ctrlKey || event.metaKey,
    alt: event.altKey,
  };
  const inInput = isTextInput(event.target);

  for (const shortcut of shortcuts) {
    if (shortcut.code !== event.code) continue;
    if (inInput && !shortcut.allowInInputs) continue;
    if (event.repeat && !shortcut.repeat) continue;

    const modifiers = shortcut.modifiers ?? [];
    if ((Object.keys(pressed) as Modifier[]).some(m => pressed[m] !== modifiers.includes(m))) continue;

    event.preventDefault();
    event.stopPropagation();
    shortcut.callback(event);
    return true;
  }

  return false;
}
