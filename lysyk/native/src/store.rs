use numpy::ndarray::{ArrayView1, ArrayView2};
use numpy::{PyArray1, PyArray2};
use pyo3::prelude::*;
use std::sync::Mutex;

pub const CAPACITY: usize = 1 << 16;
pub const COLUMNS: usize = 12;
pub const STRIDE: usize = COLUMNS * 4;

pub const COL_VISIBLE: usize = 11;
pub const COL_MODE: usize = 7;
pub const COL_COLOR: usize = 3;

struct Alloc {
    free: Vec<u32>,
    next: usize,
}

pub struct Store {
    data: *mut f32,
    mesh_ids: *mut i32,
    cast: *mut u8,
    alloc: Mutex<Alloc>,
}

unsafe impl Send for Store {}
unsafe impl Sync for Store {}

static STORE: std::sync::OnceLock<Store> = std::sync::OnceLock::new();

pub fn store() -> &'static Store {
    STORE.get_or_init(|| {
        let data: &'static mut [f32] =
            Box::leak(vec![0.0f32; CAPACITY * COLUMNS].into_boxed_slice());
        let ids: &'static mut [i32] = Box::leak(vec![-1i32; CAPACITY].into_boxed_slice());
        let cast: &'static mut [u8] = Box::leak(vec![0u8; CAPACITY].into_boxed_slice());
        Store {
            data: data.as_mut_ptr(),
            mesh_ids: ids.as_mut_ptr(),
            cast: cast.as_mut_ptr(),
            alloc: Mutex::new(Alloc {
                free: Vec::new(),
                next: 0,
            }),
        }
    })
}

impl Store {
    #[inline]
    pub fn row(&self, slot: u32) -> &mut [f32] {
        debug_assert!((slot as usize) < CAPACITY);
        unsafe { std::slice::from_raw_parts_mut(self.data.add(slot as usize * COLUMNS), COLUMNS) }
    }

    #[inline]
    pub fn row_bits(&self, slot: u32) -> &mut [u32] {
        unsafe {
            std::slice::from_raw_parts_mut(
                self.data.add(slot as usize * COLUMNS) as *mut u32,
                COLUMNS,
            )
        }
    }

    #[inline]
    pub fn mesh_id(&self, slot: u32) -> i32 {
        unsafe { *self.mesh_ids.add(slot as usize) }
    }

    #[inline]
    pub fn set_mesh_id(&self, slot: u32, id: i32) {
        unsafe { *self.mesh_ids.add(slot as usize) = id }
    }

    #[inline]
    pub fn cast(&self, slot: u32) -> bool {
        unsafe { *self.cast.add(slot as usize) != 0 }
    }

    #[inline]
    pub fn set_cast(&self, slot: u32, v: bool) {
        unsafe { *self.cast.add(slot as usize) = v as u8 }
    }

    pub fn alloc(&self) -> PyResult<u32> {
        let slot = {
            let mut a = self.alloc.lock().unwrap();
            if let Some(s) = a.free.pop() {
                s
            } else {
                if a.next >= CAPACITY {
                    return Err(pyo3::exceptions::PyMemoryError::new_err(
                        "instance store is full",
                    ));
                }
                a.next += 1;
                (a.next - 1) as u32
            }
        };
        let r = self.row(slot);
        r.fill(0.0);
        r[8] = 1.0;
        r[9] = 1.0;
        r[10] = 1.0;
        r[COL_VISIBLE] = 1.0;
        self.row_bits(slot)[COL_COLOR] = 0x00FF_FFFF;
        self.set_mesh_id(slot, -1);
        self.set_cast(slot, false);
        Ok(slot)
    }

    pub fn release(&self, slot: u32) {
        self.set_mesh_id(slot, -1);
        self.row(slot)[COL_VISIBLE] = 0.0;
        self.set_cast(slot, false);
        self.alloc.lock().unwrap().free.push(slot);
    }

    pub fn live_slots(&self) -> usize {
        let a = self.alloc.lock().unwrap();
        a.next - a.free.len()
    }
}

#[pyclass(module = "lysyk.engine._native")]
pub struct StoreOwner;

pub fn owner(py: Python<'_>) -> PyResult<Bound<'_, StoreOwner>> {
    static OWNER: std::sync::OnceLock<Py<StoreOwner>> = std::sync::OnceLock::new();
    if let Some(o) = OWNER.get() {
        return Ok(o.bind(py).clone());
    }
    let o = Py::new(py, StoreOwner)?;
    let _ = OWNER.set(o);
    Ok(OWNER.get().unwrap().bind(py).clone())
}

pub fn row_view<'py>(
    py: Python<'py>,
    slot: u32,
    from: usize,
    to: usize,
) -> PyResult<Bound<'py, PyArray1<f32>>> {
    let s = store();
    let r = s.row(slot);
    let view = unsafe { ArrayView1::from_shape_ptr(to - from, r.as_ptr().add(from)) };
    Ok(unsafe { PyArray1::borrow_from_array(&view, owner(py)?.into_any()) })
}

pub fn data_array<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyArray2<f32>>> {
    let s = store();
    let view = unsafe { ArrayView2::from_shape_ptr((CAPACITY, COLUMNS), s.data as *const f32) };
    Ok(unsafe { PyArray2::borrow_from_array(&view, owner(py)?.into_any()) })
}

pub fn color_bits_array<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyArray2<u32>>> {
    let s = store();
    let view = unsafe { ArrayView2::from_shape_ptr((CAPACITY, COLUMNS), s.data as *const u32) };
    Ok(unsafe { PyArray2::borrow_from_array(&view, owner(py)?.into_any()) })
}

pub fn mesh_ids_array<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyArray1<i32>>> {
    let s = store();
    let view = unsafe { ArrayView1::from_shape_ptr(CAPACITY, s.mesh_ids as *const i32) };
    Ok(unsafe { PyArray1::borrow_from_array(&view, owner(py)?.into_any()) })
}

#[pyfunction]
pub fn store_alloc() -> PyResult<u32> {
    store().alloc()
}

#[pyfunction]
pub fn store_release(slot: u32) {
    store().release(slot)
}

#[pyfunction]
pub fn store_live() -> usize {
    store().live_slots()
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = m.py();
    m.add_class::<StoreOwner>()?;
    m.add("STORE_CAPACITY", CAPACITY)?;
    m.add("STORE_STRIDE", STRIDE)?;
    m.add("STORE_COLUMNS", COLUMNS)?;
    m.add("store_data", data_array(py)?)?;
    m.add("store_color_bits", color_bits_array(py)?)?;
    m.add("store_mesh_ids", mesh_ids_array(py)?)?;
    m.add_function(wrap_pyfunction!(store_alloc, m)?)?;
    m.add_function(wrap_pyfunction!(store_release, m)?)?;
    m.add_function(wrap_pyfunction!(store_live, m)?)?;
    Ok(())
}
