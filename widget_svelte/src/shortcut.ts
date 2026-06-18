/**
 * Local copy of @svelte-put/shortcut with minor changes (support for event.code-based dispatch instead of event.key).
 */

import { on } from 'svelte/events';
import type { ActionReturn, Action } from 'svelte/action';

/**
 * Additional attributes extended from `svelte-put/shortcut`
 *
 * The ambient types for these extended attributes should be available automatically
 * whenever `svelte-put/shorcut` is imported.
 */
export interface ShortcutAttributes {
  onshortcut?: (event: CustomEvent<ShortcutEventDetail>) => void;
}

/**
 * Supported modifier keys, map to {@link https://developer.mozilla.org/en-US/docs/Web/API/KeyboardEvent | KeyboardEvent}'s
 * {@link https://developer.mozilla.org/en-US/docs/Web/API/KeyboardEvent/altKey | altkey},
 * {@link https://developer.mozilla.org/en-US/docs/Web/API/KeyboardEvent/ctrlKey | ctrlKey},
 * {@link https://developer.mozilla.org/en-US/docs/Web/API/KeyboardEvent/shiftKey | shiftKey},
 * {@link https://developer.mozilla.org/en-US/docs/Web/API/KeyboardEvent/metaKey | metaKey}.
 */
export type ShortcutModifier = 'alt' | 'ctrl' | 'meta' | 'shift' | 'none';

/**
 * Possible variations for modifier definition
 *
 * @example
 *
 * Listen for key (catch-all, modifier or not)
 *
 * ```svelte
 * <script>
 *  import { shortcut } from '@svelte-put/shortcut';
 * </script>
 *
 * <window use:shortcut={{
 *   trigger: {
 *    key: 'k',
 *   },
 * }}
 * />
 * ```
 *
 * @example
 *
 * Listen for key with no modifier
 *
 * ```svelte
 * <script>
 *  import { shortcut } from '@svelte-put/shortcut';
 * </script>
 *
 * <window use:shortcut={{
 *   trigger: {
 *    key: 'k',
 *    modifier: false,  // only trigger when no modifier is pressed
 *   },
 * }}
 * />
 * ```
 *
 * @example
 *
 * Listen for key with a single modifier
 *
 * ```svelte
 * <script>
 *  import { shortcut } from '@svelte-put/shortcut';
 * </script>
 *
 * <window use:shortcut={{
 *   trigger: {
 *    key: 'k',
 *    modifier: 'ctrl',
 *   },
 * }}
 * />
 * ```
 *
 * @example
 *
 * Listen for key with one of many modifiers (or)
 *
 * ```svelte
 * <script>
 *  import { shortcut } from '@svelte-put/shortcut';
 * </script>
 *
 * <window use:shortcut={{
 *   trigger: {
 *    key: 'k',
 *    modifier: ['ctrl', 'meta'],
 *   },
 * }}
 * />
 * ```
 *
 * @example
 *
 * Listen for key with a combination of multiple modifiers (and)
 *
 * ```svelte
 * <script>
 *  import { shortcut } from '@svelte-put/shortcut';
 * </script>
 *
 * <window use:shortcut={{
 *   trigger: {
 *    key: 'k',
 *    modifier: [['ctrl', 'shift']],
 *   },
 * }}
 * />
 * ```
 *
 * @example
 *
 * A mix of the 3 previous examples
 *
 * ```svelte
 * <script>
 *  import { shortcut } from '@svelte-put/shortcut';
 * </script>
 *
 * <window use:shortcut={{
 *   trigger: {
 *    key: 'k',
 *    modifier: [
 *      ['ctrl', 'shift'], // ctrl and shift
 *                         // or
 *      ['meta'],          // meta
 *    ],
 *   },
 * }}
 * />
 * ```
 */
export type ShortcutModifierDefinition =
  | null
  | false
  | ShortcutModifier
  | (ShortcutModifier | ShortcutModifier[])[];

/**
 * A definition of a shortcut trigger
 */
export type ShortcutTrigger = {
  enabled?: boolean;
  modifier?: ShortcutModifierDefinition;
  id?: string;
  callback?: (detail: ShortcutEventDetail) => void;
  preventDefault?: boolean;
} & (
  { key: string, code?: never } |
  { key?: never, code: string }
);

/** svelte action parameter to config behavior of `shortcut` */
export interface ShortcutParameter {
  enabled?: boolean;
  trigger: Array<ShortcutTrigger> | ShortcutTrigger;
  type?: 'keydown' | 'keyup';
}

/**
 * `detail` payload for 'shortcut' {@link https://developer.mozilla.org/en-US/docs/Web/API/CustomEvent | CustomEvent }
 */
export interface ShortcutEventDetail {
  node: HTMLElement;
  trigger: ShortcutTrigger;
  originalEvent: KeyboardEvent;
}

