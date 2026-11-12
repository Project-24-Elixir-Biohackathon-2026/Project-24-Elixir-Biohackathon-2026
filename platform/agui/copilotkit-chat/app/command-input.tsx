"use client";
// The chat input with `/compact` made visible (spec §15, *In the chat input*): an entry in CopilotKit's own slash
// menu while the text is still a prefix of `/compact`, and the composer marked as a command while the text parses
// as one (lib/command.ts). A textarea cannot colour one word, so the whole composer is marked.
import { CopilotChatInput } from "@copilotkit/react-core/v2";
import type { ComponentProps } from "react";
import { offersCompact, parseCommand } from "../lib/command.ts";
import { DraftTextProvider, ThreatDisclaimer } from "./threat-indicator";

// "compact" first, so the menu's filter (label starts with what follows the `/`) puts it on top.
const COMPACT_LABEL = "compact · summarise the conversation so far (/compact <focus> to say what to keep)";

// The "+" button shows `toolsMenu` too; attachments are off, so it stays disabled rather than holding the entry.
const NO_ADD_MENU = { toolsMenu: [] };

function render(props: ComponentProps<typeof CopilotChatInput>) {
  const { value = "", onSubmitMessage } = props;
  // Picking the entry (a click, or Enter while it is highlighted) clears the input and sends a bare `/compact`:
  // with the menu open, Enter picks the entry instead of sending, so the entry has to send itself.
  const toolsMenu = onSubmitMessage && offersCompact(value)
    ? [{ label: COMPACT_LABEL, action: () => onSubmitMessage("/compact") }]
    : [];
  const command = parseCommand(value) !== null;
  return (
    // The draft reaches the threat indicator (in the disclaimer slot, under the composer) through context.
    <DraftTextProvider value={value}>
      <CopilotChatInput
        {...props}
        toolsMenu={toolsMenu}
        addMenuButton={NO_ADD_MENU}
        disclaimer={ThreatDisclaimer}
        data-command={command ? "compact" : undefined}
      />
    </DraftTextProvider>
  );
}

// The slot is typed as CopilotKit's component with its static parts, so ours carries them too.
export const CommandInput = Object.assign(render, CopilotChatInput) as typeof CopilotChatInput;
