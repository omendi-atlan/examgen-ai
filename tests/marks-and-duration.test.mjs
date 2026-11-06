import test from "node:test";
import assert from "node:assert/strict";
import { isValidTotalMarks, isValidDuration } from "../worker/src/limits.js";

test("accepts examination totals above 100 and below 150", () => {
  for (const total of [100, 120, 149]) assert.equal(isValidTotalMarks(total), true, String(total));
});

test("rejects 150 and every invalid total", () => {
  for (const total of [150, 200, 0, -1, 1.5, NaN, Infinity, undefined, null, "120"]) {
    assert.equal(isValidTotalMarks(total), false, String(total));
  }
});

test("accepts supported whole-number durations", () => {
  for (const duration of [10, 60, 120, 180, 240]) assert.equal(isValidDuration(duration), true);
});

test("rejects invalid durations", () => {
  for (const duration of [9, 241, 0, -10, 60.5, NaN, undefined, "60"]) {
    assert.equal(isValidDuration(duration), false);
  }
});
