export type SelectionMode = "all" | "none" | "invert";
/** Change only the current scope; selections hidden by a filter are preserved. */
export function changeSelection(
  selected: readonly string[],
  scope: readonly string[],
  mode: SelectionMode,
): string[] {
  const result = new Set(selected);
  for (const id of new Set(scope)) {
    if (mode === "all") result.add(id);
    else if (mode === "none") result.delete(id);
    else if (result.has(id)) result.delete(id);
    else result.add(id);
  }
  return [...result];
}
