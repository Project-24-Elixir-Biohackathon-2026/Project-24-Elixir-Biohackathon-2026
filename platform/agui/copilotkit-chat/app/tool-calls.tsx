"use client";
// Tool-call cards, after Open WebUI's ToolCallDisplay: a status icon, "Executing <name>…" while the call
// runs and the bare name once it is done (the check already says so), and, unfolded, the arguments and the
// result, under Open WebUI's "Input" and "Output" labels. The calls of one model response sit under one group
// header, "Explored list_files, 2 run_command" as Open WebUI words it. All of it is React text, never HTML.
import { contentToText } from "@ag-ui/client";
import { CopilotChatToolCallsView, type CopilotChatToolCallsViewProps } from "@copilotkit/react-core/v2";
import {
  argumentRows, cardState, commandOf, groupState, readResult, toolSummary, type CallStatus, type CardState,
} from "../lib/tool-card.ts";
import { Check, ChevronRight, Cross, Spinner } from "./icons";

type ToolProps = { name: string; parameters: unknown; status: CallStatus; result: string | undefined };

function ToolStatus({ state }: { state: CardState }) {
  if (state === "running") return <Spinner className="spe-tool-icon spe-tool-spinner" />;
  return state === "failed" ? <Cross className="spe-tool-icon" /> : <Check className="spe-tool-icon" />;
}

function ToolTitle({ state, name }: { state: CardState; name: string }) {
  const code = <code>{name}</code>;
  if (state === "running") return <>Executing {code}…</>;
  return state === "failed" ? <>{code} failed</> : code;
}

// Arguments as key/value rows; run_command's command as a `$ <command>` line above them instead.
export function ToolCard({ name, parameters, status, result }: ToolProps) {
  const state = cardState(status, result, name);
  const command = commandOf(name, parameters);
  const rows = argumentRows(parameters).filter(([key]) => command === null || key !== "command");
  return (
    <details className={`spe-tool spe-tool-${state}`}>
      <summary>
        <ToolStatus state={state} />
        <span className="spe-tool-title"><ToolTitle state={state} name={name} /></span>
        <ChevronRight className="spe-tool-chevron" />
      </summary>
      {(command !== null || rows.length > 0) && <div className="spe-tool-label">Input</div>}
      {command !== null && <pre className="spe-tool-command">$ {command}</pre>}
      {rows.length > 0 && (
        <dl className="spe-tool-args">
          {rows.map(([key, value], i) => (
            <div key={i}><dt>{key}</dt><dd>{value}</dd></div>
          ))}
        </dl>
      )}
      {result !== undefined && <div className="spe-tool-label">Output</div>}
      {result !== undefined && <pre className="spe-tool-result">{readResult(name, result).body}</pre>}
    </details>
  );
}

// The assistant message's toolCallsView slot: one call as its card, several under a header that says
// "Exploring" or "Explored", which tools how often, and how many failed. A call counts as running until its tool message arrives.
export function ToolCallsView({ message, messages = [] }: CopilotChatToolCallsViewProps) {
  const calls = message.toolCalls ?? [];
  if (calls.length < 2) return <CopilotChatToolCallsView message={message} messages={messages} />;
  const states = calls.map((call) => {
    const reply = messages.find((m) => m.role === "tool" && m.toolCallId === call.id);
    return reply ? cardState("complete", contentToText(reply.content as Parameters<typeof contentToText>[0]), call.function.name) : "running";
  });
  const state = groupState(states);
  const failed = states.filter((s) => s === "failed").length;
  const names = toolSummary(calls.map((call) => call.function.name));
  return (
    <details className={`spe-tool-group spe-tool-${state}`}>
      <summary>
        <ToolStatus state={state} />
        <span className="spe-tool-title">{state === "running" ? "Exploring" : "Explored"}</span>
        <span className="spe-tool-names">
          {names}
          {failed > 0 && state !== "running" && <span className="spe-tool-group-failed"> · {failed} failed</span>}
        </span>
        <ChevronRight className="spe-tool-chevron" />
      </summary>
      <div className="spe-tool-group-calls">
        <CopilotChatToolCallsView message={message} messages={messages} />
      </div>
    </details>
  );
}
