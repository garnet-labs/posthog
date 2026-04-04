import { z } from "zod";

import type { Context, Tool, ZodObjectAny } from "./types";

const ExecSchema = z.object({
  command: z
    .string()
    .describe(
      "CLI-style command string. Supported commands:\n" +
        "  tools                         — list available tool names\n" +
        "  info <tool_name>              — show tool name, description, and input schema\n" +
        "  call <tool_name> <json_input> — call a tool with JSON input",
    ),
});

type ExecSchema = typeof ExecSchema;

function parseCommand(input: string): { verb: string; rest: string } {
  const trimmed = input.trim();
  const idx = trimmed.indexOf(" ");
  if (idx === -1) {
    return { verb: trimmed, rest: "" };
  }
  return { verb: trimmed.slice(0, idx), rest: trimmed.slice(idx + 1).trim() };
}

function findTool(
  tools: Tool<ZodObjectAny>[],
  name: string,
): Tool<ZodObjectAny> {
  const tool = tools.find((t) => t.name === name);
  if (!tool) {
    const available = tools.map((t) => t.name).join(", ");
    throw new Error(`Unknown tool: "${name}". Available tools: ${available}`);
  }
  return tool;
}

export function createExecTool(
  allTools: Tool<ZodObjectAny>[],
  context: Context,
): Tool<ExecSchema> {
  return {
    name: "posthog",
    title: "PostHog",
    description:
      'Single entry point for all PostHog tools. Use "tools" to list available tools, ' +
      '"info <tool_name>" to get tool details, and "call <tool_name> <json>" to invoke a tool.',
    schema: ExecSchema,
    scopes: [],
    annotations: {
      destructiveHint: false,
      idempotentHint: false,
      openWorldHint: true,
      readOnlyHint: false,
    },
    handler: async (_context: Context, params: z.infer<ExecSchema>) => {
      const { verb, rest } = parseCommand(params.command);

      switch (verb) {
        case "tools": {
          return allTools.map((t) => t.name);
        }

        case "info": {
          if (!rest) {
            throw new Error("Usage: info <tool_name>");
          }
          const tool = findTool(allTools, rest);
          return {
            name: tool.name,
            title: tool.title,
            description: tool.description,
            annotations: tool.annotations,
            inputSchema: z.toJSONSchema(tool.schema),
          };
        }

        case "call": {
          if (!rest) {
            throw new Error("Usage: call <tool_name> <json_input>");
          }
          const { verb: toolName, rest: jsonBody } = parseCommand(rest);
          const tool = findTool(allTools, toolName);

          let input: Record<string, unknown>;
          if (!jsonBody) {
            input = {};
          } else {
            try {
              input = JSON.parse(jsonBody) as Record<string, unknown>;
            } catch {
              throw new Error(`Invalid JSON input: ${jsonBody}`);
            }
          }

          return tool.handler(context, input);
        }

        default:
          throw new Error(
            `Unknown command: "${verb}". Supported commands: tools, info, call`,
          );
      }
    },
  };
}
