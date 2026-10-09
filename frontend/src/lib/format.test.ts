import { formatCompact, formatDate, formatMonth, formatNumber, formatPercent, formatUSD, formatUSDCompact } from "./format";

describe("format", () => {
  it("groups numbers US-style", () => {
    expect(formatNumber(12352)).toBe("12,352");
    expect(formatNumber(105860513.85, 2)).toBe("105,860,513.85");
    expect(formatNumber(null)).toBe("—");
  });

  it("formats USD", () => {
    expect(formatUSD(1234.5)).toBe("$1,234.50");
    expect(formatUSD(105860513.85, { whole: true })).toBe("$105,860,514");
    expect(formatUSD(Number.NaN)).toBe("—");
  });

  it("formats percentages that are already scaled", () => {
    expect(formatPercent(4.8)).toBe("4.8%");
    expect(formatPercent(39.4, 0)).toBe("39%");
  });

  it("formats dates as DD MMM YYYY without time-zone drift", () => {
    expect(formatDate("2020-05-27")).toBe("27 May 2020");
    expect(formatDate("2020-01-05T23:30:00")).toBe("05 Jan 2020");
    expect(formatDate("")).toBe("—");
    expect(formatMonth("2020-03")).toBe("Mar 2020");
  });
});

describe("compact formatting", () => {
  it("abbreviates large values", () => {
    expect(formatCompact(195514)).toBe("195.5K");
    expect(formatUSDCompact(12_534_916_073)).toBe("$12.5B");
    expect(formatUSDCompact(-69_695_406)).toBe("-$69.7M");
  });
  it("keeps small amounts exact", () => {
    expect(formatUSDCompact(15_192)).toBe("$15,192");
    expect(formatCompact(null)).toBe("—");
  });
});
