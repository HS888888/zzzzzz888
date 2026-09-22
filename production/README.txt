Production-сборка OPC UA Gateway
================================

Как собрать portable-версию (exe + DLL) для передачи заказчику:

1. Установите Python 3.11+ и добавьте python в PATH.
2. Из корня проекта запустите:

   build_exe.bat

3. Готовая папка:

   production\MS SERVICE\

   Содержимое:
   - MS SERVICE.exe       — программа
   - _internal\           — все библиотеки (DLL, PySide6, asyncua…)
   - Запуск.vbs           — запуск без окна терминала
   - README.txt           — инструкция для пользователя

4. Скопируйте всю папку production\OPC_UA_Gateway\ на другой ПК
   (флешка, архив ZIP). Python на целевом ПК не нужен.

Примечание: папка production\OPC_UA_Gateway\ пересобирается при каждом build_exe.bat
и не хранится в git.

Сборка выполняется во временной папке %TEMP%\OPC_UA_Gateway_build\ (ASCII-путь),
чтобы PyInstaller стабильно работал, если проект лежит в каталоге с кириллицей в пути.
