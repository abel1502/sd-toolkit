export interface TagGroupInfo {
  tags: TagInfo[];
  level: number;
  hotkey: string | null;
}

export interface TagInfo {
  tag: string;
  path: string[];
  present: boolean;
}

export interface ToggleTagEvent {
  path: string[];
  present: boolean;
}

export interface ToggleGroupEvent {
  idx: number;
  present: boolean;
}

export type SwitchImageEvent = number;

