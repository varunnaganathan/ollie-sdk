import { getActiveParent, getActiveWorkflow } from "./context.js";
import type { InteractionHandle } from "./interaction.js";
import { EXTERNAL_INTERACTION } from "./primitives.js";

export class ToolScope implements Disposable {
  readonly name: string;
  readonly input: string | null;
  readonly parent: InteractionHandle | null;
  handle: InteractionHandle | null = null;
  private wf: ReturnType<typeof getActiveWorkflow> = null;

  constructor(
    name: string,
    options?: { input?: string | null; parent?: InteractionHandle | null },
  ) {
    this.name = name;
    this.input = options?.input ?? null;
    this.parent = options?.parent ?? null;
  }

  enter(): InteractionHandle {
    const wf = getActiveWorkflow();
    if (!wf) {
      throw new Error(
        "ollie.tool() requires an active workflow. Use: with client.workflow({ name: ... }) as wf: ...",
      );
    }
    const parentHandle = this.parent ?? getActiveParent();
    this.wf = wf;
    this.handle = wf.interaction.start({
      name: this.name,
      primitive: EXTERNAL_INTERACTION,
      parent: parentHandle,
      input: this.input,
    });
    return this.handle;
  }

  exit(exc?: unknown): void {
    const handle = this.handle;
    const wf = this.wf;
    if (handle && wf && !handle.closed) {
      if (exc) handle.markSuccess(false);
      else if (handle.success === null) handle.markSuccess(true);
      wf.interaction.end(handle, handle.output);
    }
    this.handle = null;
    this.wf = null;
  }

  [Symbol.dispose](): void {
    this.exit();
  }
}

export function tool(
  name: string,
  options?: { input?: string | null; parent?: InteractionHandle | null },
): ToolScope {
  return new ToolScope(name, options);
}

export function toolDecorator(
  name: string,
  options?: { input?: string | null; parent?: InteractionHandle | null },
) {
  return function <F extends (...args: unknown[]) => unknown>(fn: F): F {
    const wrapped = (...args: unknown[]) => {
      const scope = tool(name, options);
      scope.enter();
      try {
        const result = fn(...args);
        if (scope.handle && scope.handle.output == null && result != null) {
          scope.handle.output = String(result).slice(0, 2000);
        }
        return result;
      } catch (exc) {
        scope.exit(exc);
        throw exc;
      } finally {
        scope.exit();
      }
    };
    return wrapped as F;
  };
}
