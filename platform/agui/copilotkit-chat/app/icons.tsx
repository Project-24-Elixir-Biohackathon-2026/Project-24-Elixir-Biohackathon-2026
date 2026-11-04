// Inline SVG icons (24×24 outline, stroke 1.5, currentColor), as Open WebUI's sidebar draws them.
// Most are Heroicons v2 outline; Pin, PinSlash, Tag and SidebarToggle are Open WebUI's own drawings.
// Decorative: the button or item that holds one carries the label.
import type { ReactNode } from "react";

function Icon({ children, className, strokeWidth = 1.5 }:
  { children: ReactNode; className?: string; strokeWidth?: number }) {
  return (
    <svg className={className ? `spe-icon ${className}` : "spe-icon"} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true" focusable="false">
      {children}
    </svg>
  );
}

type P = { className?: string };

export const PencilSquare = ({ className }: P) => (
  <Icon className={className}>
    <path d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0 1 15.75 21H5.25A2.25 2.25 0 0 1 3 18.75V8.25A2.25 2.25 0 0 1 5.25 6H10" />
  </Icon>
);

export const Ellipsis = ({ className }: P) => (
  <Icon className={className}>
    <path d="M6.75 12a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0ZM12.75 12a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0ZM18.75 12a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0Z" />
  </Icon>
);

export const Pencil = ({ className }: P) => (
  <Icon className={className}>
    <path d="M14.3632 5.65156L15.8431 4.17157C16.6242 3.39052 17.8905 3.39052 18.6716 4.17157L20.0858 5.58579C20.8668 6.36683 20.8668 7.63316 20.0858 8.41421L18.6058 9.8942M14.3632 5.65156L4.74749 15.2672C4.41542 15.5993 4.21079 16.0376 4.16947 16.5054L3.92738 19.2459C3.87261 19.8659 4.39148 20.3848 5.0115 20.33L7.75191 20.0879C8.21972 20.0466 8.65806 19.8419 8.99013 19.5099L18.6058 9.8942M14.3632 5.65156L18.6058 9.8942" />
  </Icon>
);

export const Pin = ({ className }: P) => (
  <Icon className={className}>
    <path d="M9.5 14.5L3 21" />
    <path d="M5.00007 9.48528L14.1925 18.6777L15.8895 16.9806L15.4974 13.1944L21.0065 8.5211L15.1568 2.67141L10.4834 8.18034L6.69713 7.78823L5.00007 9.48528Z" />
  </Icon>
);

export const PinSlash = ({ className }: P) => (
  <Icon className={className}>
    <path d="M9.5 14.5L3 21" />
    <path d="M7.67602 7.8896L6.69713 7.78823L5.00007 9.48528L14.1925 18.6777L15.8895 16.9806L15.7879 16M11.4847 7L15.1568 2.67141L21.0065 8.5211L16.6991 12.175" />
    <path d="M3 3L21 21" />
  </Icon>
);

export const Tag = ({ className }: P) => (
  <Icon className={className} strokeWidth={1.8}>
    <path d="M4 12 L8 7 H21 V17 H8 L4 12 Z" />
    <circle cx="10" cy="12" r="0.75" fill="currentColor" />
  </Icon>
);

export const EyeSlash = ({ className }: P) => (
  <Icon className={className}>
    <path d="M3.98 8.223A10.477 10.477 0 0 0 1.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0 1 12 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 0 1-4.293 5.774M6.228 6.228 3 3m3.228 3.228 3.65 3.65m7.894 7.894L21 21m-3.228-3.228-3.65-3.65m0 0a3 3 0 1 0-4.243-4.243m4.242 4.242L9.88 9.88" />
  </Icon>
);

export const Eye = ({ className }: P) => (
  <Icon className={className}>
    <path d="M2.036 12.322a1.012 1.012 0 0 1 0-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178Z" />
    <path d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
  </Icon>
);

export const Trash = ({ className }: P) => (
  <Icon className={className}>
    <path d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
  </Icon>
);

// The sidebar toggle: a rounded panel with its left column marked.
export const SidebarToggle = ({ className }: P) => (
  <Icon className={className}>
    <rect x="3" y="3" width="18" height="18" rx="5" ry="5" />
    <path d="M9.5 21V3" />
  </Icon>
);

export const ChevronRight = ({ className }: P) => (
  <Icon className={className} strokeWidth={2}>
    <path d="m8.25 4.5 7.5 7.5-7.5 7.5" />
  </Icon>
);

// The tag pill's ×: Heroicons v2 mini (20×20, solid).
export const XMark = ({ className }: P) => (
  <svg className={className ? `spe-icon ${className}` : "spe-icon"} viewBox="0 0 20 20" fill="currentColor"
    aria-hidden="true" focusable="false">
    <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
  </svg>
);

// The tool-call card's status: done, failed, and a spinner (a quarter arc over a faint ring) while running.
export const Check = ({ className }: P) => (
  <Icon className={className} strokeWidth={2}>
    <path d="m4.5 12.75 6 6 9-13.5" />
  </Icon>
);

export const Cross = ({ className }: P) => (
  <Icon className={className} strokeWidth={2}>
    <path d="M6 18 18 6M6 6l12 12" />
  </Icon>
);

export const Spinner = ({ className }: P) => (
  <Icon className={className} strokeWidth={2}>
    <circle cx="12" cy="12" r="9" opacity="0.25" />
    <path d="M21 12a9 9 0 0 0-9-9" />
  </Icon>
);

export const Sun = ({ className }: P) => (
  <Icon className={className}>
    <path d="M12 3v2.25m6.364.386-1.591 1.591M21 12h-2.25m-.386 6.364-1.591-1.591M12 18.75V21m-4.773-4.227-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0Z" />
  </Icon>
);

export const Moon = ({ className }: P) => (
  <Icon className={className}>
    <path d="M21.752 15.002A9.72 9.72 0 0 1 18 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 0 0 3 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 0 0 9.002-5.998Z" />
  </Icon>
);
