export function isValidTotalMarks(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 1 && value < 150;
}

export function isValidDuration(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 10 && value <= 240;
}
