function interactions(payload: Record<string, unknown>): Record<string, unknown>[] {
  return ((payload.interactions as unknown[]) ?? []).filter(
    (ix): ix is Record<string, unknown> => typeof ix === "object" && ix !== null,
  );
}

function childrenMap(
  items: Record<string, unknown>[],
): Map<string | null, Record<string, unknown>[]> {
  const byRef = new Map<string, Record<string, unknown>>();
  for (const ix of items) {
    const ref = ix.interaction_ref;
    if (ref) byRef.set(String(ref), ix);
  }
  const children = new Map<string | null, Record<string, unknown>[]>();
  for (const ix of items) {
    let parentKey: string | null = ix.parent_interaction_ref
      ? String(ix.parent_interaction_ref)
      : null;
    if (parentKey && !byRef.has(parentKey)) parentKey = null;
    const list = children.get(parentKey) ?? [];
    list.push(ix);
    children.set(parentKey, list);
  }
  for (const list of children.values()) {
    list.sort((a, b) => String(a.started_at ?? "").localeCompare(String(b.started_at ?? "")));
  }
  return children;
}

function formatIx(ix: Record<string, unknown>): string {
  const name = String(ix.name ?? ix.interaction_ref ?? "?");
  const primitive = ix.primitive;
  const prim = primitive ? ` [${primitive}]` : "";
  const events = ix.events;
  const attrs = (ix.attributes as unknown[]) ?? [];
  const suffixParts: string[] = [];
  if (events && typeof events === "object" && !Array.isArray(events)) {
    const ev = events as Record<string, unknown>;
    const nSig =
      ((ev.trigger as unknown[]) ?? []).length + ((ev.context as unknown[]) ?? []).length;
    const nSpans = ((ev.spans as unknown[]) ?? []).length;
    if (nSig) suffixParts.push(`signals=${nSig}`);
    if (nSpans) suffixParts.push(`spans=${nSpans}`);
  } else if (Array.isArray(events) && events.length) {
    suffixParts.push(`events=${events.length}`);
  }
  if (attrs.length) suffixParts.push(`attrs=${attrs.length}`);
  const suffix = suffixParts.length ? ` ${suffixParts.join(" ")}` : "";
  return `${name}${prim}${suffix}`;
}

function renderNode(
  ix: Record<string, unknown>,
  map: Map<string | null, Record<string, unknown>[]>,
  prefix: string,
  isLast: boolean,
): string[] {
  const ref = String(ix.interaction_ref ?? "");
  const branch = isLast ? "└── " : "├── ";
  const lines = [`${prefix}${branch}${formatIx(ix)}`];
  const childPrefix = prefix + (isLast ? "    " : "│   ");
  const kids = map.get(ref) ?? [];
  kids.forEach((child, i) => {
    lines.push(...renderNode(child, map, childPrefix, i === kids.length - 1));
  });
  return lines;
}

export function renderInteractionTree(payload: Record<string, unknown>): string {
  const workflow =
    typeof payload.workflow === "object" && payload.workflow
      ? (payload.workflow as Record<string, unknown>)
      : {};
  const name = String(workflow.name ?? "workflow");
  const status = String(workflow.status ?? "unknown");
  const started = workflow.started_at ?? "?";
  const ended = workflow.ended_at ?? "?";
  const header = `Workflow: ${name} [${status}] ${started} → ${ended}`;

  const items = interactions(payload);
  if (!items.length) return `${header}\n(no interactions)`;

  const map = childrenMap(items);
  let roots = map.get(null) ?? [];
  if (!roots.length) {
    const refsWithParent = new Set(
      items.filter((ix) => ix.parent_interaction_ref).map((ix) => String(ix.parent_interaction_ref)),
    );
    roots = items.filter((ix) => !refsWithParent.has(String(ix.interaction_ref)));
  }

  const lines = [header];
  roots.forEach((root, i) => {
    lines.push(...renderNode(root, map, "", i === roots.length - 1));
  });
  return lines.join("\n");
}
