class APIResponseError(Exception):
    """Вызывается, если эндпоинт API вернул статус-код, отличный от 200 OK."""
