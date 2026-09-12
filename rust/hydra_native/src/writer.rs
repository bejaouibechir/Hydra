//! CSV writer: writes Arrow columns exactly as `csv.writer` would write the
//! Python objects of `DataFrame.to_dict("records")`.
//!
//! Two things must match CPython byte for byte:
//!
//! * **value formatting** — `str(value)` for every type, in particular
//!   `repr(float)` (shortest round-trip, exponent below 1e-4 or from 1e17);
//! * **quoting** — `QUOTE_MINIMAL`: a field is quoted only if it contains the
//!   delimiter, the quote character or a line-ending character, the quote
//!   character being doubled; an empty field is quoted only when it is the
//!   single field of its record.
//!
//! Types this module does not handle (dates, decimals, dictionaries, nested
//! arrays) are reported so that the caller falls back to Python.

use std::fmt::Write as _;

use arrow_array::{
    Array, BooleanArray, Float32Array, Float64Array, Int32Array, Int64Array, LargeStringArray,
    NullArray, RecordBatch, StringArray, UInt32Array, UInt64Array,
};
use arrow_schema::DataType;

#[derive(Debug)]
pub enum WriteError {
    /// Column type with no exact Python equivalent here.
    Unsupported(String),
}

/// `repr(float)` of CPython.
///
/// Rust and Python both print the shortest string that reads back to the same
/// double, but they switch to exponent notation at different points and format
/// the exponent differently. We take Rust's shortest digits and re-render them
/// following CPython's rule (`decpt <= -4 || decpt > 16` -> exponent, exponent
/// written with a sign and at least two digits).
pub fn py_float_repr(x: f64) -> String {
    let mut out = String::with_capacity(24);
    let mut scratch = String::with_capacity(32);
    py_float_repr_into(x, &mut scratch, &mut out);
    out
}

/// Same, appending to `out` and reusing `scratch`: no allocation per value,
/// which matters when writing millions of numbers.
pub fn py_float_repr_into(x: f64, scratch: &mut String, out: &mut String) {
    if x.is_nan() {
        out.push_str("nan");
        return;
    }
    if x.is_infinite() {
        out.push_str(if x > 0.0 { "inf" } else { "-inf" });
        return;
    }
    if x == 0.0 {
        out.push_str(if x.is_sign_negative() { "-0.0" } else { "0.0" });
        return;
    }

    // Shortest digit count that reads back to the same double, then the
    // correctly rounded rendering with that many digits. Rust's plain shortest
    // output differs from CPython's on the rare values where two spellings are
    // equally valid (about 1 in 10,000): CPython keeps the nearest one, which
    // is what an exactly rounded rendering gives.
    scratch.clear();
    let _ = write!(scratch, "{:e}", x);
    let mut k = scratch
        .split_once('e')
        .map(|(m, _)| m.chars().filter(|c| c.is_ascii_digit()).count())
        .unwrap_or(17)
        .clamp(1, 17);
    loop {
        scratch.clear();
        let _ = write!(scratch, "{:.*e}", k - 1, x);
        if k >= 17 || scratch.parse::<f64>() == Ok(x) {
            break;
        }
        k += 1;
    }

    let (mantissa, exp) = scratch.split_once('e').expect("scientific notation");
    let exp: i32 = exp.parse().expect("exponent");
    let neg = mantissa.starts_with('-');
    let digits_end = mantissa.len() - mantissa.chars().rev().take_while(|c| *c == '0').count();
    let digits_raw = &mantissa[..digits_end.max(if neg { 2 } else { 1 })];
    let decpt = exp + 1; // position of the decimal point after the first digit

    if neg {
        out.push('-');
    }
    let start = out.len();
    for c in digits_raw.chars().filter(|c| c.is_ascii_digit()) {
        out.push(c);
    }
    let ndigits = out.len() - start;

    if decpt <= -4 || decpt > 16 {
        // Python writes 1e-05, not 1.0e-05: no ".0" padding in exponent form.
        if ndigits > 1 {
            out.insert(start + 1, '.');
        }
        let e = decpt - 1;
        let _ = write!(out, "e{}{:02}", if e < 0 { '-' } else { '+' }, e.abs());
    } else if decpt <= 0 {
        out.insert_str(start, "0.");
        for _ in 0..(-decpt) {
            out.insert(start + 2, '0');
        }
    } else if decpt as usize >= ndigits {
        for _ in 0..(decpt as usize - ndigits) {
            out.push('0');
        }
        out.push_str(".0");
    } else {
        out.insert(start + decpt as usize, '.');
    }
}

