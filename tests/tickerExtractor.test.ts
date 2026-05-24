import { describe, expect, it } from "vitest";
import { extractTickersFromPost, extractTickersFromText } from "../src/shared/tickerExtractor.js";

describe("ticker extraction", () => {
  it("extracts cashtags and plain uppercase tickers", () => {
    expect(extractTickersFromText("I like $tsla and NVDA here. TSLA has momentum.")).toEqual([
      "TSLA",
      "NVDA",
      "TSLA",
    ]);
  });

  it("filters common false positives", () => {
    expect(extractTickersFromText("THE CEO said CPI matters but AMD and $msft are moving. LOL")).toEqual([
      "MSFT",
      "AMD",
    ]);
  });

  it("extracts from post comments", () => {
    expect(extractTickersFromPost("Watching GME", "Body mentions $amc", ["NVDA calls", "YOLO"])).toEqual([
      "GME",
      "AMC",
      "NVDA",
    ]);
  });

  it("does not double count uppercase cashtags", () => {
    expect(extractTickersFromText("$TSLA is stronger than TSLA today")).toEqual(["TSLA", "TSLA"]);
  });
});
