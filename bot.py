import json

import requests
import asyncio
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart

from aiogram.fsm.state import StatesGroup, State
from aiogram.handlers import CallbackQueryHandler
from aiogram.types import Message, ReplyKeyboardMarkup, InlineKeyboardButton, KeyboardButton, ReplyKeyboardRemove, \
    InlineKeyboardMarkup, CallbackQuery
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.fsm.context import FSMContext
from aiogram.utils.chat_action import ChatActionSender

from decouple import config

import admin

bot = Bot(token=config('TOKEN'), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = RedisStorage.from_url(config('REDIS_URL'))
dp = Dispatcher(storage=storage)


class RegistrationForm(StatesGroup):
    name = State()
    phone = State()
    birth_date = State()
    education = State()
    work_place = State()
    personal_data_agreement = State()
    library_rules_agreement = State()


def check_user_registration(telegram_id):
    response = requests.get(f'{config("API_URL")}readers/search_by_telegram_id', params={'telegram_id': telegram_id})
    return response.status_code == 200 and response.json()


@dp.callback_query(F.data.startswith('get_book_'))
async def get_book(call: CallbackQuery):
    await call.answer()
    telegram_id = call.from_user.id
    book_id = int(call.data.replace('get_book_', ''))

    if check_user_registration(telegram_id):
        response = requests.get(f'{config("API_URL")}books/is_available',
                                params={'book_id': book_id, 'telegram_id': telegram_id})
        if response.status_code == 200:
            if response.json().get('detail') == 'Already in the possession of the current reader':
                await call.message.answer('Эта книга уже находится у Вас.')
            if response.json().get('detail') == 'Already in the possession of the another reader':
                await call.message.answer('Эта книга находится у другого читателя')
            if response.json().get('detail') == 'Book is available for issue':
                await call.message.answer(
                    '✅ Ваш заказ принят.\n\n⏳ Ожидайте, через некоторое время библиотекарь ответит Вам.')
                await admin_new_order(book_id, call)
        else:
            await call.message.answer(f'{response.status_code}')
    else:
        await call.message.answer(
            "Вы еще не зарегистрированы. Пожалуйста, пройдите регистрацию, отправив команду /register.")


async def admin_new_order(book_id, call):
    librarians = requests.get(f'{config("API_URL")}users/get_librarians')
    book = requests.get(f'{config("API_URL")}books/search_by_pk', params={'pk': book_id})
    if librarians.status_code == 200 and book.status_code == 200:
        for librarian in librarians.json():
            inline_buttons = [
                [InlineKeyboardButton(text='🌐 Перейти на сайт для просмотра заказа (в разработке)',
                                      url='https://services.pystart.by')],
                [InlineKeyboardButton(text='ℹ️ О читателе', callback_data=f'about_reader_{call.from_user.id}')],
                [InlineKeyboardButton(text='✅ Выдать книгу', callback_data=f'issue_book_{book_id}')],
                [InlineKeyboardButton(text='❌ Отказать', callback_data=f'not_issue_book')],
                [InlineKeyboardButton(text='📝 Написать читателю', url=f'https://t.me/{call.from_user.username}')]
            ]
            inline_keyboard = InlineKeyboardMarkup(inline_keyboard=inline_buttons)

            await bot.send_message(librarian['telegram_id'],
                                   f'❗️❗️❗️<b>НОВЫЙ ЗАКАЗ</b>❗️❗️❗️\n\n'
                                   f'<b>Автор</b>: {book.json()["author"]}\n'
                                   f'<b>Название</b>: {book.json()["title"]}\n'
                                   f'<b>Место издания</b>: {book.json()["pub_place"]}\n'
                                   f'<b>Издательство</b>: {book.json()["publishing"]}\n'
                                   f'<b>Год издания</b>: {book.json()["pub_date"]}\n'
                                   f'<b>Количество страниц</b>: {book.json()["num_pages"]}\n\n'
                                   f'<b>Читатель</b>: {call.from_user.full_name}\n',
                                   reply_markup=inline_keyboard)
        return {'status_code': 200}
    return {'status_code': 400}


@dp.callback_query(F.data.startswith('issue_book_'))
async def issue_book_allowed(call: CallbackQuery):
    await call.answer()
    book_id = int(call.data.replace('issue_book_', ''))
    response = requests.post(f'{config("API_URL")}issues/book_issue/',
                             data={'book_id': book_id, 'reader': call.from_user.id})
    librarians = requests.get(f'{config("API_URL")}users/get_librarians')

    if response.status_code == 201:
        await call.message.answer('✅ Книга одобрена к выдаче. Вам необходимо забрать ее в течение 2 рабочих дней по адресу: г. Гродно, ул. Гагарина, 6.')
        for librarian in librarians.json():
            await bot.send_message(librarian['telegram_id'],
                                   f'✅ Вы одобрили выдачу книги.\n'
                                   f'{call.from_user.full_name} должен забрать ее в течение 2 рабочих дней.')
    else:
        await call.message.answer('Упс... Что-то пошло не так. Попробуйте позже.')
        for librarian in librarians.json():
            await bot.send_message(librarian['telegram_id'],
                                   f'Упс... Что-т пошло не так.\n\n Читателю предложено попробовать позже.\n '
                                   f'Свяжитесь с администратором и назовите ему код ошибки: {response.status_code}')


@dp.callback_query(F.data.startswith('not_issue_book'))
async def issue_book_disallowed(call: CallbackQuery):
    await call.message.answer()
    librarians = requests.get(f'{config("API_URL")}users/get_librarians')
    inline_buttons_reader = [
        [InlineKeyboardButton(text='📝 Написать библиотекарю', url=f'tg://user?id={librarians.json()[0]["telegram_id"]}')]
    ]
    inline_keyboard_reader = InlineKeyboardMarkup(inline_keyboard=inline_buttons_reader)
    await call.message.answer('❌ Вам отказано в выдаче данной книги. Попробуйте позже или свяжитесь с библиотекарем',
                              reply_markup=inline_keyboard_reader)


    inline_buttons_librarian = [
        [InlineKeyboardButton(text='📝 Написать читателю', url=f'https://t.me/{call.from_user.username}')]
    ]
    inline_keyboard_librarian = InlineKeyboardMarkup(inline_keyboard=inline_buttons_librarian)
    for librarian in librarians.json():
        await bot.send_message(librarian['telegram_id'],
                               f'Вы отказали в выдаче книги. Вы можете написать причину отказа читателю', reply_markup=inline_keyboard_librarian)


@dp.callback_query(F.data.startswith('about_reader_'))
async def about_reader(call: CallbackQuery):
    await call.answer()
    reader_id = call.data.replace('about_reader_', '')
    response = requests.get(f'{config("API_URL")}readers/search_by_telegram_id',
                            params={'telegram_id': call.from_user.id})
    if response.status_code == 200:
        reader = response.json()
        inline_buttons = [
            [InlineKeyboardButton(text='📖 Сейчас читает (в разработке)',
                                  callback_data=f'reader_books_now_{reader_id}')],
            [InlineKeyboardButton(text='📚 Читал ранее (в разработке)',
                                  callback_data=f'reader_books_history_{reader_id}')],
        ]
        inline_keyboard = InlineKeyboardMarkup(inline_keyboard=inline_buttons)

        await call.message.answer(f'<b>ℹ️ Информация о читателе\n\n</b>'
                                  f'<b>Имя:</b> {reader["name"]}\n'
                                  f'<b>Номер телефона:</b> {reader["phone"]}\n'
                                  f'<b>Дата рождения:</b> {datetime.fromisoformat(reader["birth_date"]).strftime("%d.%m.%Y")}\n'
                                  f'<b>Возраст:</b> {(datetime.now().date()).year - (datetime.strptime(reader["birth_date"], "%Y-%m-%d").date()).year}\n'
                                  f'<b>Образование:</b> {reader["education"]}\n'
                                  f'<b>Место работы:</b> {reader["work_place"]}\n'
                                  f'<b>Дата регистрации:</b> {datetime.fromisoformat(reader["date_create"]).strftime("%d.%m.%Y")}\n',
                                  reply_markup=inline_keyboard)


@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    telegram_id = message.from_user.id
    if check_user_registration(telegram_id):
        await message.answer(f"Добро пожаловать в библиотеку ГрОИРО, {message.from_user.first_name}!")
    else:
        await message.answer(
            "Добро пожаловать в библиотеку! Вы еще не зарегистрированы. "
            "Пожалуйста, пройдите регистрацию, отправив команду /register.")


@dp.message(Command('register'))
async def register_reader(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    if check_user_registration(telegram_id):
        await message.answer('Вы уже зарегистрированы.')
    else:
        await message.answer('Введите Ваше имя, отчество и фамилию:')
        await state.set_state(RegistrationForm.name)


@dp.message(RegistrationForm.name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)

    await message.answer('Введите дату рождения в формате ДД.ММ.ГГГГ (например, 18.06.1993):')
    await state.set_state(RegistrationForm.birth_date)


@dp.message(RegistrationForm.birth_date)
async def process_birth_date(message: types.Message, state: FSMContext):
    await state.update_data(birth_date=message.text)
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text='Отправить номер телефона', request_contact=True)]],
        resize_keyboard=True)
    await message.answer('Пожалуйста, нажмите кнопку, чтобы отправить свой номер телефона', reply_markup=keyboard)
    await state.set_state(RegistrationForm.phone)


