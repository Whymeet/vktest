# Быстрый доступ к логам планировщика

## Команды для просмотра логов (в Docker)

### 1. Логи Docker контейнера (самое простое)

```bash
# Логи конкретного планировщика (замените USER_ID на ID пользователя)
docker logs -f --tail 100 vkads-scheduler-USER_ID

# Все логи backend
docker logs -f vkads-backend

# Логи за последний час
docker logs --since 1h vkads-backend
```

### 2. Файловые логи (детальная информация)

```bash
# Основной лог планировщика (с именем пользователя)
tail -f logs/scheduler/scheduler_USERNAME_20251217.log

# События в JSON формате
tail -f logs/scheduler/events_USERNAME.jsonl | jq .

# Общий файл событий (все пользователи)
tail -f logs/scheduler/scheduler_events.log
```

### 3. Логи процессов (полный stdout/stderr)

```bash
# Список всех логов процессов пользователя
ls -lht logs/scheduler/process_logs/USERNAME/

# Последний stderr (ошибки)
ls -t logs/scheduler/process_logs/USERNAME/*_stderr.log | head -1 | xargs cat

# Последний stdout
ls -t logs/scheduler/process_logs/USERNAME/*_stdout.log | head -1 | xargs cat

# Метаданные последнего запуска
ls -t logs/scheduler/process_logs/USERNAME/*_meta.txt | head -1 | xargs cat
```

## Поиск проблем

### Найти отключения планировщика

```bash
# В основном логе
grep "отключен\|DISABLED" logs/scheduler/scheduler_USERNAME_*.log

# В событиях
grep "SCHEDULER_DISABLED\|SCHEDULER_STOPPED" logs/scheduler/events_USERNAME.jsonl | jq .
```

### Найти ошибки с кодом -9 (OOM - нехватка памяти)

```bash
# В логах планировщика
grep "код -9\|SIGKILL\|OOM" logs/scheduler/scheduler_USERNAME_*.log

# Все файлы с ошибкой -9
ls logs/scheduler/process_logs/USERNAME/*_rc-9_*.log

# Метаданные всех ошибок -9
cat logs/scheduler/process_logs/USERNAME/*_rc-9_meta.txt
```

### Найти все ошибки анализа

```bash
# Последние 20 ошибок
grep "ANALYSIS_FAILED" logs/scheduler/events_USERNAME.jsonl | tail -20 | jq .

# Статистика по типам ошибок
grep "ANALYSIS_FAILED" logs/scheduler/events_USERNAME.jsonl | jq -r .error_type | sort | uniq -c
```

### Проверить, почему планировщик остановился

```bash
# Последняя остановка
grep "SCHEDULER_STOPPED" logs/scheduler/events_USERNAME.jsonl | tail -1 | jq .

# История всех остановок
grep "SCHEDULER_STOPPED" logs/scheduler/events_USERNAME.jsonl | jq -r '[.timestamp, .stop_reason, .message] | @tsv'
```

## Зайти в Docker контейнер

```bash
# Зайти в контейнер backend
docker exec -it vkads-backend /bin/bash

# Внутри контейнера перейти в логи
cd /app/logs/scheduler
ls -lh
```

## Мониторинг в реальном времени

```bash
# Следить за событиями в реальном времени (красиво)
tail -f logs/scheduler/events_USERNAME.jsonl | jq -r '[.timestamp, .event_type, .message] | @tsv'

# Только ошибки
tail -f logs/scheduler/scheduler_USERNAME_*.log | grep -E "ERROR|FAILED|SIGKILL"

# Следить за Docker логами + файловыми логами одновременно
# Терминал 1:
docker logs -f vkads-scheduler-USER_ID

# Терминал 2:
tail -f logs/scheduler/scheduler_USERNAME_*.log
```

## Примеры анализа

### Проанализировать последний провал

```bash
# Найти последний провальный запуск
LAST_FAIL=$(ls -t logs/scheduler/process_logs/USERNAME/*_rc-9_meta.txt 2>/dev/null | head -1)

if [ -n "$LAST_FAIL" ]; then
    echo "=== МЕТАДАННЫЕ ==="
    cat "$LAST_FAIL"

    echo -e "\n=== STDERR (последние 50 строк) ==="
    cat "${LAST_FAIL/_meta.txt/_stderr.log}" 2>/dev/null | tail -50

    echo -e "\n=== STDOUT (последние 50 строк) ==="
    cat "${LAST_FAIL/_meta.txt/_stdout.log}" 2>/dev/null | tail -50
else
    echo "Нет провальных запусков"
fi
```

### Статистика за день

```bash
# Количество запусков
grep "ANALYSIS_STARTED" logs/scheduler/events_USERNAME.jsonl | wc -l

# Количество успехов
grep "ANALYSIS_SUCCESS" logs/scheduler/events_USERNAME.jsonl | wc -l

# Количество провалов
grep "ANALYSIS_FAILED" logs/scheduler/events_USERNAME.jsonl | wc -l

# Среднее время выполнения успешных анализов
grep "ANALYSIS_SUCCESS" logs/scheduler/events_USERNAME.jsonl | jq -r .elapsed_seconds | awk '{s+=$1; c++} END {print s/c " сек"}'
```

## Очистка старых логов

```bash
# Удалить логи процессов старше 7 дней
find logs/scheduler/process_logs/ -type f -mtime +7 -delete

# Удалить старые ежедневные логи (старше 30 дней)
find logs/scheduler/ -name "scheduler_*_*.log" -mtime +30 -delete
```

## Экспорт логов

```bash
# Экспорт логов за сегодня
TODAY=$(date +%Y%m%d)
tar -czf scheduler_logs_$TODAY.tar.gz logs/scheduler/

# Экспорт только событий
cp logs/scheduler/events_USERNAME.jsonl ~/events_backup_$TODAY.jsonl
```

## Переменные окружения (если нужно настроить)

В docker-compose.yml или .env:

```yaml
VK_ADS_USER_ID=1              # ID пользователя из БД
VK_ADS_USERNAME=admin         # Имя пользователя (будет в названиях файлов)
```

## Структура имен файлов логов процессов

Формат: `{timestamp}_{run_type}_{extra}_rc{code}_{type}.log`

Примеры:
- `20251217_143521_основной_rc0_stdout.log` - успешный основной анализ
- `20251217_143724_расширенный_plus29d_rc-9_stderr.log` - провальный расширенный анализ с +29 дней, код ошибки -9
- `20251217_143724_расширенный_plus29d_rc-9_meta.txt` - метаданные этого запуска

Где:
- `20251217_143521` - дата и время запуска
- `основной`/`расширенный` - тип анализа
- `plus29d` - дополнительные дни (если есть)
- `rc-9` - return code процесса (-9 = SIGKILL)
- `stdout`/`stderr`/`meta` - тип файла
