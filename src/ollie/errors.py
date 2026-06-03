class OllieError(Exception):
    """Base SDK error."""


class OllieHTTPError(OllieError):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")


class OllieValidationError(OllieError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


class OllieDeliveryError(OllieError):
    def __init__(self, batch_id: str, attempt: int, detail: str):
        self.batch_id = batch_id
        self.attempt = attempt
        self.detail = detail
        super().__init__(f"delivery batch {batch_id} failed after attempt {attempt}: {detail}")
