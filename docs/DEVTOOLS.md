# Інструменти розробника

## Оверлей (F3)

Показує API та адаптер, FPS, середній/p99/максимальний час кадру, графік останніх 240 кадрів з лініями 16.7 і 33.3 мс, середній час стадій (update, draw, cull, upload, shadow, scene, ui, submit, present), кількість об'єктів, draw-викликів, трикутників, джерел світла, мешів і слотів. Запуск одразу з оверлеєм: `python main.py --overlay` або `LYSYK_OVERLAY=1`.

## Скриншоти (F12)

Зберігає `lysyk_<час>.png` у поточну теку. З коду: `window.screenshot("shot.png")`. Якщо поверхня API не підтримує копіювання (типово для OpenGL), цей кадр рендериться в позаекранну текстуру і не презентується.

## Гаряче перезавантаження шейдерів

```
python -m lysyk.engine dump-shaders my_shaders
LYSYK_SHADERS=my_shaders python main.py --overlay
```

Редагуйте `common.wgsl`, `main.wgsl`, `shadow.wgsl`; зміни підхоплюються за ~0.5 с. Помилка компіляції не ламає гру: лишається попередня версія, текст помилки в `renderer.shader_error` і в оверлеї. З коду: `renderer.watch_shaders(dir)`, `renderer.reload_shaders()`.

## CLI

- `python -m lysyk.engine info [--api vulkan|gl]` — адаптери, драйвери, ліміти, MSAA.
- `python -m lysyk.engine probe` — чи створюється пристрій на кожному скомпільованому API.

## Профайлер

`window.profile()` повертає `avg_ms`, `p50_ms`, `p99_ms`, `max_ms`, `stages_ms`, `history_ms`. `renderer.stats` — лічильники сцени.

## Headless

`OffscreenWindow` рендерить без вікна: `frame(draw)`, `read_pixels()`, `save_png(path)`.

`python tools/snapshot.py --out snaps --api vulkan` рендерить усі траси; `--compare DIR --tolerance N` порівнює з еталонами і повертає код помилки (візуальні регресії в CI).

`python tools/smoke_game.py --api gl` проганяє реальне вікно гри: меню, гараж, налаштування, заїзд (потрібен дисплей, наприклад `xvfb-run`).

## Логи

Повідомлення Rust і wgpu (валідація, вибраний адаптер, перезавантаження шейдерів) йдуть у стандартний Python `logging`.
