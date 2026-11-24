import { mount, unmount } from "svelte";
import type { Component } from "svelte";
import type { AnyModel, Experimental, AnyWidget } from "@anywidget/types";

export type { AnyModel, Experimental, AnyWidget };

export type WidgetProps<T extends Record<string, any>> = {
  model: AnyModel<T>,
  experimental: Experimental,
};

/**
 * Defines the widget module. All the widgets share a single bundle, so the component
 * to render is picked based on the `_component` trait.
 */
export function defineWidget(components: Record<string, Component<WidgetProps<any>>>): AnyWidget<any> {
  return () => {
    return {
      render({ model, el, experimental }) {
        const name: string = model.get("_component");
        const Widget = components[name];

        if (!Widget) {
          el.textContent = `Unknown widget component: ${JSON.stringify(name)}`;
          return;
        }

        let app = mount(Widget, {
          target: el,
          props: { model, experimental },
        });
        return () => unmount(app);
      },
    };
  };
}

/**
 * A reactive view of a trait. Setting `.value` syncs the change back to Python.
 *
 * Must be called during component initialization.
 */
export function useTrait<T extends Record<string, any>, K extends keyof T & string>(
  model: AnyModel<T>,
  trait: K,
): { value: T[K] } {
  // Raw, since traits are replaced as a whole anyway
  let value: T[K] = $state.raw(model.get(trait));

  const handler = () => { value = model.get(trait); };
  model.on(`change:${trait}`, handler);
  $effect(() => () => model.off(`change:${trait}`, handler));

  return {
    get value() {
      return value;
    },
    set value(newValue: T[K]) {
      value = newValue;
      model.set(trait, newValue);
      model.save_changes();
    },
  };
}

/**
 * Sends a custom message (handled by `Messages` on the Python side).
 */
export function sendMessage(model: AnyModel<any>, type: string, content: Record<string, any> = {}) {
  model.send({
    kind: "custom",
    type,
    ...content,
  });
}

/**
 * Invokes a Python command (see `command` in `widgets/base.py`), turning error responses into exceptions.
 */
export async function invoke<T>(
  experimental: Experimental,
  name: string,
  msg: any,
  buffers: DataView[] = [],
): Promise<[T, DataView[]]> {
  const [response, responseBuffers] = await experimental.invoke<any>(name, msg, { buffers });

  if (response !== null && typeof response === "object" && "__error__" in response) {
    throw new Error(response.__error__);
  }

  return [response as T, responseBuffers];
}
