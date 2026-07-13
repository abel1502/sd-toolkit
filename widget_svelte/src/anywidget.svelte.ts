import { mount, unmount } from "svelte";
import type { Component } from "svelte";
import type { AnyModel, Experimental, AnyWidget } from "@anywidget/types";

export type { AnyModel, Experimental, AnyWidget };

export function defineWidget<T extends Record<string, any>>(Widget: Component<{ model: AnyModel<T>, experimental: Experimental }>): AnyWidget<T> {
  return () => {
    return {
      render({ model, el, experimental }) {
        let app = mount(Widget, {
          target: el,
          props: { model, experimental },
        });
        return () => unmount(app);
      },
    };
  };
}

export function bindTrait<T>({ model, trait, get, set }: {
  model: AnyModel,
  trait: string,
  get: () => T,
  set: (value: T) => void,
}) {
  let syncing = false;

  model.on(`change:${trait}`, () => {
    syncing = true;
    set(model.get(trait));
    syncing = false;
  });

  $effect(() => {
    const value = get();

    if (syncing) return;

    if (model.get(trait) !== value) {
        model.set(trait, value);
        model.save_changes();
    }
  });
}