@dp.message(RegistrationForm.phone)
async def process_phone(message: types.Message, state: FSMContext):
    if message.contact:
        phone = message.contact.phone_number
        await state.update_data(phone=phone)
        await message.answer(f'Ваш номер телефона: {phone}')
    else:
        await message.answer('Пожалуйста, используйте кнопку для отправки номера телефона.')

    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text='Высшее')],
        [KeyboardButton(text='Среднее специальное')],
        [KeyboardButton(text='Профессионально-техническое')],
        [KeyboardButton(text='Общее среднее')]
    ], resize_keyboard=True)
    await message.answer("Укажите Ваше образование:", reply_markup=keyboard)
    await state.set_state(RegistrationForm.education)


@dp.message(RegistrationForm.education)
async def process_education(message: types, state: FSMContext):
    await state.update_data(education=message.text)

    await message.answer('Укажите название организации, в которой Вы работаете:',
                         reply_markup=ReplyKeyboardRemove())
    await state.set_state(RegistrationForm.work_place)


@dp.message(RegistrationForm.work_place)
async def process_work_place(message: types, state: FSMContext):
    await state.update_data(work_place=message.text)

    keyboard = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Я согласен с условиями Политики')]],
                                   resize_keyboard=True)
    await message.answer('Ознакомьтесь с Политикой обработки персональных данных, действующей в институте',
                         reply_markup=keyboard)
    await state.set_state(RegistrationForm.personal_data_agreement)


