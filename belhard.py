import asyncio
import logging
from difflib import SequenceMatcher
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
import aiohttp
from knowledge_base import knowledge_base


# Устанавливаем уровень логирования
logging.basicConfig(level=logging.INFO)

# Токен вашего Telegram-бота
BOT_TOKEN = '6689433021:AAEikkiTiXa18w57FUm6FOp2jd1_IO4byH4'

# URL вебхука Bitrix24
BITRIX24_WEBHOOK_URL = 'https://b24-kw5z35.bitrix24.by/rest/11/ffqo36u9m5t1zydv/crm.lead.add.json'

# Инициализируем бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Хранилище для данных заявки
user_data = {}
collecting_data = set()

# Переменная для хранения состояния ожидания триггера
expected_trigger_response = {}

# Функция для нахождения наиболее похожего ключа в базе знаний
def find_best_match(question):
    best_match = None
    highest_ratio = 0
    for key in knowledge_base:
        ratio = SequenceMatcher(None, question.lower(), key.lower()).ratio()
        if ratio > highest_ratio:
            highest_ratio = ratio
            best_match = key
    return best_match if highest_ratio > 0.5 else None

# Обработчик команды /start
@dp.message(Command(commands=['start']))
async def send_welcome(message: Message):
    await message.reply("Добро пожаловать в Академию Белхард! Как я могу помочь Вам сегодня?")

# Обработчик команды /lead
@dp.message(Command(commands=['lead']))
async def start_lead(message: Message):
    chat_id = message.chat.id
    user_data[chat_id] = {}
    collecting_data.add(chat_id)
    await message.reply("Пожалуйста, введите ваши данные в формате: Фамилия Имя Отчество Телефон Email")

