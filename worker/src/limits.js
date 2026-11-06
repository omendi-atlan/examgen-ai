export function isValidTotalMarks(value) {
  return Number.isInteger(value) && value >= 1 && value < 150;
}

export function isValidDuration(value) {
  return Number.isInteger(value) && value >= 10 && value <= 240;
}
