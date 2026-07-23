Production-сборка OPC UA Gateway для Astra Linux
=================================================

Portable-папка (как production\OPC_UA_Gateway на Windows): бинарник + _internal,
без установки Python на целевой машине.

Целевая платформа: Astra Linux SE 1.8, x86_64.
Собирать нужно на Astra Linux SE 1.8 x86_64. Сборка на более новой Debian/Ubuntu
может не запуститься на Astra из-за несовместимости glibc.

Быстрый путь на Astra Linux
---------------------------

1. Скопируйте проект на машину сборки Astra.
2. В терминале Astra:

   cd "Astra Linux"
   chmod +x preflight.sh install_system_deps.sh validate_source.sh build.sh smoke_test.sh package_release.sh
   ./preflight.sh
   sudo ./install_system_deps.sh
   ./validate_source.sh
   ./build.sh
   ./smoke_test.sh
   ./package_release.sh

3. Готовый архив для передачи:

   Astra Linux/release/opcua-gateway-astra-se18-x86_64.tar.gz
   Astra Linux/release/opcua-gateway-astra-se18-x86_64.tar.gz.sha256

Автоустановка на целевой Astra (скачать с GitHub)
-------------------------------------------------

  cd "Astra Linux"
  chmod +x install-opc-gateway.sh install_runtime_deps.sh
  sudo ./install-opc-gateway.sh

Или одной командой с GitHub (после первого релиза):

  curl -fsSL "https://raw.githubusercontent.com/HS888888/zzzzzz888/main/Astra%20Linux/install-opc-gateway.sh" -o install-opc-gateway.sh
  chmod +x install-opc-gateway.sh
  sudo ./install-opc-gateway.sh

Подробнее: INSTALL.txt

Проверка на целевой Astra (вручную)
-----------------------------------

1. Сверьте контрольную сумму:

   sha256sum -c opcua-gateway-astra-se18-x86_64.tar.gz.sha256

2. Распакуйте и запустите:

   tar xzf opcua-gateway-astra-se18-x86_64.tar.gz
   cd OPC_UA_Gateway
   ./Запуск.sh

Результат (все варианты)
------------------------
Astra Linux/OPC_UA_Gateway/
  OPC_UA_Gateway   — программа
  _internal/       — библиотеки (.so, Qt WebEngine, asyncua)
  Запуск.sh        — ./Запуск.sh
  README.txt       — для пользователя

Передайте заказчику архив или всю папку OPC_UA_Gateway. Python на целевом ПК не нужен.
На целевой машине должны быть системные библиотеки Qt WebEngine; их отсутствие покажет
`ldd` в `smoke_test.sh`. Список устанавливает `install_system_deps.sh`.
