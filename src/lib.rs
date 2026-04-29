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
use std::time::Instant;
use uuid::Uuid;

#[pyclass]
struct Experiment {
    run_id: String,
    name: String,
    path: PathBuf,
    started_at: Instant,
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

        let experiment = Self {
            run_id,
            name,
            path,
            started_at: Instant::now(),
        };
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

    #[pyo3(signature = (value, note = None))]
    fn track(&self, value: &Bound<'_, PyAny>, note: Option<String>) -> PyResult<()> {
        let value = py_to_json(value)?;
        let mut record = json!({
            "schema_version": 1,
            "exprag_version": env!("CARGO_PKG_VERSION"),
            "run_id": self.run_id,
            "experiment_name": self.name,
            "kind": "track",
            "value": value,
            "created_at": Utc::now().to_rfc3339(),
            "elapsed_ms": self.elapsed_ms(),
        });
        if let Some(note) = note {
            record
                .as_object_mut()
                .expect("track record must be a JSON object")
                .insert("note".to_string(), JsonValue::String(note));
        }

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
    fn elapsed_ms(&self) -> u64 {
        u64::try_from(self.started_at.elapsed().as_millis()).unwrap_or(u64::MAX)
    }

    fn write_run_start(&self, metadata: Option<JsonValue>) -> PyResult<()> {
        let cwd = env::current_dir()
            .ok()
            .map(|path| path.display().to_string());
        let argv = env::args_os()
            .map(|arg| arg.to_string_lossy().into_owned())
            .collect::<Vec<_>>();

        let git_info = git_state(&self.run_id);
        let mut value = json!({
            "git": git_info,
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
            "exprag_version": env!("CARGO_PKG_VERSION"),
            "run_id": self.run_id,
            "experiment_name": self.name,
            "kind": "run_start",
            "value": value,
            "created_at": Utc::now().to_rfc3339(),
            "elapsed_ms": self.elapsed_ms(),
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

fn git_state(run_id: &str) -> JsonValue {
    if git_output(&["rev-parse", "--is-inside-work-tree"]).as_deref() != Some("true") {
        return JsonValue::Null;
    }

    let head = git_output(&["rev-parse", "HEAD"]).unwrap_or_default();
    let branch = git_output(&["rev-parse", "--abbrev-ref", "HEAD"]).unwrap_or_default();
    let dirty = is_dirty();

    let run_commit = dirty
        .then(|| snapshot_run_commit(run_id, &head))
        .flatten();
    let run_branch = run_commit.as_ref().map(|_| format!("run/{run_id}"));

    json!({
        "commit": head,
        "branch": branch,
        "dirty": dirty,
        "run_commit": run_commit,
        "run_branch": run_branch,
    })
}

fn is_dirty() -> bool {
    git_output(&["status", "--porcelain", "--ignore-submodules"])
        .map(|s| !s.trim().is_empty())
        .unwrap_or(false)
}

/// Create a clean, non-destructive snapshot branch for this run.
fn snapshot_run_commit(run_id: &str, head: &str) -> Option<String> {
    let git_dir = git_output(&["rev-parse", "--git-dir"])?;
    let work_tree = git_output(&["rev-parse", "--show-toplevel"])?;
    let exprag_dir = env::var("EXPRAG_DIR").unwrap_or_else(|_| ".exprag".to_string());
    let exprag_root = std::path::Path::new(&exprag_dir);
    let exprag_relative = if exprag_root.is_absolute() {
        exprag_root
            .strip_prefix(&work_tree)
            .unwrap_or(exprag_root)
            .to_string_lossy()
            .into_owned()
    } else {
        exprag_root.to_string_lossy().into_owned()
    };

    let index_file = std::env::temp_dir().join(format!("exprag-{run_id}.index"));

    // helper to run git with a temporary index so HEAD never moves
    let git = |args: &[&str]| -> Option<String> {
        let mut cmd = Command::new("git");
        cmd.args(args)
            .env("GIT_INDEX_FILE", &index_file)
            .env("GIT_DIR", &git_dir)
            .env("GIT_WORK_TREE", &work_tree);
        let output = cmd.output().ok()?;
        if !output.status.success() {
            return None;
        }
        Some(String::from_utf8_lossy(&output.stdout).trim_end().to_string())
    };

    git(&["read-tree", head])?;
    git(&["add", "--all"])?;

    let exprag_in_worktree = exprag_root.is_absolute()
        .then(|| exprag_root.strip_prefix(&work_tree).is_ok())
        .unwrap_or(true);
    if exprag_in_worktree {
        // Ensure exprag's own run records never leak into the snapshot
        git(&["reset", "--quiet", "--", &exprag_relative])?;
    }

    let tree = git(&["write-tree"])?;

    // If .exprag/ was the only dirty thing, tree == HEAD and there's nothing
    // meaningful to snapshot. Use plain git_output to avoid the temp index env.
    let head_tree = git_output(&["rev-parse", &format!("{}^{{tree}}", head)])?;
    if tree == head_tree {
        return None;
    }

    let msg = format!("exprag: snapshot run {run_id}");
    let commit = git(&["commit-tree", &tree, "-p", head, "-m", &msg])?;

    let branch = format!("run/{run_id}");
    // update-ref doesn't need the temp env, but we reuse the command builder
    git(&[
        "update-ref",
        &format!("refs/heads/{branch}"),
        &commit,
    ])?;

    let _ = std::fs::remove_file(&index_file);
    Some(commit)
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
