import { describe, expect, it } from "vitest";
import { displayStockName, knownStockName, normalizeStockName } from "../lib/stock-display";

describe("stock display names", () => {
  it("knows common fallback names that can be shown before live data returns", () => {
    expect(knownStockName("2313")).toBe("華通");
    expect(knownStockName("3653")).toBe("健策");
    expect(knownStockName("3665")).toBe("貿聯-KY");
    expect(knownStockName("3693")).toBe("營邦");
    expect(knownStockName("6285")).toBe("啟碁");
    expect(normalizeStockName("3693", null)).toBe("營邦");
  });

  it("never displays an industry label as a company name", () => {
    expect(displayStockName("3693", "其他產業")).toBe("營邦");
    expect(displayStockName("9999", "其他產業")).toBe("待確認代碼");
    expect(displayStockName("9999", "電腦及週邊設備")).toBe("待確認代碼");
  });
});
