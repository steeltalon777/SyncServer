# Server Sync API

FastAPI приложение для синхронизации данных между серверами и устройствами. Система предназначена для отслеживания событий, управления устройствами и сайтами.

## 🚀 Быстрый старт

### Предварительные требования
- Python 3.8+
- PostgreSQL (или другая поддерживаемая СУБД)
- Установленный pip

### Установка

1. Клонируйте репозиторий:
```bash
git clone <repository-url>
cd "Server Sync API"
```

2. Создайте виртуальное окружение и активируйте его:
```bash
python -m venv .venv
# Для Windows:
.venv\Scripts\activate
# Для Linux/Mac:
source .venv/bin/activate
```

3. Установите зависимости:
```bash
pip install -r requirements.txt
```

4. Настройте переменные окружения:
```bash
copy .env.example .env
# Отредактируйте .env файл согласно вашей конфигурации
```

5. Запустите приложение:
```bash
uvicorn main:app --reload
```

Приложение будет доступно по адресу: http://localhost:8000

## 📁 Структура проекта

```
Server Sync API/
├── app/                    # Основное приложение
│   ├── core/              # Основные настройки и утилиты
│   │   ├── config.py      # Конфигурация приложения
│   │   ├── db.py          # Настройки базы данных
│   │   └── json_encoder.py # Кастомный JSON энкодер
│   ├── models/            # SQLAlchemy модели
│   │   ├── base.py        # Базовая модель
│   │   ├── device.py      # Модель устройства
│   │   ├── event.py       # Модель события
│   │   ├── site.py        # Модель сайта
│   │   └── __init__.py    # Инициализация моделей
│   ├── repos/             # Репозитории для работы с данными
│   │   ├── device_repo.py # Репозиторий устройств
│   │   ├── event_repo.py  # Репозиторий событий
│   │   └── site_repo.py   # Репозиторий сайтов
│   └── schemas/           # Pydantic схемы
│       └── event.py       # Схемы для событий
├── main.py                # Основной файл приложения
├── requirements.txt       # Зависимости Python
├── .env.example          # Пример переменных окружения
├── .gitignore            # Git ignore файл
└── test_main.http        # HTTP тесты для API
```

## 🗄️ Модели данных

### Устройство (Device)
- **id**: Уникальный идентификатор устройства
- **name**: Название устройства
- **site_id**: Ссылка на сайт
- **created_at**: Время создания
- **updated_at**: Время последнего обновления

### Событие (Event)
- **id**: Уникальный идентификатор события
- **device_id**: Ссылка на устройство
- **event_type**: Тип события
- **data**: Данные события в формате JSON
- **timestamp**: Временная метка события
- **created_at**: Время создания записи

### Сайт (Site)
- **id**: Уникальный идентификатор сайта
- **name**: Название сайта
- **created_at**: Время создания
- **updated_at**: Время последнего обновления

## 🔧 API Эндпоинты

### События (Events)

#### Получить все события
```
GET /events/
```
Параметры:
- `skip`: Количество записей для пропуска (по умолчанию: 0)
- `limit`: Максимальное количество записей (по умолчанию: 100)

#### Создать новое событие
```
POST /events/
```
Тело запроса:
```json
{
  "device_id": 1,
  "event_type": "status_change",
  "data": {"status": "online"},
  "timestamp": "2024-01-01T12:00:00"
}
```

#### Получить событие по ID
```
GET /events/{event_id}
```

#### Удалить событие
```
DELETE /events/{event_id}
```

### Устройства (Devices)

#### Получить все устройства
```
GET /devices/
```

#### Создать новое устройство
```
POST /devices/
```
Тело запроса:
```json
{
  "name": "Device 1",
  "site_id": 1
}
```

#### Получить устройство по ID
```
GET /devices/{device_id}
```

#### Обновить устройство
```
PUT /devices/{device_id}
```

#### Удалить устройство
```
DELETE /devices/{device_id}
```

### Сайты (Sites)

#### Получить все сайты
```
GET /sites/
```

#### Создать новый сайт
```
POST /sites/
```
Тело запроса:
```json
{
  "name": "Main Site"
}
```

#### Получить сайт по ID
```
GET /sites/{site_id}
```

#### Обновить сайт
```
PUT /sites/{site_id}
```

#### Удалить сайт
```
DELETE /sites/{site_id}
```

## ⚙️ Конфигурация

Основные переменные окружения (файл `.env`):

```
DATABASE_URL=postgresql://user:password@localhost/dbname
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

## 🧪 Тестирование

Для тестирования API используйте файл `test_main.http` с HTTP клиентом (например, VS Code REST Client).

Примеры запросов:
```http
### Получить все события
GET http://localhost:8000/events/

### Создать событие
POST http://localhost:8000/events/
Content-Type: application/json

{
  "device_id": 1,
  "event_type": "test",
  "data": {"message": "test event"},
  "timestamp": "2024-01-01T12:00:00"
}
```

## 🛠️ Технологии

- **FastAPI** - Веб-фреймворк для создания API
- **SQLAlchemy** - ORM для работы с базой данных
- **Pydantic** - Валидация данных и сериализация
- **PostgreSQL** - Основная база данных (поддерживаются другие через SQLAlchemy)
- **Uvicorn** - ASGI сервер для запуска приложения

## 📊 Особенности

1. **Автоматическая документация API**: Доступна по адресам:
   - Swagger UI: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

2. **Кастомный JSON энкодер**: Поддержка сериализации datetime объектов

3. **Асинхронная работа**: Все эндпоинты используют async/await

4. **Валидация данных**: Автоматическая валидация входных данных через Pydantic

5. **Обработка ошибок**: Единая система обработки ошибок

## 🔄 Миграции базы данных

Для создания миграций используйте Alembic:

```bash
# Инициализация Alembic
alembic init migrations

# Создание миграции
alembic revision --autogenerate -m "Описание изменений"

# Применение миграций
alembic upgrade head
```

## 🤝 Вклад в проект

1. Форкните репозиторий
2. Создайте ветку для новой функции (`git checkout -b feature/amazing-feature`)
3. Зафиксируйте изменения (`git commit -m 'Add amazing feature'`)
4. Запушьте ветку (`git push origin feature/amazing-feature`)
5. Откройте Pull Request

## 📄 Лицензия

Этот проект лицензируется под MIT License - смотрите файл LICENSE для деталей.

## 📞 Контакты

Для вопросов и предложений создайте issue в репозитории проекта.

---

**Примечание**: Убедитесь, что база данных запущена перед запуском приложения. Для разработки можно использовать SQLite, изменив DATABASE_URL в `.env` файле.