# OPC UA Gateway (Windows)

Краткая инструкция по запуску: **[index.html](index.html)** (офлайн HTML5, открывается в браузере).

Настольное Windows-приложение с **нативным GUI (PySide6 / Qt)** для настройки и запуска OPC UA шлюза. Шлюз читает переменные с ПЛК ОВЕН210 и публикует их на локальном OPC UA сервере.

## Требования

- Windows 10/11
- Python 3.11 или новее (для разработки / запуска из исходников)
- Сетевой доступ к OPC UA endpoints ПЛК (порт 4840)

## Быстрый старт (Python)

1. Откройте терминал в папке `OPC_UA_Gateway`.
2. (Опционально) Создайте виртуальное окружение:

   ```bat
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. Установите зависимости:

   ```bat
   pip install -r requirements.txt
   ```

4. Запустите приложение:

   ```bat
   run.bat
   ```

   Или напрямую:

   ```bat
   python app.py
   ```

   Откроется **окно на рабочем столе** — браузер не используется.

## Интерфейс

Окно содержит:

1. **Схему архитектуры** — 3× ПЛК ОВЕН210 (зелёные) → шлюз Windows (жёлтый) → клиент заказчика (фиолетовый), как в `opcua-gateway/index.html`.
2. **Настройки ПЛК** — URL (`opc.tcp://192.168.1.10:4840` и т.д.), NodeId и локальные имена переменных для каждого из 3 ПЛК.
3. **Локальный сервер** — порт (по умолчанию `4841`), namespace URI, папка, интервалы опроса и переподключения.
4. **Кнопки** — «Сохранить», «Запустить шлюз», «Остановить», **«Тест / Эмулятор»**, **«Остановить тест»**.
5. **Журнал** — прокручиваемая панель с сообщениями runtime.

Настройки сохраняются в `settings.json` рядом с приложением (или рядом с `.exe` после сборки). **Перед первым запуском или после изменения настроек нажмите «Сохранить»** — без сохранения кнопка «Запустить шлюз» заблокирована..

## Сборка production (exe + DLL)

1. Установите Python 3.11+ и добавьте `python` в PATH.
2. Запустите:

   ```bat
   build_exe.bat
   ```

3. Результат: **`production\OPC_UA_Gateway\`** — portable-папка для передачи заказчику:
   - `OPC_UA_Gateway.exe` — окно приложения (без консоли)
   - `_internal\` — все библиотеки (DLL, PySide6, Qt WebEngine, asyncua)
   - `Запуск.bat` — запуск для пользователя
   - `README.txt` — краткая инструкция

Скопируйте **всю папку** `production\OPC_UA_Gateway\` на другой ПК (USB, ZIP). Python не нужен.  
`settings.json` и `logs\` создаются **рядом с exe** при работе программы.

Подробнее для разработчика: [`production/README.txt`](production/README.txt).

Ручная сборка:

```bat
pip install -r requirements.txt
pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean build_exe.spec
xcopy dist\OPC_UA_Gateway production\OPC_UA_Gateway\ /E /I /Y
```

## Сборка для Astra Linux (portable)

Целевая платформа: **Astra Linux SE 1.8 x86_64**. Сборку выполняйте именно на
машине с Astra SE 1.8: сборка на более новой Linux-системе может не запуститься
из-за несовместимости glibc и Qt WebEngine.

1. Скопируйте проект на Astra Linux.
2. Проверьте среду и установите системные пакеты:

   ```bash
   cd "Astra Linux"
   chmod +x preflight.sh install_system_deps.sh validate_source.sh build.sh smoke_test.sh package_release.sh
   ./preflight.sh
   sudo ./install_system_deps.sh
   ./validate_source.sh
   ```

3. Соберите и проверьте portable-папку:

   ```bash
   ./build.sh
   ./smoke_test.sh
   ./package_release.sh
   ```

4. Результат: **`Astra Linux/OPC_UA_Gateway/`** — аналог Windows `production`:
   - `OPC_UA_Gateway` — исполняемый файл
   - `_internal/` — библиотеки (.so, PySide6, Qt WebEngine, asyncua)
   - `Запуск.sh` — запуск для пользователя
   - `README.txt` — краткая инструкция

Для передачи используйте архив
`Astra Linux/release/opcua-gateway-astra-se18-x86_64.tar.gz` и файл контрольной
суммы `.sha256`, либо скопируйте **всю папку** на другой ПК с Astra Linux. Python не нужен.  
`settings.json` и `logs/` создаются **рядом с бинарником** при работе программы.

Подробнее: [`Astra Linux/README.txt`](Astra%20Linux/README.txt).

WSL/Docker на Windows можно использовать только для предварительной проверки. Для
поставки на Astra SE 1.8 собирайте и проверяйте выпуск на Astra SE 1.8.

Запуск из исходников на Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

## Структура проекта

```
OPC_UA_Gateway/
├── app.py                 # Точка входа (PySide6 GUI)
├── gui_app.py             # Окно приложения, схема, кнопки, журнал (PySide6)
├── gateway.py             # OpcUaGateway (asyncua client + server)
├── emulator_service.py    # Встроенный эмулятор fake ПЛК (фоновый поток)
├── config_manager.py      # Загрузка/сохранение settings.json, defaults
├── requirements.txt       # asyncua, PySide6
├── requirements-build.txt # pyinstaller
├── run.bat                # Запуск из Python
├── build_exe.bat          # Сборка production\OPC_UA_Gateway\
├── build_exe.spec         # PyInstaller onedir (exe + _internal DLL)
├── production/            # Windows production (см. production/README.txt)
│   └── packaging/         # Запуск.bat и README для копирования в сборку
├── Astra Linux/           # Сборка для Astra Linux (см. Astra Linux/README.txt)
│   ├── build.sh           # PyInstaller onedir → OPC_UA_Gateway/
│   ├── build_linux.spec
│   └── packaging/         # Запуск.sh и README для пользователя
├── emulator/              # Эмулятор ПЛК для тестов без ОВЕН (см. emulator/README.md)
├── README.md
└── .gitignore
```

## Настройки по умолчанию

Если `settings.json` отсутствует, подставляются 3 ПЛК (как в `opcua-gateway/config.json`):

| ПЛК | URL |
|-----|-----|
| BHK1_PLC1 | `opc.tcp://192.168.1.10:4840` |
| BHK1_PLC2 | `opc.tcp://192.168.1.11:4840` |
| BHK1_PLC3 | `opc.tcp://192.168.1.12:4840` |

