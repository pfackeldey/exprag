use chrono::Utc;
use pyo3::exceptions::{PyIOError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyModule};
use serde_json::{json, Value as JsonValue};
use std::env;
use std::fs::{create_dir_all, OpenOptions};
use std::io::Write;
use std::path::PathBuf;
use std::process::Command;
use uuid::Uuid;

#[pyclass]
struct Experiment {
    run_id: String,
    name: String,
    path: PathBuf,
}

#[pymethods]
impl Experiment {
    #[new]
    #[pyo3(signature = (name, metadata = None))]
    fn new(name: String, metadata: Option<&Bound<'_, PyAny>>) -> PyResult<Self> {
        if name.trim().is_empty() {
            return Err(PyValueError::new_err("experiment name cannot be empty"));
        }

        let run_id = Uuid::new_v4().to_string();
        let path = run_path(&run_id)?;
        let metadata = metadata.map(py_to_json).transpose()?;

        let experiment = Self { run_id, name, path };
        experiment.write_run_start(metadata)?;
        Ok(experiment)
    }

    #[getter]
    fn run_id(&self) -> String {
        self.run_id.clone()
    }

    #[getter]
    fn name(&self) -> String {
        self.name.clone()
    }

    #[getter]
    fn path(&self) -> String {
        self.path.display().to_string()
    }

    fn track(&self, value: &Bound<'_, PyAny>) -> PyResult<()> {
        let value = py_to_json(value)?;
        let record = json!({
            "schema_version": 1,
            "run_id": self.run_id,
            "experiment_name": self.name,
            "kind": "track",
            "value": value,
            "created_at": Utc::now().to_rfc3339(),
        });

        append_jsonl(&self.path, &record)
    }
}

#[pymodule]
fn exprag(_py: Python<'_>, module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<Experiment>()?;
    Ok(())
}

fn run_path(run_id: &str) -> PyResult<PathBuf> {
    let root = env::var("EXPRAG_DIR").unwrap_or_else(|_| ".exprag".to_string());
    let runs_dir = PathBuf::from(root).join("runs");
    create_dir_all(&runs_dir).map_err(|error| PyIOError::new_err(error.to_string()))?;
    Ok(runs_dir.join(format!("{run_id}.jsonl")))
}

fn append_jsonl(path: &PathBuf, value: &JsonValue) -> PyResult<()> {
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|error| PyIOError::new_err(error.to_string()))?;

    serde_json::to_writer(&mut file, value)
        .map_err(|error| PyValueError::new_err(error.to_string()))?;
    file.write_all(b"\n")
        .map_err(|error| PyIOError::new_err(error.to_string()))
}

impl Experiment {
    fn write_run_start(&self, metadata: Option<JsonValue>) -> PyResult<()> {
        let cwd = env::current_dir()
            .ok()
            .map(|path| path.display().to_string());
        let argv = env::args_os()
            .map(|arg| arg.to_string_lossy().into_owned())
            .collect::<Vec<_>>();

        let mut value = json!({
            "git": git_state(),
            "host": host_state(),
            "process": {
                "pid": std::process::id(),
                "ppid": parent_process_id(),
                "cwd": cwd,
                "argv": argv,
            },
        });
        if let Some(metadata) = metadata {
            value
                .as_object_mut()
                .expect("run_start value must be a JSON object")
                .insert("metadata".to_string(), metadata);
        }

        let record = json!({
            "schema_version": 1,
            "run_id": self.run_id,
            "experiment_name": self.name,
            "kind": "run_start",
            "value": value,
            "created_at": Utc::now().to_rfc3339(),
        });

        append_jsonl(&self.path, &record)
    }
}

fn host_state() -> JsonValue {
    json!({
        "hostname": env::var("HOSTNAME")
            .ok()
            .or_else(|| command_output("hostname", &[])),
        "os": env::consts::OS,
        "arch": env::consts::ARCH,
        "username": env::var("USER")
            .ok()
            .or_else(|| env::var("USERNAME").ok()),
        "cpu_count": std::thread::available_parallelism()
            .ok()
            .map(|count| count.get()),
    })
}

#[cfg(unix)]
fn parent_process_id() -> Option<u32> {
    let ppid = unsafe { libc::getppid() };
    u32::try_from(ppid).ok()
}

#[cfg(not(unix))]
fn parent_process_id() -> Option<u32> {
    None
}

fn git_state() -> JsonValue {
    if git_output(&["rev-parse", "--is-inside-work-tree"]).as_deref() != Some("true") {
        return JsonValue::Null;
    }

    let status = git_output(&["status", "--porcelain"]).unwrap_or_default();
    json!({
        "commit": git_output(&["rev-parse", "HEAD"]),
        "branch": git_output(&["rev-parse", "--abbrev-ref", "HEAD"]),
        "dirty": !status.is_empty(),
        "status": status,
        "diff": git_output(&["diff", "--no-ext-diff", "HEAD"]).unwrap_or_default(),
    })
}

fn git_output(args: &[&str]) -> Option<String> {
    command_output("git", args)
}

fn command_output(program: &str, args: &[&str]) -> Option<String> {
    let output = Command::new(program).args(args).output().ok()?;
    if !output.status.success() {
        return None;
    }

    Some(
        String::from_utf8_lossy(&output.stdout)
            .trim_end()
            .to_string(),
    )
}

fn py_to_json(value: &Bound<'_, PyAny>) -> PyResult<JsonValue> {
    let json_module = value.py().import("json")?;
    let dumped: String = json_module.call_method1("dumps", (value,))?.extract()?;
    serde_json::from_str(&dumped).map_err(|error| PyValueError::new_err(error.to_string()))
}