export type ShortcutAction = Action<HTMLElement, ShortcutParameter, ShortcutAttributes>;
export type ShortcutActionReturn = ActionReturn<ShortcutParameter, ShortcutAttributes>;

function mapModifierToBitMask(def: ShortcutModifier): number {
  switch (def) {
    case 'ctrl':
      return 0b1000;
    case 'shift':
      return 0b0100;
    case 'alt':
      return 0b0010;
    case 'meta':
      return 0b0001;
    case 'none':
      return 0b0000;
  }
}

/**
 * Listen for keyboard event and trigger `shortcut` {@link https://developer.mozilla.org/en-US/docs/Web/API/CustomEvent | CustomEvent }
 *
 * @example Typical usage
 *
 * ```svelte
 * <script lang="ts">
 *  import { shortcut, type ShortcutEventDetail } from '@svelte-put/shortcut';
 *
 *  let commandPalette = false;
 *
 *  function onOpenCommandPalette() {
 *    commandPalette = true;
 *  }
 *  function onCloseCommandPalette() {
 *    commandPalette = false;
 *  }
 *
 *  function doSomethingElse(details: ShortcutEventDetail) {
 *    console.log('Action was placed on:', details.node);
 *    console.log('Trigger:', details.trigger);
 *  }
 *
 *  function onShortcut(event: CustomEvent<ShortcutEventDetail>) {
 *    if (event.detail.trigger.id === 'do-something-else') {
 *      console.log('Same as doSomethingElse()');
 *      // be careful here doSomethingElse would have been called too
 *   }
 * }
 * </script>
 *
 * <svelte:window
 *   use:shortcut={{
 *     trigger: [
 *       {
 *         key: 'k',
 *
 *         // trigger if either ctrl or meta is pressed
 *         modifier: ['ctrl', 'meta'],
 *
 *         callback: onOpenCommandPalette,
 *         preventDefault: true,
 *       },
 *       {
 *         key: 'Escape',
 *         modifier: false,
 *
 *         callback: onCloseCommandPalette,
 *
 *         enabled: commandPalette,
 *         preventDefault: true,
 *       },
 *      {
 *         key: 'k',
 *
 *         // trigger if both ctrl & shift are pressed
 *         modifier: [['ctrl', 'shift']],
 *         id: 'do-something-else',
 *         callback: doSomethingElse,
 *      },
 *     ],
 *   }}
 *   onshortcut={onShortcut}
 * />
 * ```
 */
export function shortcut(
  node: HTMLElement,
  param: ShortcutParameter,
): ShortcutActionReturn {
  let { enabled = true, trigger, type = 'keydown' } = param;

  function handler(event: KeyboardEvent) {
    const normalizedTriggers = Array.isArray(trigger) ? trigger : [trigger];
    const modifierMask = [event.metaKey, event.altKey, event.shiftKey, event.ctrlKey].reduce(
      (acc, value, index) => {
        if (value) {
          return acc | (1 << index);
        }
        return acc;
      },
      0b0000,
    );

    for (const trigger of normalizedTriggers) {
      const mergedTrigger = {
        preventDefault: false,
        enabled: true,
        ...trigger,
      };

      const {
        modifier,
        key = null,
        code = null,
        callback,
        preventDefault,
        enabled: triggerEnabled,
      } = mergedTrigger;

      if (triggerEnabled) {
        if (key !== null && event.key !== key) continue;
        if (code !== null && event.code !== code) continue;

        if (modifier === null || modifier === false) {
          if (modifierMask !== 0b0000) continue;
        } else if (
          modifier !== undefined &&
          (modifier as any)?.[0]?.length > 0
        ) {
          const orDefs = Array.isArray(modifier) ? modifier : [modifier];
          let modified = false;

          for (const orDef of orDefs) {
            const mask = (Array.isArray(orDef) ? orDef : [orDef]).reduce(
              (acc, def) => acc | mapModifierToBitMask(def),
              0b0000,
            );

            if (mask === modifierMask) {
              modified = true;
              break;
            }
          }

          if (!modified) continue;
        }

        if (preventDefault) event.preventDefault();

        const detail: ShortcutEventDetail = {
          node,
          trigger: mergedTrigger,
          originalEvent: event,
        };

        node.dispatchEvent(new CustomEvent('shortcut', { detail }));
        callback?.(detail);
      }
    }
  }

  let off: undefined | (() => void);

  if (enabled) {
    off = on(node, type, handler);
  }

  return {
    update: (update) => {
      const { enabled: newEnabled = true, type: newType = 'keydown' } = update;

      if (enabled && (!newEnabled || type !== newType)) {
        off?.();
      } else if (!enabled && newEnabled) {
        off = on(node, newType, handler);
      }

      enabled = newEnabled;
      type = newType;
      trigger = update.trigger;
    },
    destroy: () => {
      off?.();
    },
  };
}
