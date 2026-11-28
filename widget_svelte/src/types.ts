import type { Component } from "svelte";
import type { ActionState } from "./notifier.svelte";

export interface TagGroupInfo {
  tags: TagInfo[];
  level: number;
  hotkey: string | null;
};

export interface TagInfo {
  tag: string;
  path: string[];
  path_str: string;
};

export interface TagDisplay {
  path: string[];
  path_str: string;
  tag: string;
  category: string;
  origin: string;
  confidence: number;
  is_trigger: boolean;
};

export interface InfoItem {
  key: string;
  value: string;
};

export interface MarkStyle {
  label: string;
  color: string;
};

export interface ImageButton {
  icon: Component<any>;
  title: string;
  onclick: () => unknown;
  /** The state of the button's action (see `ActionStatus`). */
  status?: ActionState;
};

export interface ToggleTagEvent {
  path: string[];
  present: boolean;
};

export interface ToggleGroupEvent {
  idx: number;
  present: boolean;
};

export interface SwitchImageEvent {
  idx: number;
};

/** The traits of `ImageViewerWidget`. */
export interface ViewerTraits {
  _component: string;
  image_idx: number;
  image_count: number;
  image_path: string;
  image_key: string;
  image_info: InfoItem[];
  image_marks: number[];
  mark_styles: (MarkStyle | null)[];
  has_done_screen: boolean;
  can_edit_copy: boolean;
};

/** The image currently shown by the `Viewer`. */
export interface ViewerImage {
  idx: number;
  url: string | null;
  /** The key of the loaded version of the image (may lag behind the `image_key` trait while loading). */
  key: string;
};
