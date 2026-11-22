/* Bun Bun's face no longer lives in the panel.
 *
 * Through pre14 she was drawn here as a DOM overlay, which made her a
 * web page wearing an OS costume — exactly the problem diagnosed on
 * Nov 22: on the desktop and in Game Mode she rendered as a website,
 * not a system. The native presence layer (tools/bunhud) now draws her
 * straight through the compositor in both sessions, with her real
 * artwork, her listening face and her spoken lines as native bubbles.
 *
 * This stub keeps the shell's calls harmless, so the panel keeps its
 * own chrome while bunhud owns her face. No DOM subtree, no timer.
 */
export function createCompanion() {
  return {
    setScreen() {},
    react() {},
  };
}
