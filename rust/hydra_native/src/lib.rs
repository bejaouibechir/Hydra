//! hydra_native — Rust accelerators for Hydra ETL.
//!
//! Step 3 of the Rust integration plan: a CSV reader that yields Arrow record
//! batches of UTF-8 columns, with the exact tokenization of Python's `csv`
//! module (see `tokenizer.rs`). Independent from the Hydra package: the Python
//! side decides whether and how to use it.

pub mod tokenizer;
pub mod writer;

use std::fs::File;
use std::io::BufReader;
use std::sync::Arc;

use arrow_array::builder::LargeStringBuilder;
use arrow_array::{ArrayRef, RecordBatch};
use arrow_schema::{DataType, Field, Schema};
use pyo3::create_exception;
use pyo3::exceptions::{PyException, PyValueError};
use pyo3::prelude::*;
use pyo3_arrow::PyRecordBatch;

use std::io::Write as _;
use writer::{render_csv, Dialect, WriteError};

use tokenizer::{precheck, Fallback, Precheck, Tokenizer};

create_exception!(
    hydra_native,
    CsvFallback,
    PyException,
    "The file must be read by the Python implementation. `args[1]` is the number of data rows already returned."
);

/// One batch, before conversion to Python.
enum Batch {
    /// Every row has as many fields as the header, and the header names are unique.
    Columns(Vec<ArrayRef>),
    /// At least one irregular row (or duplicated header names): raw rows.
    Rows(Vec<Vec<String>>),
}

#[pyclass(unsendable, module = "hydra_native")]
pub struct CsvBatchReader {
    tok: Tokenizer<BufReader<File>>,
    header: Option<Vec<String>>,
    unique_header: bool,
    batch_size: usize,
    rows_emitted: usize,
}

fn single_char(name: &str, value: &str) -> PyResult<char> {
    let mut it = value.chars();
    match (it.next(), it.next()) {
        (Some(c), None) => Ok(c),
        _ => Err(CsvFallback::new_err((format!("unsupported {name}: {value:?}"), 0usize))),
    }
}

fn single_ascii(name: &str, value: &str) -> PyResult<u8> {
    let b = value.as_bytes();
    if b.len() == 1 && b[0].is_ascii() && b[0] != b'\n' && b[0] != b'\r' {
        Ok(b[0])
    } else {
        Err(CsvFallback::new_err((format!("unsupported {name}: {value:?}"), 0usize)))
    }
}

fn to_py_err(f: Fallback, rows_emitted: usize) -> PyErr {
    CsvFallback::new_err((format!("{f:?}"), rows_emitted))
}

impl CsvBatchReader {
    /// Current record as UTF-8 strings (validated by the precheck).
    fn record_strings(&self) -> Vec<String> {
        (0..self.tok.field_count())
            .map(|i| String::from_utf8_lossy(self.tok.field(i)).into_owned())
            .collect()
    }

    fn read_batch(&mut self) -> Result<Option<Batch>, Fallback> {
        let header_len = self.header.as_ref().map_or(0, |h| h.len());
        let mut builders: Vec<LargeStringBuilder> =
            (0..header_len).map(|_| LargeStringBuilder::new()).collect();
        let mut rows: Option<Vec<Vec<String>>> = if self.unique_header { None } else { Some(Vec::new()) };
        let mut n = 0usize;

        while n < self.batch_size {
            if !self.tok.next_record()? {
                break;
            }
            let nf = self.tok.field_count();
            if nf == 0 {
                continue; // csv.DictReader skips blank rows
            }
            n += 1;
            match rows.as_mut() {
                Some(r) => r.push(self.record_strings()),
                None if nf == header_len => {
                    for (i, b) in builders.iter_mut().enumerate() {
                        // SAFETY: the whole file was validated as UTF-8 by `precheck`,
                        // and fields end on ASCII delimiters, quotes or newlines.
                        b.append_value(unsafe { std::str::from_utf8_unchecked(self.tok.field(i)) });
                    }
                }
                None => {
                    // First irregular row: move the rows built so far to the row form.
                    let mut r: Vec<Vec<String>> = Vec::with_capacity(n);
                    let arrays: Vec<_> = builders.iter_mut().map(|b| b.finish()).collect();
                    for row in 0..(n - 1) {
                        r.push(arrays.iter().map(|a| a.value(row).to_string()).collect());
                    }
                    r.push(self.record_strings());
                    rows = Some(r);
                }
            }
        }
        if n == 0 {
            return Ok(None);
        }
        self.rows_emitted += n;
        Ok(Some(match rows {
            Some(r) => Batch::Rows(r),
            None => Batch::Columns(
                builders.iter_mut().map(|b| Arc::new(b.finish()) as ArrayRef).collect(),
            ),
        }))
    }
}