/// Dialect of `csv.writer` (QUOTE_MINIMAL, doublequote, no escapechar).
pub struct Dialect {
    pub delimiter: char,
    pub quotechar: char,
    pub lineterminator: String,
}

impl Dialect {
    fn needs_quoting(&self, s: &str) -> bool {
        // CPython quotes on CR and LF even when they are not the line
        // terminator in use, to keep the record unambiguous.
        s.chars().any(|c| {
            c == self.delimiter
                || c == self.quotechar
                || c == '\r'
                || c == '\n'
                || self.lineterminator.contains(c)
        })
    }

    /// Appends one already-formatted field, quoted if needed.
    fn push_field(&self, out: &mut String, s: &str, single_empty: bool) {
        if s.is_empty() {
            if single_empty {
                out.push(self.quotechar);
                out.push(self.quotechar);
            }
            return;
        }
        if self.needs_quoting(s) {
            out.push(self.quotechar);
            for c in s.chars() {
                if c == self.quotechar {
                    out.push(self.quotechar);
                }
                out.push(c);
            }
            out.push(self.quotechar);
        } else {
            out.push_str(s);
        }
    }
}

/// One column, pre-checked, ready to be rendered row by row.
enum Column<'a> {
    Str(&'a StringArray),
    LargeStr(&'a LargeStringArray),
    I64(&'a Int64Array),
    I32(&'a Int32Array),
    U64(&'a UInt64Array),
    U32(&'a UInt32Array),
    F64(&'a Float64Array),
    F32(&'a Float32Array),
    Bool(&'a BooleanArray),
    Null(&'a NullArray),
}

impl<'a> Column<'a> {
    fn new(a: &'a dyn Array) -> Result<Self, WriteError> {
        macro_rules! cast {
            ($t:ty, $v:ident) => {
                Ok(Column::$v(a.as_any().downcast_ref::<$t>().expect("array type")))
            };
        }
        match a.data_type() {
            DataType::Utf8 => cast!(StringArray, Str),
            DataType::LargeUtf8 => cast!(LargeStringArray, LargeStr),
            DataType::Int64 => cast!(Int64Array, I64),
            DataType::Int32 => cast!(Int32Array, I32),
            DataType::UInt64 => cast!(UInt64Array, U64),
            DataType::UInt32 => cast!(UInt32Array, U32),
            DataType::Float64 => cast!(Float64Array, F64),
            DataType::Float32 => cast!(Float32Array, F32),
            DataType::Boolean => cast!(BooleanArray, Bool),
            DataType::Null => cast!(NullArray, Null),
            other => Err(WriteError::Unsupported(other.to_string())),
        }
    }

    /// Renders row `i` into `buf`, exactly as `str()` would in Python.
    /// A null renders as the empty string, like `None` for `csv.writer`.
    fn render(&self, i: usize, buf: &mut String, scratch: &mut String) {
        buf.clear();
        match self {
            Column::Null(_) => {}
            Column::Str(a) => {
                if a.is_valid(i) {
                    buf.push_str(a.value(i))
                }
            }
            Column::LargeStr(a) => {
                if a.is_valid(i) {
                    buf.push_str(a.value(i))
                }
            }
            Column::I64(a) => {
                if a.is_valid(i) {
                    let _ = write!(buf, "{}", a.value(i));
                }
            }
            Column::I32(a) => {
                if a.is_valid(i) {
                    let _ = write!(buf, "{}", a.value(i));
                }
            }
            Column::U64(a) => {
                if a.is_valid(i) {
                    let _ = write!(buf, "{}", a.value(i));
                }
            }
            Column::U32(a) => {
                if a.is_valid(i) {
                    let _ = write!(buf, "{}", a.value(i));
                }
            }
            Column::F64(a) => {
                if a.is_valid(i) {
                    py_float_repr_into(a.value(i), scratch, buf);
                }
            }
            Column::F32(a) => {
                if a.is_valid(i) {
                    py_float_repr_into(a.value(i) as f64, scratch, buf);
                }
            }
            Column::Bool(a) => {
                if a.is_valid(i) {
                    buf.push_str(if a.value(i) { "True" } else { "False" });
                }
            }
        }
    }
}

/// Renders `batch` (plus an optional header row) as CSV text.
pub fn render_csv(
    batch: &RecordBatch,
    header: Option<&[String]>,
    dialect: &Dialect,
) -> Result<String, WriteError> {
    let columns: Vec<Column> = batch
        .columns()
        .iter()
        .map(|a| Column::new(a.as_ref()))
        .collect::<Result<_, _>>()?;
    let ncols = columns.len();
    let nrows = batch.num_rows();

    let mut out = String::with_capacity(nrows * ncols * 12 + 64);
    let mut buf = String::with_capacity(32);
    let mut scratch = String::with_capacity(32);

    if let Some(names) = header {
        for (c, name) in names.iter().enumerate() {
            if c > 0 {
                out.push(dialect.delimiter);
            }
            dialect.push_field(&mut out, name, names.len() == 1);
        }
        out.push_str(&dialect.lineterminator);
    }

    for row in 0..nrows {
        for (c, col) in columns.iter().enumerate() {
            if c > 0 {
                out.push(dialect.delimiter);
            }
            col.render(row, &mut buf, &mut scratch);
            dialect.push_field(&mut out, &buf, ncols == 1);
        }
        out.push_str(&dialect.lineterminator);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    // Expected values below come from CPython 3.11 (`repr(x)`).
    #[test]
    fn float_repr_matches_python() {
        for (x, expected) in [
            (1.5_f64, "1.5"),
            (1.0, "1.0"),
            (-0.1, "-0.1"),
            (0.0001, "0.0001"),
            (0.00001, "1e-05"),
            (1e16, "1e+16"),
            (1e15, "1000000000000000.0"),
            (1e20, "1e+20"),
            (1.2345678901234567e-13, "1.2345678901234566e-13"),
            (123456789.123, "123456789.123"),
            (f64::NAN, "nan"),
            (f64::INFINITY, "inf"),
            (f64::NEG_INFINITY, "-inf"),
            (0.0, "0.0"),
            (-0.0, "-0.0"),
            (f64::from_bits(1), "5e-324"),
        ] {
            assert_eq!(py_float_repr(x), expected, "repr({x})");
        }
    }

    #[test]
    fn quoting_matches_csv_writer() {
        let d = Dialect { delimiter: ',', quotechar: '"', lineterminator: "\r\n".into() };
        let mut s = String::new();
        d.push_field(&mut s, "plain", false);
        assert_eq!(s, "plain");
        s.clear();
        d.push_field(&mut s, "a,b", false);
        assert_eq!(s, "\"a,b\"");
        s.clear();
        d.push_field(&mut s, "say \"hi\"", false);
        assert_eq!(s, "\"say \"\"hi\"\"\"");
        s.clear();
        d.push_field(&mut s, "line\nbreak", false);
        assert_eq!(s, "\"line\nbreak\"");
        s.clear();
        let d_lf = Dialect { delimiter: ',', quotechar: '"', lineterminator: "\n".into() };
        d_lf.push_field(&mut s, "cr\rreturn", false);   // quoted even with LF terminator
        assert_eq!(s, "\"cr\rreturn\"");
        s.clear();
        d.push_field(&mut s, "", false);
        assert_eq!(s, "");
        s.clear();
        d.push_field(&mut s, "", true); // single empty field of a record
        assert_eq!(s, "\"\"");
    }
}
