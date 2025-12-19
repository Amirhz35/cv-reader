from rest_framework.exceptions import APIException


class CustomException(APIException):
    def __init__(self, code, detail, status_code=400):
        self.code = code
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


class ValidationException(CustomException):
    pass


class AuthenticationException(CustomException):
    pass


class PermissionException(CustomException):
    pass


class NotFoundException(CustomException):
    def __init__(self, detail="Resource not found", code="not_found", status_code=404):
        super().__init__(code, detail, status_code)