#[pymethods]
impl CsvBatchReader {
    /// Opens `path` and reads the header line.
    ///
    /// Raises `CsvFallback` when the file must be handled by Python (BOM,
    /// invalid UTF-8, NUL byte, non-ASCII dialect characters).
    #[new]
    #[pyo3(signature = (path, delimiter = ",", quotechar = "\"", batch_size = 10_000))]
    fn new(path: &str, delimiter: &str, quotechar: &str, batch_size: usize) -> PyResult<Self> {
        if batch_size == 0 {
            return Err(PyValueError::new_err("batch_size must be >= 1"));
        }
        let d = single_ascii("delimiter", delimiter)?;
        let q = single_ascii("quotechar", quotechar)?;
        if d == q {
            return Err(CsvFallback::new_err(("delimiter == quotechar".to_string(), 0usize)));
        }
        match precheck(BufReader::new(File::open(path)?))? {
            Precheck::Ok => {}
            other => return Err(CsvFallback::new_err((format!("{other:?}"), 0usize))),
        }
        let mut tok = Tokenizer::new(BufReader::new(File::open(path)?), d, q);
        // DictReader.fieldnames = next(reader): the first record, blank or not.
        let header = if tok.next_record().map_err(|f| to_py_err(f, 0))? {
            Some(
                (0..tok.field_count())
                    .map(|i| String::from_utf8_lossy(tok.field(i)).into_owned())
                    .collect::<Vec<_>>(),
            )
        } else {
            None
        };
        let unique_header = header.as_ref().is_some_and(|h| {
            let mut seen = std::collections::HashSet::new();
            h.iter().all(|x| seen.insert(x.as_str()))
        });
        Ok(Self { tok, header, unique_header, batch_size, rows_emitted: 0 })
    }

    /// Column names (`None` for an empty file, `[]` if the first line is blank).
    #[getter]
    fn header(&self) -> Option<Vec<String>> {
        self.header.clone()
    }

    /// Number of data rows returned so far.
    #[getter]
    fn rows_emitted(&self) -> usize {
        self.rows_emitted
    }

    fn __iter__(slf: PyRef<'_, Self>) -> PyRef<'_, Self> {
        slf
    }

    /// Next batch: a `pyarrow.RecordBatch` of string columns, or a `list[list[str]]`
    /// when the batch contains an irregular row or the header has duplicates.
    fn __next__(&mut self, py: Python<'_>) -> PyResult<Option<Py<PyAny>>> {
        let header = match &self.header {
            Some(h) if !h.is_empty() => h.clone(),
            _ => return Ok(None),
        };
        let before = self.rows_emitted;
        let batch = self.read_batch().map_err(|f| to_py_err(f, before))?;
        match batch {
            None => Ok(None),
            Some(Batch::Rows(r)) => Ok(Some(r.into_pyobject(py)?.into_any().unbind())),
            Some(Batch::Columns(arrays)) => {
                let fields: Vec<Field> =
                    header.iter().map(|n| Field::new(n, DataType::LargeUtf8, false)).collect();
                let rb = RecordBatch::try_new(Arc::new(Schema::new(fields)), arrays)
                    .map_err(|e| PyValueError::new_err(e.to_string()))?;
                Ok(Some(PyRecordBatch::new(rb).into_pyarrow(py)?.unbind()))
            }
        }
    }
}

/// Writes `batch` as CSV, exactly as `csv.writer` would write the Python rows
/// of `DataFrame.to_dict("records")` (see writer.rs).
///
/// `append` selects the open mode; `header` is written first when given.
/// Raises `CsvFallback` for a column type this writer does not handle, before
/// touching the file.
#[pyfunction]
#[pyo3(signature = (path, batch, *, append, header=None, delimiter=",", quotechar="\"", lineterminator="\r\n"))]
fn write_csv(
    py: Python<'_>,
    path: &str,
    batch: PyRecordBatch,
    append: bool,
    header: Option<Vec<String>>,
    delimiter: &str,
    quotechar: &str,
    lineterminator: &str,
) -> PyResult<usize> {
    let d = Dialect {
        delimiter: single_char("delimiter", delimiter)?,
        quotechar: single_char("quotechar", quotechar)?,
        lineterminator: lineterminator.to_string(),
    };
    let rb = batch.into_inner();
    let rows = rb.num_rows();
    let text = py
        .detach(|| render_csv(&rb, header.as_deref(), &d))
        .map_err(|WriteError::Unsupported(t)| {
            CsvFallback::new_err((format!("unsupported column type: {t}"), 0usize))
        })?;
    let mut f = std::fs::OpenOptions::new()
        .create(true)
        .append(append)
        .write(!append)
        .truncate(!append)
        .open(path)?;
    py.detach(|| f.write_all(text.as_bytes()))?;
    Ok(rows)
}

#[pymodule]
fn hydra_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<CsvBatchReader>()?;
    m.add_function(wrap_pyfunction!(write_csv, m)?)?;
    m.add("CsvFallback", m.py().get_type::<CsvFallback>())?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
