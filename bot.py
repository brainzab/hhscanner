import os
import time
import logging
import json
import requests
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# Настройка логирования
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = os.environ.get("TELEGRAM_TOKEN", "YOUR_TELEGRAM_TOKEN")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "3600"))  # По умолчанию проверка каждый час
DATA_FILE = "user_data.json"

# Структура данных пользователей
user_data = {}

def load_data():
    """Загрузка данных пользователей из файла"""
    global user_data
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as file:
                user_data = json.load(file)
            logger.info("Данные пользователей загружены")
    except Exception as e:
        logger.error(f"Ошибка при загрузке данных: {e}")
        user_data = {}

def save_data():
    """Сохранение данных пользователей в файл"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as file:
            json.dump(user_data, file, ensure_ascii=False, indent=4)
        logger.info("Данные пользователей сохранены")
    except Exception as e:
        logger.error(f"Ошибка при сохранении данных: {e}")

def init_user_data(user_id):
    """Инициализация данных нового пользователя"""
    if str(user_id) not in user_data:
        user_data[str(user_id)] = {
            "keywords": [],
            "last_check": None,
            "last_vacancies": [],
            "notification_enabled": True,
            "check_interval": CHECK_INTERVAL
        }
        save_data()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    init_user_data(user_id)
    
    await update.message.reply_text(
        "👋 Привет! Я бот для отслеживания вакансий на hh.ru.\n\n"
        "🔍 Чтобы начать поиск, добавьте ключевые слова с помощью команды /add_keywords.\n"
        "📋 Вы можете посмотреть текущие настройки через /settings.\n"
        "ℹ️ Для получения справки используйте /help."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help"""
    help_text = (
        "📚 *Доступные команды:*\n\n"
        "/start - Перезапуск бота\n"
        "/add_keywords - Добавить ключевые слова для поиска\n"
        "/remove_keywords - Удалить ключевые слова\n"
        "/list_keywords - Показать текущие ключевые слова\n"
        "/search - Выполнить поиск вакансий сейчас\n"
        "/settings - Настройки уведомлений\n"
        "/help - Показать эту справку\n\n"
        "🔍 Бот автоматически ищет вакансии в режиме удаленной работы по всем городам и странам."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def add_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /add_keywords"""
    user_id = update.effective_user.id
    init_user_data(user_id)
    
    if not context.args:
        await update.message.reply_text(
            "Укажите ключевые слова через пробел или в кавычках.\n"
            "Пример: /add_keywords python django\n"
            "Или: /add_keywords \"python разработчик\" java"
        )
        return
    
    # Обработка аргументов с учетом кавычек
    new_keywords = []
    current_keyword = ""
    in_quotes = False
    
    for arg in ' '.join(context.args).strip():
        if arg == '"' and not in_quotes:
            in_quotes = True
        elif arg == '"' and in_quotes:
            in_quotes = False
            if current_keyword:
                new_keywords.append(current_keyword.strip())
                current_keyword = ""
        elif in_quotes:
            current_keyword += arg
        elif arg == ' ' and not in_quotes:
            if current_keyword:
                new_keywords.append(current_keyword.strip())
                current_keyword = ""
        else:
            current_keyword += arg
    
    if current_keyword:
        new_keywords.append(current_keyword.strip())
    
    # Добавление ключевых слов
    for keyword in new_keywords:
        if keyword and keyword not in user_data[str(user_id)]["keywords"]:
            user_data[str(user_id)]["keywords"].append(keyword)
    
    save_data()
    
    if new_keywords:
        keywords_list = "\n• ".join(user_data[str(user_id)]["keywords"])
        await update.message.reply_text(
            f"✅ Ключевые слова успешно добавлены!\n\n"
            f"🔍 Текущие ключевые слова:\n• {keywords_list}\n\n"
            f"🔄 Выполняю поиск вакансий..."
        )
        await search_vacancies(update, context)
    else:
        await update.message.reply_text("❌ Не удалось добавить ключевые слова. Проверьте формат ввода.")

async def remove_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /remove_keywords"""
    user_id = update.effective_user.id
    init_user_data(user_id)
    
    if not user_data[str(user_id)]["keywords"]:
        await update.message.reply_text("У вас нет сохраненных ключевых слов.")
        return
    
    keyboard = []
    for keyword in user_data[str(user_id)]["keywords"]:
        keyboard.append([InlineKeyboardButton(f"❌ {keyword}", callback_data=f"remove_{keyword}")])
    
    keyboard.append([InlineKeyboardButton("✅ Готово", callback_data="remove_done")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("Выберите ключевые слова для удаления:", reply_markup=reply_markup)

async def list_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /list_keywords"""
    user_id = update.effective_user.id
    init_user_data(user_id)
    
    if not user_data[str(user_id)]["keywords"]:
        await update.message.reply_text("У вас нет сохраненных ключевых слов. Добавьте их с помощью /add_keywords.")
        return
    
    keywords_list = "\n• ".join(user_data[str(user_id)]["keywords"])
    await update.message.reply_text(f"🔍 Ваши ключевые слова:\n• {keywords_list}")

async def search_vacancies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /search и поиск вакансий"""
    user_id = update.effective_user.id
    init_user_data(user_id)
    
    if not user_data[str(user_id)]["keywords"]:
        await update.message.reply_text(
            "❌ У вас нет сохраненных ключевых слов.\n"
            "Добавьте их с помощью команды /add_keywords."
        )
        return
    
    await update.message.reply_text("🔍 Ищу вакансии на hh.ru...")
    
    # Получаем вакансии для каждого ключевого слова
    all_vacancies = []
    for keyword in user_data[str(user_id)]["keywords"]:
        vacancies = fetch_vacancies(keyword)
        if vacancies:
            all_vacancies.extend(vacancies)
    
    # Удаляем дубликаты
    unique_vacancies = []
    vacancy_ids = set()
    for vacancy in all_vacancies:
        if vacancy["id"] not in vacancy_ids:
            unique_vacancies.append(vacancy)
            vacancy_ids.add(vacancy["id"])
    
    # Сортируем по дате публикации (самые свежие вначале)
    unique_vacancies.sort(key=lambda x: x["published_at"], reverse=True)
    
    # Сохраняем ID вакансий для будущих проверок
    user_data[str(user_id)]["last_vacancies"] = [v["id"] for v in unique_vacancies]
    user_data[str(user_id)]["last_check"] = datetime.now().isoformat()
    save_data()
    
    if not unique_vacancies:
        await update.message.reply_text(
            "🔍 По вашим ключевым словам не найдено вакансий в режиме удаленной работы.\n"
            "Я буду уведомлять вас, когда появятся новые вакансии."
        )
        return
    
    # Отправляем результаты
    await update.message.reply_text(f"🔍 Найдено {len(unique_vacancies)} вакансий:")
    
    # Группируем по 10 вакансий для избежания ограничений Telegram
    chunks = [unique_vacancies[i:i+10] for i in range(0, len(unique_vacancies), 10)]
    
    for chunk in chunks:
        message = ""
        for vacancy in chunk:
            published_date = datetime.fromisoformat(vacancy["published_at"].replace("Z", "+00:00"))
            published_str = published_date.strftime("%d.%m.%Y %H:%M")
            
            salary_info = "Зарплата не указана"
            if vacancy["salary"]:
                from_salary = vacancy["salary"]["from"] if vacancy["salary"]["from"] else ""
                to_salary = vacancy["salary"]["to"] if vacancy["salary"]["to"] else ""
                currency = vacancy["salary"]["currency"] if vacancy["salary"]["currency"] else ""
                
                if from_salary and to_salary:
                    salary_info = f"{from_salary} - {to_salary} {currency}"
                elif from_salary:
                    salary_info = f"от {from_salary} {currency}"
                elif to_salary:
                    salary_info = f"до {to_salary} {currency}"
            
            message += f"[{vacancy['name']}]({vacancy['alternate_url']})\n"
            message += f"🏢 {vacancy['employer']['name']}\n"
            message += f"💰 {salary_info}\n"
            message += f"📅 {published_str}\n\n"
        
        await update.message.reply_text(message, parse_mode="Markdown", disable_web_page_preview=True)
    
    await update.message.reply_text(
        "✅ Поиск завершен! Я буду уведомлять вас о новых вакансиях.\n"
        "Вы можете изменить настройки уведомлений с помощью /settings."
    )

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /settings"""
    user_id = update.effective_user.id
    init_user_data(user_id)
    
    notification_status = "включены" if user_data[str(user_id)]["notification_enabled"] else "выключены"
    check_interval_hours = user_data[str(user_id)]["check_interval"] // 3600
    
    keyboard = [
        [InlineKeyboardButton(
            f"{'🔔' if user_data[str(user_id)]['notification_enabled'] else '🔕'} Уведомления: {notification_status}",
            callback_data="toggle_notifications"
        )],
        [InlineKeyboardButton(f"⏱ Интервал проверки: {check_interval_hours} ч", callback_data="change_interval")],
        [InlineKeyboardButton("✅ Готово", callback_data="settings_done")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("⚙️ Настройки:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик кнопок"""
    query = update.callback_query
    user_id = query.from_user.id
    
    await query.answer()
    
    if query.data.startswith("remove_"):
        keyword = query.data[7:]  # Отрезаем "remove_"
        
        if keyword == "done":
            await query.edit_message_text("✅ Готово!")
            return
        
        if keyword in user_data[str(user_id)]["keywords"]:
            user_data[str(user_id)]["keywords"].remove(keyword)
            save_data()
        
        # Обновляем кнопки
        keyboard = []
        for kw in user_data[str(user_id)]["keywords"]:
            keyboard.append([InlineKeyboardButton(f"❌ {kw}", callback_data=f"remove_{kw}")])
        
        keyboard.append([InlineKeyboardButton("✅ Готово", callback_data="remove_done")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if user_data[str(user_id)]["keywords"]:
            await query.edit_message_text("Выберите ключевые слова для удаления:", reply_markup=reply_markup)
        else:
            await query.edit_message_text("Список ключевых слов пуст.")
    
    elif query.data == "toggle_notifications":
        user_data[str(user_id)]["notification_enabled"] = not user_data[str(user_id)]["notification_enabled"]
        save_data()
        
        notification_status = "включены" if user_data[str(user_id)]["notification_enabled"] else "выключены"
        check_interval_hours = user_data[str(user_id)]["check_interval"] // 3600
        
        keyboard = [
            [InlineKeyboardButton(
                f"{'🔔' if user_data[str(user_id)]['notification_enabled'] else '🔕'} Уведомления: {notification_status}",
                callback_data="toggle_notifications"
            )],
            [InlineKeyboardButton(f"⏱ Интервал проверки: {check_interval_hours} ч", callback_data="change_interval")],
            [InlineKeyboardButton("✅ Готово", callback_data="settings_done")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text("⚙️ Настройки:", reply_markup=reply_markup)
    
    elif query.data == "change_interval":
        intervals = [1, 3, 6, 12, 24]
        keyboard = []
        row = []
        for hours in intervals:
            row.append(InlineKeyboardButton(f"{hours} ч", callback_data=f"set_interval_{hours}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        
        if row:
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("↩️ Назад", callback_data="back_to_settings")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text("⏱ Выберите интервал проверки новых вакансий:", reply_markup=reply_markup)
    
    elif query.data.startswith("set_interval_"):
        hours = int(query.data[13:])  # Отрезаем "set_interval_"
        user_data[str(user_id)]["check_interval"] = hours * 3600
        save_data()
        
        notification_status = "включены" if user_data[str(user_id)]["notification_enabled"] else "выключены"
        
        keyboard = [
            [InlineKeyboardButton(
                f"{'🔔' if user_data[str(user_id)]['notification_enabled'] else '🔕'} Уведомления: {notification_status}",
                callback_data="toggle_notifications"
            )],
            [InlineKeyboardButton(f"⏱ Интервал проверки: {hours} ч", callback_data="change_interval")],
            [InlineKeyboardButton("✅ Готово", callback_data="settings_done")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text("⚙️ Настройки:", reply_markup=reply_markup)
    
    elif query.data == "back_to_settings":
        notification_status = "включены" if user_data[str(user_id)]["notification_enabled"] else "выключены"
        check_interval_hours = user_data[str(user_id)]["check_interval"] // 3600
        
        keyboard = [
            [InlineKeyboardButton(
                f"{'🔔' if user_data[str(user_id)]['notification_enabled'] else '🔕'} Уведомления: {notification_status}",
                callback_data="toggle_notifications"
            )],
            [InlineKeyboardButton(f"⏱ Интервал проверки: {check_interval_hours} ч", callback_data="change_interval")],
            [InlineKeyboardButton("✅ Готово", callback_data="settings_done")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text("⚙️ Настройки:", reply_markup=reply_markup)
    
    elif query.data == "settings_done":
        await query.edit_message_text("✅ Настройки сохранены!")

def fetch_vacancies(keyword):
    """Получение вакансий с hh.ru API"""
    try:
        url = "https://api.hh.ru/vacancies"
        params = {
            "text": keyword,
            "schedule": "remote",  # Удаленная работа
            "per_page": 100,       # Максимальное количество вакансий на страницу
            "order_by": "publication_time"  # Сортировка по дате публикации
        }
        
        headers = {
            "User-Agent": "JobSearchTelegramBot/1.0"
        }
        
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        return data.get("items", [])
    
    except Exception as e:
        logger.error(f"Ошибка при получении вакансий: {e}")
        return []

async def check_new_vacancies(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Проверка новых вакансий и отправка уведомлений"""
    now = datetime.now()
    
    for user_id, data in user_data.items():
        # Проверяем, включены ли уведомления
        if not data["notification_enabled"]:
            continue
        
        # Проверяем, пора ли выполнять проверку
        if data["last_check"]:
            last_check = datetime.fromisoformat(data["last_check"])
            next_check = last_check + timedelta(seconds=data["check_interval"])
            
            if now < next_check:
                continue
        
        # Пропускаем пользователей без ключевых слов
        if not data["keywords"]:
            continue
        
        logger.info(f"Проверка новых вакансий для пользователя {user_id}")
        
        # Получаем вакансии для каждого ключевого слова
        all_vacancies = []
        for keyword in data["keywords"]:
            vacancies = fetch_vacancies(keyword)
            if vacancies:
                all_vacancies.extend(vacancies)
        
        # Удаляем дубликаты
        unique_vacancies = []
        vacancy_ids = set()
        for vacancy in all_vacancies:
            if vacancy["id"] not in vacancy_ids:
                unique_vacancies.append(vacancy)
                vacancy_ids.add(vacancy["id"])
        
        # Сортируем по дате публикации (самые свежие вначале)
        unique_vacancies.sort(key=lambda x: x["published_at"], reverse=True)
        
        # Находим новые вакансии
        new_vacancies = []
        for vacancy in unique_vacancies:
            if vacancy["id"] not in data["last_vacancies"]:
                new_vacancies.append(vacancy)
        
        # Обновляем данные пользователя
        user_data[user_id]["last_vacancies"] = [v["id"] for v in unique_vacancies]
        user_data[user_id]["last_check"] = now.isoformat()
        save_data()
        
        # Отправляем уведомления о новых вакансиях
        if new_vacancies:
            try:
                await context.bot.send_message(
                    chat_id=int(user_id),
                    text=f"🔔 Найдено {len(new_vacancies)} новых вакансий по вашим запросам!"
                )
                
                # Группируем по 10 вакансий для избежания ограничений Telegram
                chunks = [new_vacancies[i:i+10] for i in range(0, len(new_vacancies), 10)]
                
                for chunk in chunks:
                    message = ""
                    for vacancy in chunk:
                        published_date = datetime.fromisoformat(vacancy["published_at"].replace("Z", "+00:00"))
                        published_str = published_date.strftime("%d.%m.%Y %H:%M")
                        
                        salary_info = "Зарплата не указана"
                        if vacancy["salary"]:
                            from_salary = vacancy["salary"]["from"] if vacancy["salary"]["from"] else ""
                            to_salary = vacancy["salary"]["to"] if vacancy["salary"]["to"] else ""
                            currency = vacancy["salary"]["currency"] if vacancy["salary"]["currency"] else ""
                            
                            if from_salary and to_salary:
                                salary_info = f"{from_salary} - {to_salary} {currency}"
                            elif from_salary:
                                salary_info = f"от {from_salary} {currency}"
                            elif to_salary:
                                salary_info = f"до {to_salary} {currency}"
                        
                        message += f"[{vacancy['name']}]({vacancy['alternate_url']})\n"
                        message += f"🏢 {vacancy['employer']['name']}\n"
                        message += f"💰 {salary_info}\n"
                        message += f"📅 {published_str}\n\n"
                    
                    await context.bot.send_message(
                        chat_id=int(user_id),
                        text=message,
                        parse_mode="Markdown",
                        disable_web_page_preview=True
                    )
            
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления пользователю {user_id}: {e}")

def main() -> None:
    """Запуск бота"""
    # Загрузка сохраненных данных
    load_data()
    
    # Создание приложения
    application = Application.builder().token(TOKEN).build()
    
    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("add_keywords", add_keywords))
    application.add_handler(CommandHandler("remove_keywords", remove_keywords))
    application.add_handler(CommandHandler("list_keywords", list_keywords))
    application.add_handler(CommandHandler("search", search_vacancies))
    application.add_handler(CommandHandler("settings", settings))
    
    # Обработчик кнопок
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Запуск периодической проверки новых вакансий
    job_queue = application.job_queue
    job_queue.run_repeating(check_new_vacancies, interval=60, first=10)
    
    # Запуск бота
    application.run_polling()

if __name__ == "__main__":
    main()