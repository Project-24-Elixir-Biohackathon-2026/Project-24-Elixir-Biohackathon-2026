import type { KeyboardEvent } from "react";

// IME composition (e.g. a CJK input method) uses Enter and Escape itself.
export const composing = (e: KeyboardEvent) => e.nativeEvent.isComposing || e.keyCode === 229;
