class APIError(Exception):
    """Honest, typed error. Codes match the frontend contract."""
    def __init__(self, code: str, message: str, status: int):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)

def invalid_coords(msg="Latitude must be -90..90 and longitude -180..180."):
    return APIError("INVALID_COORDINATES", msg, 400)
