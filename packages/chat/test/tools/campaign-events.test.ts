import { describe, expect, it } from "vitest";
import { makeEvent } from "../fixtures.js";
import { formatEvent, formatEvents } from "../../src/tools/campaign-events.js";

describe("formatEvent", () => {
  it("renders one line with timestamp, actor, type, and reason", () => {
    const out = formatEvent(makeEvent());
    expect(out).toBe(
      "2026-10-02 03:42:00Z agent campaign.created             plan accepted",
    );
  });

  it("appends the payload when verbose", () => {
    const out = formatEvent(
      makeEvent({ payload: { stop_reason: "cancelled" } }),
      true,
    );
    const [line, detail] = out.split("\n");
    expect(line).toContain("plan accepted");
    expect(detail).toContain('{"stop_reason":"cancelled"}');
  });

  it("omits an empty payload even when verbose", () => {
    const out = formatEvent(makeEvent(), true);
    expect(out).not.toContain("\n");
  });
});

describe("formatEvents", () => {
  it("renders an empty ledger", () => {
    expect(formatEvents([])).toBe("No events yet.");
  });

  it("renders one line per event", () => {
    const out = formatEvents([
      makeEvent(),
      makeEvent({ seq: 2, type: "experiment.proposed" }),
    ]);
    expect(out.split("\n")).toHaveLength(2);
  });
});
