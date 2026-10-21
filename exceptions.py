class APIResponseError(Exception):
    """Вызывается, если эндпоинт API вернул статус-код, отличный от 200 OK."""
    pass


class EmptyAPIResponseError(Exception):
    """Вызывается при критических ошибках запроса."""
    pass