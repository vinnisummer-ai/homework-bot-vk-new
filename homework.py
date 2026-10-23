import http
import logging
import os
import sys
import time
from datetime import datetime

import requests
import vk_api
from dotenv import load_dotenv
from vk_api.utils import get_random_id

from constants import ENDPOINT, HEADERS, HOMEWORK_VERDICTS, RETRY_PERIOD
from exceptions import APIResponseError

load_dotenv()

VK_TOKEN = os.environ.get('VK_TOKEN')
VK_USER_ID = os.environ.get('VK_USER_ID')
PRACTICUM_TOKEN = os.environ.get('PRACTICUM_TOKEN')

logger = logging.getLogger(__name__)


def check_tokens():
    """Проверяет доступность переменных окружения.

    В случае отсутствия токенов вызывает исключение APIResponseError.
    """
    tokens = (
        ('VK_TOKEN', VK_TOKEN),
        ('VK_USER_ID', VK_USER_ID),
        ('PRACTICUM_TOKEN', PRACTICUM_TOKEN),
    )
    missing_tokens = [name for name, value in tokens if not value]
    if missing_tokens:
        error_msg = (
            f'Отсутствуют обязательные переменные окружения: '
            f"{', '.join(missing_tokens)}"
        )
        logger.critical(error_msg)
        raise APIResponseError(error_msg)


def send_message(vk, message: str) -> bool:
    """Отправляет подготовленное сообщение в VK.

    Возвращает True в случае успешной отправки, иначе False.
    """
    logger.info('Начало отправки сообщения в VK для ID %s', VK_USER_ID)
    try:
        vk.messages.send(
            user_id=VK_USER_ID,
            message=message,
            random_id=get_random_id()
        )
        logger.debug(
            'Сообщение успешно отправлено в VK для ID %s.',
            VK_USER_ID
        )
        return True
    except (vk_api.exceptions.ApiError, requests.RequestException) as error:
        logger.error('Сбой при отправке сообщения в VK: %s.', error)
        return False


def get_api_answer(current_timestamp: int):
    """Делает запрос к эндпоинту API сервиса и возвращает ответ."""
    request_params = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {'from_date': current_timestamp},
    }
    unix_time = request_params['params']['from_date']
    readable_date = (
        datetime.fromtimestamp(unix_time)
        .strftime('%Y-%m-%d %H:%M:%S')
    )
    logger.info(
        f'Начало запроса к API. Время: {readable_date}'
    )
    try:
        response = requests.get(**request_params)
    except requests.RequestException as error:
        raise APIResponseError(f'Ошибка при запросе к API: {error}')
    if response.status_code != http.HTTPStatus.OK:
        raise APIResponseError(
            f'Неожиданный статус-код ответа API. '
            f'Эндпоинт: {ENDPOINT}, статус-код: {response.status_code}'
        )
    return response.json()


def check_response(response: dict):
    """Проверяет соответствие полученного ответа ожидаемой структуре."""
    if not isinstance(response, dict):
        raise TypeError(
            f'Неверный тип данных в ответе API. '
            f'Ожидался словарь (dict), но получен: {type(response).__name__}'
        )
    if 'homeworks' not in response:
        raise KeyError('В ответе API отсутствует ожидаемый ключ "homeworks".')
    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError(
            f'Под ключом "homeworks" ожидался список (list), '
            f'но получен: {type(homeworks).__name__}'
        )
    return homeworks


def parse_status(homework: dict):
    """Обрабатывает информацию о домашней работе и возвращает текст."""
    if not isinstance(homework, dict):
        raise TypeError(
            f'Неверный тип данных для домашней работы. '
            f'Ожидался словарь (dict), но получен: {type(homework).__name__}'
        )
    if 'homework_name' not in homework:
        raise KeyError(
            'В данных домашней работы отсутствует ключ "homework_name".'
        )
    if 'status' not in homework:
        raise KeyError('В данных домашней работы отсутствует ключ "status".')
    homework_name = homework['homework_name']
    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(f'Получен неизвестный статус работы: {status}')
    verdict = HOMEWORK_VERDICTS[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    check_tokens()
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    timestamp = int(time.time())
    last_error = None
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks:
                latest_homework = homeworks[0]
                message = parse_status(latest_homework)
                if send_message(vk, message):
                    timestamp = response.get('current_date', timestamp)
            else:
                logger.debug('Новых домашних работ в ответе нет.')
                timestamp = response.get('current_date', timestamp)
            last_error = None
        except Exception as error:
            error_msg = f'Сбой в работе программы: {error}'
            logger.error(error_msg)
            current_error_str = str(error)
            if current_error_str != last_error:
                send_message(vk, error_msg)
                last_error = current_error_str
        finally:
            logger.info('Ожидание следующей проверки: %s сек.', RETRY_PERIOD)
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [%(levelname)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    try:
        main()
    except Exception as error:
        logger.critical(f'Бот упал из-за непредвиденной ошибки: {error}')
        sys.exit(1)
