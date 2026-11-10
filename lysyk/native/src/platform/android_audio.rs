use jni::objects::{Global, JObject, JString};
use jni::sys::jobject;
use jni::{errors::Error as JniError, jni_sig, jni_str, JValue, JavaVM};
use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use std::collections::HashMap;
use std::sync::atomic::{AtomicI32, Ordering};
use std::sync::Mutex;

fn vm() -> PyResult<JavaVM> {
    JavaVM::singleton().map_err(|e| PyRuntimeError::new_err(e.to_string()))
}

fn jni_error(error: JniError) -> PyErr {
    PyRuntimeError::new_err(error.to_string())
}

#[pyclass(module = "lysyk.engine._native")]
pub struct AndroidSoundPool {
    pool: Global<JObject<'static>>,
    long_sounds: Mutex<HashMap<i32, String>>,
    ready_players: Mutex<HashMap<i32, Global<JObject<'static>>>>,
    players: Mutex<HashMap<i32, Global<JObject<'static>>>>,
    next_sound: AtomicI32,
    next_stream: AtomicI32,
}

#[pymethods]
impl AndroidSoundPool {
    #[new]
    fn new() -> PyResult<Self> {
        let pool = vm()?
            .attach_current_thread(|env| {
                let local = env.new_object(
                    jni_str!("android/media/SoundPool"),
                    jni_sig!("(III)V"),
                    &[JValue::Int(16), JValue::Int(3), JValue::Int(0)],
                )?;
                env.new_global_ref(&local)
            })
            .map_err(jni_error)?;
        Ok(Self {
            pool,
            long_sounds: Mutex::new(HashMap::new()),
            ready_players: Mutex::new(HashMap::new()),
            players: Mutex::new(HashMap::new()),
            next_sound: AtomicI32::new(-1),
            next_stream: AtomicI32::new(-1_000_000),
        })
    }