Локальный сервер: `opc.tcp://0.0.0.0:4841`, папка `GatewayData`, опрос 2 с, переподключение 5 с.

## Встроенный тест

Отдельные терминалы для эмулятора **не нужны** — тест запускается из окна приложения.

1. Нажмите **«Тест / Эмулятор»** на панели инструментов.
2. Программа в фоне:
   - запускает 3 fake ПЛК на `127.0.0.1:4840`, `4842`, `4844`;
   - подставляет тестовые адреса в настройки и **автоматически сохраняет** `settings.json`;
   - показывает сообщение «Применены тестовые адреса localhost»;
   - запускает шлюз (если он уже работал — сначала спросит о перезапуске);
   - ждёт подключения и проверяет данные (статус ПЛК + чтение переменных с `:4841`).
3. Результат — окно **«Тест пройден»** или **«Тест не пройден»**; подробности — в журнале.
4. Пока идёт проверка, статус **«Тестирование…»**; на схеме блоки должны стать зелёными при успехе.
5. **«Остановить тест»** — останавливает эмулятор и шлюз (кнопка активна, пока эмулятор работает).

NodeId на fake ПЛК: `ns=2;i=1001` (Temperature), `ns=2;i=1002` (Pressure) — как у реальных ОВЕН210.

Папка [`emulator/`](emulator/README.md) по-прежнему доступна для ручного запуска из терминала, но основной сценарий — кнопка в GUI.

## Тест без реальных ПЛК (эмулятор, терминал)

Папка [`emulator/`](emulator/README.md) — три fake OPC UA сервера на `127.0.0.1:4840/4842/4844` для проверки GUI и шлюза без ОВЕН210. **Рекомендуется встроенный тест** (см. выше). Альтернатива: терминал 1 — `emulator\run_emulator.bat`, терминал 2 — `run.bat` (сохранить localhost URL, запустить шлюз), терминал 3 — `emulator\run_check.bat` или зелёные индикаторы на схеме.

## Устранение неполадок

- **Python not found** — установите с [python.org](https://www.python.org/downloads/) и включите «Add Python to PATH».
- **Ошибки подключения** — проверьте IP ПЛК, firewall и OPC UA порт 4840.
- **Порт 4841 занят** — измените локальный порт в окне приложения, если другой OPC UA сервер уже использует его.
