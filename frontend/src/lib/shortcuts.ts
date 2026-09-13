export interface ShortcutGroup {
  name: string;
  shortcuts: Shortcut[];
}

export interface Shortcut {
  keys: string[];
  description: string;
}

export const KEYBOARD_SHORTCUTS: ShortcutGroup[] = [
  {
    name: "Canvas",
    shortcuts: [
      { keys: ["Delete", "/", "Backspace"], description: "Delete selected boxes" },
      { keys: ["⌘ / Ctrl", "Z"], description: "Undo box deletion" },
    ],
  },
  {
    name: "Gallery",
    shortcuts: [
      { keys: ["Esc"], description: "Close lightbox" },
      { keys: ["←"], description: "Previous image" },
      { keys: ["→"], description: "Next image" },
      { keys: ["R"], description: "Rotate right 90°" },
      { keys: ["Shift", "R"], description: "Rotate left 90°" },
    ],
  },
  {
    name: "Navigation",
    shortcuts: [
      { keys: ["Alt", "←"], description: "Previous scan" },
      { keys: ["Alt", "→"], description: "Next scan" },
      { keys: ["?"], description: "Show shortcuts" },
    ],
  },
];