# Обработчик для сбора данных
@dp.message()
async def collect_data(message: Message):
    chat_id = message.chat.id

    if chat_id in collecting_data:
        if any(cancel_word in message.text.lower() for cancel_word in ['отмена', 'отменить', 'вернуться',
                                                                       'не сейчас', 'позже', 'назад', 'начало']):
            collecting_data.remove(chat_id)
            await message.reply("Академию Белхард! Как я могу помочь Вам?")
            return

        best_match = find_best_match(message.text)
        if best_match:
            response = knowledge_base[best_match]
            await message.reply(response)

            if response == "Уточните, пожалуйста, на какой курс Вы хотели бы записаться? Для записи от Вас необходимы ваши полные ФИО, контактный телефон и электронная почта, на которую мы вышлем письмо-приглашение на курс." \
                    or response == "Курс Войти в IT, стоит 50 руб." \
                    or response == "Стоимость тренинга составляет 50 белорусских рублей." \
                    or response == "Время проведения с 10:00 до 16:00." \
                    or response == "Оплату можно вносить через ЕРИП или же любое отделение банка." \
                    or response == "Тренинг на данный момент проходит в 2 форматах одновременно (в очном, удаленном), поэтому самостоятельно можете выбирать формат участия.":

                expected_trigger_response[chat_id] = True
            collecting_data.remove(chat_id)  # Останавливаем сбор данных, если вопрос найден в базе знаний
            return

        data = message.text.split()
        if len(data) == 5:
            user_data[chat_id]['last_name'] = ''.join(filter(str.isalpha, data[0]))  # Оставляем только буквы
            user_data[chat_id]['first_name'] = ''.join(filter(str.isalpha, data[1]))  # Оставляем только буквы
            user_data[chat_id]['middle_name'] = ''.join(filter(str.isalpha, data[2]))  # Оставляем только буквы
            user_data[chat_id]['phone'] = ''.join(filter(str.isdigit, data[3]))  # Оставляем только цифры
            user_data[chat_id]['email'] = data[4]
            await send_to_bitrix24(chat_id)
            collecting_data.remove(chat_id)
        else:
            missing_data = []
            if 'last_name' not in user_data[chat_id]:
                missing_data.append("Фамилия")
            if 'first_name' not in user_data[chat_id]:
                missing_data.append("Имя")
            if 'middle_name' not in user_data[chat_id]:
                missing_data.append("Отчество")
            if 'phone' not in user_data[chat_id]:
                missing_data.append("Телефон")
            if 'email' not in user_data[chat_id]:
                missing_data.append("Email")
            await message.reply(f"Недостающие данные: {', '.join(missing_data)}. Пожалуйста, введите данные заново.")
        return

    user_input = message.text

    # Проверка на наличие триггера в нужном контексте
    if chat_id in expected_trigger_response and expected_trigger_response[chat_id]:
        if any(trigger in user_input.lower() for trigger in ['вайти', 'войти в', 'вти в', 'хорошо', 'ок',
                                                             'купить', 'запишусь', 'как подать заявку',
                                                             'как записаться', 'возьму', 'приобрести',
                                                             'заявку', 'как записаться', 'как приобрести'
                                                             ]):
            user_data[chat_id] = {}
            collecting_data.add(chat_id)
            expected_trigger_response[chat_id] = False  # Сброс состояния ожидания триггера
            await message.reply("Пожалуйста, введите ваши данные в формате: Фамилия Имя Отчество Телефон Email")
            return


        # Проверяем наличие триггеров в тексте сообщения
    triggers = ['на тренинг войти в', 'приобрести курс войти в', 'приобрести тренинг войти в',
               'на курс войти в', 'купить курс войти в', 'купить тренинг войти в']
    if any(trigger in user_input.lower() for trigger in triggers):
        user_data[chat_id] = {}
        collecting_data.add(chat_id)
        await message.reply("Пожалуйста, введите ваши данные в формате: Фамилия Имя Отчество Телефон Email")
        return

    # Сначала пытаемся найти наиболее похожий ключ в базе знаний
    best_match = find_best_match(user_input)
    if best_match:
        response = knowledge_base[best_match]
        await message.reply(response)
        # Устанавливаем ожидание триггера после отправки конкретного сообщения
        if response == "Уточните, пожалуйста, на какой курс Вы хотели бы записаться? Для записи от Вас необходимы ваши полные ФИО, контактный телефон и электронная почта, на которую мы вышлем письмо-приглашение на курс." \
                or response == "Курс Войти в IT, стоит 50 руб."\
                or response == "Стоимость тренинга составляет 50 белорусских рублей.":
            expected_trigger_response[chat_id] = True

    else:
        response = "Данную информацию Вы можете уточнить у менеджеров учебного центра по номерам: +375445465454, +375295465454."
        await message.reply(response)



# Функция для отправки данных в Bitrix24
async def send_to_bitrix24(chat_id):
    lead_data = user_data.pop(chat_id, None)
    if lead_data:
        params = {
            'fields': {
                'TITLE': f"Заявка от клиента: {lead_data.get('last_name', '')} {lead_data.get('first_name', '')} {lead_data.get('middle_name', '')}",
                'NAME': lead_data.get('first_name', ''),
                'LAST_NAME': lead_data.get('last_name', ''),
                'SECOND_NAME': lead_data.get('middle_name', ''),
                'PHONE': [{'VALUE': lead_data.get('phone', ''), 'VALUE_TYPE': 'WORK'}],
                'EMAIL': [{'VALUE': lead_data.get('email', ''), 'VALUE_TYPE': 'WORK'}],
                'COMMENTS': f"ФИО: {lead_data.get('last_name', '')} {lead_data.get('first_name', '')} {lead_data.get('middle_name', '')}\nТелефон: {lead_data.get('phone', '')}\nПочта: {lead_data.get('email', '')}"
            }
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(BITRIX24_WEBHOOK_URL, json=params) as resp:
                if resp.status == 200:
                    await bot.send_message(chat_id, "Ваша заявка успешно отправлена!")
                else:
                    await bot.send_message(chat_id, "Произошла ошибка при отправке заявки. Пожалуйста, попробуйте позже.")
    else:
        await bot.send_message(chat_id, "Не удалось собрать данные для заявки.")

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())


