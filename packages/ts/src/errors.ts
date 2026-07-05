export class OllieError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "OllieError";
  }
}

export class OllieHTTPError extends OllieError {
  statusCode: number;
  detail: string;

  constructor(statusCode: number, detail: string) {
    super(`HTTP ${statusCode}: ${detail}`);
    this.name = "OllieHTTPError";
    this.statusCode = statusCode;
    this.detail = detail;
  }
}

export class OllieValidationError extends OllieError {
  errors: string[];

  constructor(errors: string[]) {
    super(errors.join("; "));
    this.name = "OllieValidationError";
    this.errors = errors;
  }
}

export class OllieDeliveryError extends OllieError {
  batchId: string;
  attempt: number;
  detail: string;

  constructor(batchId: string, attempt: number, detail: string) {
    super(`delivery batch ${batchId} failed after attempt ${attempt}: ${detail}`);
    this.name = "OllieDeliveryError";
    this.batchId = batchId;
    this.attempt = attempt;
    this.detail = detail;
  }
}