@dp.message(RegistrationForm.personal_data_agreement)
async def process_personal_data_agreement(message: types, state: FSMContext):
    await state.update_data(personal_data_agreement=True)

    keyboard = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Я согласен с правилами библиотеки')]],
                                   resize_keyboard=True, one_time_keyboard=True)
    await message.answer('Ознакомьтесь с Правилами библиотеки', reply_markup=keyboard)
    await state.set_state(RegistrationForm.library_rules_agreement)


@dp.message(RegistrationForm.library_rules_agreement)
async def process_library_rules_agreement(message: types, state: FSMContext):
    await state.update_data(library_rules_agreement=True)

    user_data = await state.get_data()

    payload = {
        'telegram_id': message.from_user.id,
        'name': user_data['name'],
        'phone': user_data['phone'],
        'birth_date': datetime.strptime((user_data['birth_date']), '%d.%m.%Y').strftime('%Y-%m-%d'),
        'education': user_data['education'],
        'work_place': user_data['work_place'],
        'personal_data_agreement': user_data['personal_data_agreement'],
        'library_rules_agreement': user_data['library_rules_agreement']
    }

    response = requests.post(f'{config("API_URL")}readers/', data=payload)

    if response.status_code == 201:
        await message.answer('Вы успешно зарегистрированы как читатель.', reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer(
            f'Произошла ошибка при регистрации {response.status_code}. Обратитесь к администратору')

    await state.clear()


@dp.message(Command('last_books'))
async def books(message: Message):
    last_books = requests.get(f'{config("API_URL")}last_books/')
    if last_books.status_code == 200:
        last_books = last_books.json()
        inline_buttons = []
        for book in last_books:
            inline_buttons.append(
                [InlineKeyboardButton(text=f'{book["author"]} - {book["title"]}',
                                      callback_data=f'detail_{book['id']}')]
            )
        inline_keyboard = InlineKeyboardMarkup(inline_keyboard=inline_buttons, )
        async with ChatActionSender(bot=bot, chat_id=message.from_user.id, action='typing'):
            await asyncio.sleep(2)
            await message.answer('Вот последние 5 книг в нашей библиотеке:', reply_markup=inline_keyboard)


@dp.callback_query(F.data.startswith('detail_'))
async def view_book(call: CallbackQuery):
    await call.answer()
    book_id = int(call.data.replace('detail_', ''))
    book = requests.get(f'{config("API_URL")}books/search_by_pk', params={'pk': book_id})
    if book.status_code == 200:
        book = book.json()
        inline_kb_list = [
            [InlineKeyboardButton(text='Я хочу взять эту книгу', callback_data=f'get_book_{book_id}')],
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=inline_kb_list)
        async with ChatActionSender(bot=bot, chat_id=call.from_user.id, action='typing'):
            await asyncio.sleep(2)
            await call.message.answer(
                f'<b>Автор</b>: {book["title"]}\n'
                f'<b>Название</b>: {book["author"]}\n'
                f'<b>Место издания</b>: {book["pub_place"]}\n'
                f'<b>Издательство</b>: {book["publishing"]}\n'
                f'<b>Год издания</b>: {book["pub_date"]}\n'
                f'<b>Количество страниц</b>: {book["num_pages"]}', reply_markup=keyboard
            )


@dp.message(Command('my_books'))
async def my_books(message: Message):
    telegram_id = message.from_user.id
    if check_user_registration(telegram_id):
        response = requests.get(f'{config("API_URL")}issues/get_readers_books', params={'telegram_id': telegram_id})
        if response.status_code == 200:
            books = response.json()
            not_returned = '<b>Эти книги сейчас находятся у Вас:</b>\n\n'
            for book in books:
                if not book['is_return']:
                    not_returned += (f'<b>Название:</b> {book["book_title"]}\n'
                                     f'<b>Дата выдачи:</b> {datetime.fromisoformat(book["issue_date"]).strftime("%d.%m.%Y")}\n'
                                     f'------------------------------------\n')

            inline_kb_list = [
                [InlineKeyboardButton(text='Какие книги я брал(а) раньше?', callback_data='history_issues')],
            ]
            keyboard = InlineKeyboardMarkup(inline_keyboard=inline_kb_list)

            if not_returned == '<b>Эти книги сейчас находятся у Вас:</b>\n\n':
                await message.answer(
                    'Сейчас у Вас нет книг.\n'
                    'Вы можете посмотреть последние поступившие книги при помощи '
                    'команды /last_books или воспользоваться поиском - /search', reply_markup=keyboard)
            else:
                await message.answer(not_returned, reply_markup=keyboard)

        elif response.status_code == 404 and response.json().get(
                'detail') == "No books were found for the current user.":
            await message.answer(
                'Вы еще не брали книги.\n'
                'Вы можете посмотреть последние поступившие книги при помощи '
                'команды /last_books или воспользоваться поиском - /search')
        else:
            await message.answer(f'{response.status_code}')


@dp.callback_query(F.data == 'history_issues')
async def history_issues(call: CallbackQuery):
    await call.answer()
    telegram_id = call.from_user.id
    if check_user_registration(telegram_id):
        response = requests.get(f'{config("API_URL")}issues/get_readers_books', params={'telegram_id': telegram_id})
        if response.status_code == 200:
            books = response.json()
            returned = '<b>Эти книги Вы брали раньше:</b>\n\n'
            for book in books:
                if book['is_return']:
                    returned += (f'Название: {book["book_title"]}\n'
                                 f'Дата выдачи: {datetime.fromisoformat(book["issue_date"]).strftime("%d.%m.%Y")}\n'
                                 f'------------------------------------\n')
            if returned == '<b>Эти книги Вы брали раньше:</b>\n\n':
                await call.message.answer(
                    'Вы еще не брали книги.\nВы можете посмотреть последние поступившие книги при помощи '
                    'команды /last_books или воспользоваться поиском - /search')
            else:
                await call.message.answer(returned)
        elif response.status_code == 404 and response.json().get(
                'detail') == "No books were found for the current user.":
            await call.message.answer('Вы еще не брали книги.\n'
                                      'Вы можете посмотреть последние поступившие книги при помощи '
                                      'команды /last_books или воспользоваться поиском - /search')
        else:
            await call.message.answer(f'{response.status_code}')


class SearchState(StatesGroup):
    waiting_for_query = State()


@dp.message(Command('search'))
async def search(message: Message, state: FSMContext):
    await message.answer('Введите фамилию автора, название книги (можно не полностью)...')
    await state.set_state(SearchState.waiting_for_query)


@dp.message(SearchState.waiting_for_query)
async def perform_search(message: Message, state: FSMContext):
    query = message.text
    response = requests.get(f'{config("API_URL")}books/search', params={'query': query})
    if response.status_code == 200:
        books = response.json()
        inline_kb_list = []
        for book in books:
            inline_kb_list.append([InlineKeyboardButton(text=f'{book["author"]} - {book["title"]}',
                                                        callback_data=f'detail_{book['id']}')])

        keyboard = InlineKeyboardMarkup(inline_keyboard=inline_kb_list)
        await message.answer('<b>Вот, что мы нашли по Вашему запросу:</b>\n\n'
                             '<i>Нажмите на книгу для детального просмотра</i>', reply_markup=keyboard)
    await state.clear()


async def main():
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == '__main__':
    asyncio.run(main())
