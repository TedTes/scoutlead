class SoutleadError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationError(SoutleadError):
    status_code = 400
    code = "validation_error"


class NotFoundError(SoutleadError):
    status_code = 404
    code = "not_found"


class ConflictError(SoutleadError):
    status_code = 409
    code = "conflict"


class WorkflowBoundaryError(SoutleadError):
    status_code = 422
    code = "workflow_boundary_error"
