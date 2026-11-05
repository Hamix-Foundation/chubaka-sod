# Збірка під Android

Гра запускається як `NativeActivity`: Rust-бібліотека `lib_native.so` стартує `android_main`, розпаковує `bundle.tar` з ассетів APK у внутрішню пам'ять, піднімає вбудований CPython і запускає `chubaka.android.run()`. Вікно, ввід і життєвий цикл (`on_suspend` / `on_resume`) обробляє winit, рендер іде через wgpu (Vulkan, запасний варіант OpenGL ES).

## Що потрібно

- Rust 1.85+, JDK 17, Android SDK Command-line Tools і Gradle 8.9+ (або Gradle wrapper)
- CPython для Android із `lib/libpython3.X.so` та NumPy, зібраними під `arm64-v8a`; обидва мають бути з одного префікса або NumPy треба передати через `ANDROID_SITE_PACKAGES`
- На Android звук виводиться через системний `SoundPool` за допомогою pyjnius; на desktop використовується `miniaudio`

Збірка шукає Android SDK у звичних каталогах, `local.properties` та `~/.buildozer/android/platform/android-sdk`. NDK шукається в SDK і в сусідньому каталозі Buildozer; встановлена версія передається Gradle. Якщо NDK відсутній, скрипт встановлює r27.2; також перевіряє Android API 35, Build Tools і platform-tools, додає Rust target та встановлює `cargo-ndk`, якщо його немає. Якщо Android CPython і NumPy не задані через змінні оточення, перший запуск створює їх через `python-for-android` у `.android/`; артефакти зберігаються для наступних збірок.

## Збірка

```
export ANDROID_PYTHON_PREFIX=/path/to/python-android-prefix
./android/build.sh release
./android/build.sh debug
```

Скрипт збирає `lysyk/native/` у `lib_native.so` (`--no-default-features --features backend-vulkan,backend-gl,android-host`), копіює `libpython`, перевіряє NumPy, пакує `bundle.tar` (stdlib, залежності, `lysyk/`, `chubaka/`, `assets/`) і викликає Gradle. Готовий APK копіюється у `build/android/chubaka-release.apk` або `build/android/chubaka-debug.apk`. Для власного підпису задайте `CHUBAKA_KEYSTORE`, `CHUBAKA_KEYSTORE_PASSWORD`, `CHUBAKA_KEY_ALIAS`, `CHUBAKA_KEY_PASSWORD`.

Встановлення й логи:

```
adb install -r build/android/chubaka-release.apk
adb logcat -s lysyk python
```

## Якість і продуктивність

На Android за замовчуванням профіль `low`: без MSAA, тіней, частинок і плівкових ефектів, із лімітом 30 FPS. Змінити профіль можна в меню «Налаштування → Графіка» або через `settings.json` (`"quality": "auto|low|medium|high"`).

Перший запуск довший: розпаковується бандл. Далі він перевіряється за відбитком і не розпаковується повторно.