    fn load(&self, path: &str) -> PyResult<(i32, f64)> {
        vm()?
            .attach_current_thread(|env| {
                let duration = (|| -> jni::errors::Result<f64> {
                    let retriever = env.new_object(
                        jni_str!("android/media/MediaMetadataRetriever"),
                        jni_sig!("()V"),
                        &[],
                    )?;
                    let file = env.new_string(path)?;
                    let file_object = JObject::from(file);
                    env.call_method(
                        &retriever,
                        jni_str!("setDataSource"),
                        jni_sig!("(Ljava/lang/String;)V"),
                        &[JValue::Object(&file_object)],
                    )?;
                    let metadata = env
                        .call_method(
                            &retriever,
                            jni_str!("extractMetadata"),
                            jni_sig!("(I)Ljava/lang/String;"),
                            &[JValue::Int(9)],
                        )?
                        .l()?;
                    let result = if metadata.is_null() {
                        0.0
                    } else {
                        let text =
                            unsafe { env.as_cast_raw::<Global<JString<'static>>>(&metadata)? };
                        text.to_string().parse::<f64>().unwrap_or(0.0) / 1000.0
                    };
                    env.call_method(&retriever, jni_str!("release"), jni_sig!("()V"), &[])?;
                    Ok(result)
                })();
                let duration = match duration {
                    Ok(value) => value,
                    Err(_) => {
                        let _ = env.exception_clear();
                        0.0
                    }
                };
                if duration > 4.0 {
                    let sound_id = self.next_sound.fetch_sub(1, Ordering::Relaxed);
                    self.long_sounds
                        .lock()
                        .unwrap()
                        .insert(sound_id, path.to_string());
                    let player = env.new_object(
                        jni_str!("android/media/MediaPlayer"),
                        jni_sig!("()V"),
                        &[],
                    )?;
                    let file = env.new_string(path)?;
                    let file_object = JObject::from(file);
                    env.call_method(
                        &player,
                        jni_str!("setDataSource"),
                        jni_sig!("(Ljava/lang/String;)V"),
                        &[JValue::Object(&file_object)],
                    )?;
                    env.call_method(&player, jni_str!("prepare"), jni_sig!("()V"), &[])?;
                    self.ready_players
                        .lock()
                        .unwrap()
                        .insert(sound_id, env.new_global_ref(&player)?);
                    return Ok((sound_id, duration));
                }
                let path_string = env.new_string(path)?;
                let path_object = JObject::from(path_string);
                let sound_id = env
                    .call_method(
                        &self.pool,
                        jni_str!("load"),
                        jni_sig!("(Ljava/lang/String;I)I"),
                        &[JValue::Object(&path_object), JValue::Int(1)],
                    )?
                    .i()?;
                Ok((sound_id, duration))
            })
            .map_err(jni_error)
    }

    #[pyo3(signature = (sound_id, left, right, loop_count))]
    fn play(&self, sound_id: i32, left: f32, right: f32, loop_count: i32) -> PyResult<i32> {
        if sound_id < 0 {
            let path = self
                .long_sounds
                .lock()
                .unwrap()
                .get(&sound_id)
                .cloned()
                .ok_or_else(|| PyRuntimeError::new_err("long audio asset is not loaded"))?;
            let stream_id = self.next_stream.fetch_sub(1, Ordering::Relaxed);
            let ready = self.ready_players.lock().unwrap().remove(&sound_id);
            let player = vm()?
                .attach_current_thread(|env| {
                    let player = if let Some(ready) = ready {
                        ready
                    } else {
                        let player = env.new_object(
                            jni_str!("android/media/MediaPlayer"),
                            jni_sig!("()V"),
                            &[],
                        )?;
                        let file = env.new_string(path)?;
                        let file_object = JObject::from(file);
                        env.call_method(
                            &player,
                            jni_str!("setDataSource"),
                            jni_sig!("(Ljava/lang/String;)V"),
                            &[JValue::Object(&file_object)],
                        )?;
                        env.call_method(&player, jni_str!("prepare"), jni_sig!("()V"), &[])?;
                        env.new_global_ref(&player)?
                    };
                    env.call_method(
                        &player,
                        jni_str!("setLooping"),
                        jni_sig!("(Z)V"),
                        &[JValue::Bool(loop_count < 0)],
                    )?;
                    env.call_method(
                        &player,
                        jni_str!("setVolume"),
                        jni_sig!("(FF)V"),
                        &[JValue::Float(left), JValue::Float(right)],
                    )?;
                    env.call_method(&player, jni_str!("start"), jni_sig!("()V"), &[])?;
                    Ok(player)
                })
                .map_err(jni_error)?;
            self.players.lock().unwrap().insert(stream_id, player);
            return Ok(stream_id);
        }
        vm()?
            .attach_current_thread(|env| {
                env.call_method(
                    &self.pool,
                    jni_str!("play"),
                    jni_sig!("(IFFIIF)I"),
                    &[
                        JValue::Int(sound_id),
                        JValue::Float(left),
                        JValue::Float(right),
                        JValue::Int(1),
                        JValue::Int(loop_count),
                        JValue::Float(1.0),
                    ],
                )?
                .i()
            })
            .map_err(jni_error)
    }

    fn set_volume(&self, stream_id: i32, left: f32, right: f32) -> PyResult<()> {
        if stream_id <= -1_000_000 {
            let players = self.players.lock().unwrap();
            let player = players
                .get(&stream_id)
                .ok_or_else(|| PyRuntimeError::new_err("media player stream is unavailable"))?;
            return vm()?
                .attach_current_thread(|env| {
                    env.call_method(
                        player,
                        jni_str!("setVolume"),
                        jni_sig!("(FF)V"),
                        &[JValue::Float(left), JValue::Float(right)],
                    )?;
                    Ok(())
                })
                .map_err(jni_error);
        }
        vm()?
            .attach_current_thread(|env| {
                env.call_method(
                    &self.pool,
                    jni_str!("setVolume"),
                    jni_sig!("(IFF)V"),
                    &[
                        JValue::Int(stream_id),
                        JValue::Float(left),
                        JValue::Float(right),
                    ],
                )?;
                Ok(())
            })
            .map_err(jni_error)
    }

    fn position(&self, stream_id: i32) -> PyResult<f64> {
        if stream_id > -1_000_000 {
            return Ok(-1.0);
        }
        let players = self.players.lock().unwrap();
        let Some(player) = players.get(&stream_id) else {
            return Ok(-1.0);
        };
        vm()?
            .attach_current_thread(|env| {
                let position = env
                    .call_method(player, jni_str!("getCurrentPosition"), jni_sig!("()I"), &[])?
                    .i()?;
                Ok(position as f64 / 1000.0)
            })
            .map_err(jni_error)
    }

    fn stop(&self, stream_id: i32) -> PyResult<()> {
        if stream_id <= -1_000_000 {
            if let Some(player) = self.players.lock().unwrap().remove(&stream_id) {
                vm()?
                    .attach_current_thread(|env| {
                        let _ = env.call_method(&player, jni_str!("stop"), jni_sig!("()V"), &[]);
                        env.call_method(&player, jni_str!("release"), jni_sig!("()V"), &[])?;
                        Ok(())
                    })
                    .map_err(jni_error)?;
            }
            return Ok(());
        }
        vm()?
            .attach_current_thread(|env| {
                env.call_method(
                    &self.pool,
                    jni_str!("stop"),
                    jni_sig!("(I)V"),
                    &[JValue::Int(stream_id)],
                )?;
                Ok(())
            })
            .map_err(jni_error)
    }

    fn auto_pause(&self) -> PyResult<()> {
        vm()?
            .attach_current_thread(|env| {
                env.call_method(&self.pool, jni_str!("autoPause"), jni_sig!("()V"), &[])?;
                for player in self.players.lock().unwrap().values() {
                    env.call_method(player, jni_str!("pause"), jni_sig!("()V"), &[])?;
                }
                Ok(())
            })
            .map_err(jni_error)
    }

    fn auto_resume(&self) -> PyResult<()> {
        vm()?
            .attach_current_thread(|env| {
                env.call_method(&self.pool, jni_str!("autoResume"), jni_sig!("()V"), &[])?;
                for player in self.players.lock().unwrap().values() {
                    env.call_method(player, jni_str!("start"), jni_sig!("()V"), &[])?;
                }
                Ok(())
            })
            .map_err(jni_error)
    }

    fn release(&self) -> PyResult<()> {
        vm()?
            .attach_current_thread(|env| {
                for player in self.players.lock().unwrap().values() {
                    let _ = env.call_method(player, jni_str!("stop"), jni_sig!("()V"), &[]);
                    env.call_method(player, jni_str!("release"), jni_sig!("()V"), &[])?;
                }
                self.players.lock().unwrap().clear();
                for player in self.ready_players.lock().unwrap().values() {
                    env.call_method(player, jni_str!("release"), jni_sig!("()V"), &[])?;
                }
                self.ready_players.lock().unwrap().clear();
                env.call_method(&self.pool, jni_str!("release"), jni_sig!("()V"), &[])?;
                Ok(())
            })
            .map_err(jni_error)
    }
}

#[pyfunction]
fn android_open_url(url: &str) -> PyResult<()> {
    let app = crate::android::app()
        .ok_or_else(|| PyRuntimeError::new_err("Android activity is unavailable"))?;
    let raw_activity = app.activity_as_ptr() as jobject;
    vm()?
        .attach_current_thread(|env| {
            let activity = unsafe { env.as_cast_raw::<Global<JObject<'static>>>(&raw_activity)? };
            let action = env.new_string("android.intent.action.VIEW")?;
            let uri_class = env.find_class(jni_str!("android/net/Uri"))?;
            let url_string = env.new_string(url)?;
            let url_object = JObject::from(url_string);
            let uri = env
                .call_static_method(
                    uri_class,
                    jni_str!("parse"),
                    jni_sig!("(Ljava/lang/String;)Landroid/net/Uri;"),
                    &[JValue::Object(&url_object)],
                )?
                .l()?;
            let intent = env.new_object(
                jni_str!("android/content/Intent"),
                jni_sig!("(Ljava/lang/String;Landroid/net/Uri;)V"),
                &[JValue::Object(action.as_ref()), JValue::Object(&uri)],
            )?;
            env.call_method(
                &intent,
                jni_str!("addFlags"),
                jni_sig!("(I)Landroid/content/Intent;"),
                &[JValue::Int(0x10000000)],
            )?;
            env.call_method(
                &*activity,
                jni_str!("startActivity"),
                jni_sig!("(Landroid/content/Intent;)V"),
                &[JValue::Object(&intent)],
            )?;
            Ok(())
        })
        .map_err(jni_error)
}

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<AndroidSoundPool>()?;
    module.add_function(wrap_pyfunction!(android_open_url, module)?)?;
    Ok(())
}
