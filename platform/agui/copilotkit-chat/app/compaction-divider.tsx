"use client";

import { CopilotChatAssistantMessage } from "@copilotkit/react-core/v2";
import type { ComponentProps } from "react";
import { isCompactionMarker } from "../lib/compaction.ts";

// The summary is React text, never Markdown or HTML: it is model output over tool output.
export function CompactionDivider({ summary }: { summary: string }) {
  return (
    <div className="spe-compaction">
      <div className="spe-compaction-rule">
        <span className="spe-compaction-label">Earlier conversation compacted</span>
      </div>
      <details className="spe-compaction-summary">
        <summary>Summary the model continues from</summary>
        <div>{summary}</div>
      </details>
    </div>
  );
}

function render(props: ComponentProps<typeof CopilotChatAssistantMessage>) {
  if (isCompactionMarker(props.message)) {
    return <CompactionDivider summary={props.message.content} />;
  }
  return <CopilotChatAssistantMessage {...props} />;
}

// The slot is typed as CopilotKit's component with its static parts, so ours carries them too.
export const AssistantOrCompaction = Object.assign(render, CopilotChatAssistantMessage) as
  typeof CopilotChatAssistantMessage;
