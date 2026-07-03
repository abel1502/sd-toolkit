export interface TagGroupInfo {
  tags: TagInfo[];
  level: number;
  hotkey: string | null;
};

export interface TagInfo {
  tag: string;
  path: string[];
  path_str: string;
  present: boolean;
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
