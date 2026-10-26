# 🗑️ Разбор `shredder.py` и `timer.py` — Затирка данных, Win+V и таймер

Эти два модуля отвечают за гарантированное уничтожение секретов из памяти компьютера.

---

## 🗑️ Часть 1: `ghostclip/shredder.py` — Затирка буфера и очистка Win+V

### 1. Почему простой очистки буфера недостаточно?

Начиная с Windows 10, в операционной системе появился встроенный журнал `Win + V`. Если программа очищает только текущий буфер обмена (`EmptyClipboard`), **все скопированные пароли, токены и номера карт продолжают лежать в системной истории Windows** и даже синхронизируются через облако Microsoft!

Чтобы очистить этот журнал, GhostClip отправляет вызов официальному API среды выполнения Windows (WinRT):

```python
CREATE_NO_WINDOW = 0x08000000  # Системный флаг Windows: не показывать окно консоли

def wipe_win_v_history() -> bool:
    # Команда вызывает класс DataTransfer.Clipboard из Windows Runtime API:
    cmd = (
        "[Windows.ApplicationModel.DataTransfer.Clipboard,"
        "Windows.ApplicationModel.DataTransfer,ContentType=WindowsRuntime]::ClearHistory()"
    )
    try:
        # Запускаем команду бесшумно:
        # creationflags=CREATE_NO_WINDOW гарантирует, что на экране не моргнет черное окно PowerShell!
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True,
            timeout=5,
            creationflags=CREATE_NO_WINDOW,
        )
        return res.returncode == 0
    except Exception:
        return False
```

---

### 2. Затирка буфера текстом-заглушкой: `shred_clipboard`

Если просто очистить буфер, то при попытке вставки (`Ctrl + V`) приложение ничего не вставит, но вредоносные программы или остатки в памяти могут попытаться вытащить предыдущее содержимое.

Функция `shred_clipboard` сначала **перезаписывает буфер текстом**, чтобы гарантировать, что в памяти не осталось ни одной секретной цифры:

```python
OVERWRITE_DUMMY_TEXT = "[GHOSTCLIP: СЕКРЕТ ЗАТЕРТ. ВСЕ ЦИФРЫ УНИЧТОЖЕНЫ]"

def shred_clipboard(dummy_text: str = OVERWRITE_DUMMY_TEXT) -> Tuple[bool, bool]:
    # 1. Записываем в буфер защитный текст вместо номера карты или пароля:
    write_clipboard_text(dummy_text)
    # 2. Очищаем память текущего буфера:
    clip_ok = wipe_clipboard()
    # 3. Полностью сносим системный журнал Win+V:
    hist_ok = wipe_win_v_history()
    return clip_ok, hist_ok
```

---

## ⏳ Часть 2: `ghostclip/timer.py` — Таймер самоуничтожения секретов

Когда пользователь скопировал пароль или токен, ему нужно время, чтобы вставить его в нужное поле. Но оставлять пароль в буфере на часы опасно.

Класс `GhostTimer` запускает обратный отсчет на **45 секунд**.

### Как решена проблема состояния гонки (Race Condition)? Механизм эпох (`_epoch`)

Представьте ситуацию:
1. В 12:00:00 пользователь скопировал Пароль №1. Таймер запустился на 45 секунд.
2. В 12:00:35 (через 35 секунд) пользователь скопировал Пароль №2.
3. Если бы мы просто спали в потоке, то через 10 секунд (в 12:00:45) старый поток стёр бы только что скопированный Пароль №2!

Чтобы этого не произошло, используется **счётчик эпох (`self._epoch`)**:

```python
class GhostTimer:
    def __init__(self):
        self._lock = threading.Lock()
        self._epoch = 0           # Номер текущей «эпохи»
        self._remaining = 0
        self._armed = False

    def arm(self, seconds: int, desc: str, on_expire=None):
        with self._lock:
            # При КАЖДОМ новом секрете номер эпохи увеличивается на 1:
            self._epoch += 1
            current_epoch = self._epoch
            self._remaining = seconds
            self._armed = True
            self._desc = desc
            self._on_expire = on_expire

        # Запускаем отсчет в фоновом потоке, передав ему номер ЕГО эпохи:
        threading.Thread(
            target=self._countdown_loop,
            args=(current_epoch, seconds),
            daemon=True,
        ).start()

    def _countdown_loop(self, epoch: int, total_seconds: int):
        for sec in range(total_seconds, 0, -1):
            with self._lock:
                # 💡 ПРОВЕРКА ЭПОХИ: если пользователь скопировал новый секрет,
                # self._epoch изменился! Старый поток мгновенно завершается и ничего не трогает!
                if not self._armed or self._epoch != epoch:
                    return
                self._remaining = sec

            time.sleep(1.0)

        with self._lock:
            if not self._armed or self._epoch != epoch:
                return
            self._armed = False

        # ВРЕМЯ ВЫШЛО: Уничтожаем данные в буфере и истории Win+V!
        wipe_clipboard()
        if config.wipe_win_v:
            wipe_win_v_history()
```
