import http
import logging
import os
import sys
import time
import requests
import vk_api
from vk_api.utils import get_random_id

from dotenv import load_dotenv

from constants import RETRY_PERIOD, ENDPOINT, HEADERS, HOMEWORK_VERDICTS
from exceptions import APIResponseError, EmptyAPIResponseError


load_dotenv()


VK_TOKEN = os.environ.get('VK_TOKEN')
VK_USER_ID = os.environ.get('VK_USER_ID')
PRACTICUM_TOKEN = os.environ.get('PRACTICUM_TOKEN')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)],
)


def check_tokens():
    """Проверяет доступность всех обязательных переменных."""
    return all([VK_TOKEN, VK_USER_ID, PRACTICUM_TOKEN])


def send_message(vk, message: str):
    """Отправляет подготовленное сообщение в VK."""
    try:
        response = vk.messages.send(
            user_id=VK_USER_ID,
            message=message,
            random_id=get_random_id()
        )
        logging.debug(f'Сообщение успешно '
                      f'отправлено в VK для ID {VK_USER_ID}.')
        return response
    except Exception as error:
        logging.error(f'Сбой при отправке сообщения в VK: {error}.')


def get_api_answer(current_timestamp: int):
    """Делает запрос к эндпоинту API сервиса и возвращает ответ."""
    HEADERS['Authorization'] = f'OAuth {PRACTICUM_TOKEN}'
    payload = {'from_date': current_timestamp}

    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=payload)
    except requests.RequestException as error:
        error_msg = f'Ошибка при запросе к API: {error}.'
        logging.error(error_msg)
        raise EmptyAPIResponseError(error_msg)
    if response.status_code != http.HTTPStatus.OK:
        error_msg = (
            f'Эндпоинт {ENDPOINT} недоступен. '
            f'Код ответа API: {response.status_code}.'
        )
        logging.error(error_msg)
        raise APIResponseError(error_msg)
    return response.json()


def check_response(response: dict):
    """Проверяет соответствие полученного ответа ожидаемой структуре."""
    if not isinstance(response, dict):
        raise TypeError('Ответ API должен быть словарем.')
    if "homeworks" not in response:
        error_msg = 'В ответе API отсутствует ожидаемый ключ "homeworks".'
        logging.error(error_msg)
        raise KeyError(error_msg)
    if not isinstance(response['homeworks'], list):
        raise TypeError('Под ключом "homeworks" должен быть список.')
    return True


def parse_status(homework: dict):
    """Обрабатывает информацию о домашней работе и возвращает текст."""
    if 'homework_name' not in homework:
        raise KeyError('В ответе API отсутствует ключ "homework_name"')
    if 'status' not in homework:
        raise KeyError('В ответе API отсутствует ключ "status"')
    homework_name = homework['homework_name']
    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        error_message = f'Получен неизвестный статус работы: {status}.'
        logging.error(error_message)
        raise ValueError(error_message)  # Тесты ждут именно raise!
    verdict = HOMEWORK_VERDICTS[status]
    return (
        f'Изменился статус проверки работы "{homework_name}". '
        f'{verdict}'
    )


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logging.critical(
            'Критическая ошибка: '
            'отсутствуют обязательные переменные окружения!')
        sys.exit('Программа принудительно остановлена.')
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    timestamp = int(time.time())
    last_status = None
    last_error = None
    while True:
        try:
            response = get_api_answer(timestamp)
            if check_response(response):
                homeworks = response.get('homeworks')
                if homeworks:
                    latest_homework = homeworks[0]
                    current_status = latest_homework.get('status')
                    if current_status != last_status:
                        message = parse_status(latest_homework)
                        send_message(vk, message)
                        last_status = current_status
                    else:
                        logging.info('Статус работы не изменился.')
                else:
                    logging.debug('Новых домашних работ в ответе нет.')
                timestamp = response.get('current_date', timestamp)
                last_error = None
        except Exception as error:
            message = f'Сбой в работе программы: {error}.'
            logging.error(message)
            if str(error) != last_error:
                send_message(vk, message)
                last_error = str(error)
        finally:
            logging.info(f'Ожидание следующей проверки '
                         f'{RETRY_PERIOD} секунд...')
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
