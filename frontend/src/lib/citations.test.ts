import { describe, expect, it } from "vitest";
import { linkCitations, parseCiteHref, urlTransform } from "./citations";

describe("linkCitations", () => {
  const valid = new Set([1, 2, 3]);

  it("groups adjacent citations into one link", () => {
    expect(linkCitations("Al Marjan Island [1][2].", valid)).toBe("Al Marjan Island [1,2](cite:1,2).");
  });

  it("supports comma lists and drops unknown numbers", () => {
    expect(linkCitations("Yes [1, 3] and [9].", valid)).toBe("Yes [1,3](cite:1,3) and.");
  });

  it("works inside table cells and Arabic text", () => {
    expect(linkCitations("| DG1 | Dubai [2] |", valid)).toBe("| DG1 | Dubai [2](cite:2) |");
    expect(linkCitations("في جزيرة المرجان [1].", valid)).toBe("في جزيرة المرجان [1](cite:1).");
  });
});

describe("cite links", () => {
  it("parses cite hrefs and keeps them through sanitising", () => {
    expect(parseCiteHref("cite:1,2")).toEqual([1, 2]);
    expect(parseCiteHref("https://x")).toBeNull();
    expect(urlTransform("cite:3")).toBe("cite:3");
    expect(urlTransform("javascript:alert(1)")).toBe("");
    expect(urlTransform("https://darglobal.co.uk")).toBe("https://darglobal.co.uk");
  });
});
