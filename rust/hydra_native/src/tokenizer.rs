//! CSV tokenizer: a byte-level port of CPython's `_csv` reader state machine.
//!
//! Scope: the dialect Hydra uses (`csv.DictReader(f, delimiter=d, quotechar=q)`
//! on a file opened with `newline=""`), i.e. `doublequote=True`,
//! `escapechar=None`, `skipinitialspace=False`, `quoting=QUOTE_MINIMAL`,
//! `strict=False`. Delimiter and quote char must be ASCII.
//!
//! Line boundaries follow Python's universal newlines with `newline=""`: an
//! end-of-line event (EOL) is processed after `\n`, after a `\r` that is not
//! followed by `\n`, and at EOF when the last line is not terminated. As in
//! CPython, a record is complete when the state is back to `StartRecord` after
//! an EOL. Blank lines produce records with zero fields (Python's `[]`).
//!
//! Every situation where Python would raise, or where its behaviour depends on
//! the Python version, is reported as a [`Fallback`] so that the caller can hand
//! the file over to the Python implementation.

use std::io::Read;

/// `csv.field_size_limit()` default, in characters (code points).
pub const PY_FIELD_LIMIT: usize = 131_072;

const READ_CHUNK: usize = 256 * 1024;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Fallback {
    /// A field is longer than `csv.field_size_limit()` (Python raises `csv.Error`).
    FieldLimit { record: usize },
    /// `new-line character seen in unquoted field` (Python raises `csv.Error`).
    NewlineInUnquotedField { record: usize },
    /// EOF inside a quoted field: accepted by recent Python versions only.
    EofInQuotedField { record: usize },
    /// I/O error while reading.
    Io(String),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum State {
    StartRecord,
    StartField,
    InField,
    InQuotedField,
    QuoteInQuotedField,
    EatCrnl,
}

/// Streaming tokenizer. Fields of the current record are stored contiguously in
/// `row` and delimited by `ends`, to avoid one allocation per field.
pub struct Tokenizer<R: Read> {
    input: R,
    buf: Vec<u8>,
    pos: usize,
    len: usize,
    eof: bool,
    finished: bool,

    delimiter: u8,
    quote: u8,

    state: State,
    row: Vec<u8>,
    ends: Vec<usize>,
    field_start: usize,
    field_chars: usize,
    pending_cr: bool,
    line_open: bool,
    records: usize,
}

impl<R: Read> Tokenizer<R> {
    pub fn new(input: R, delimiter: u8, quote: u8) -> Self {
        Self {
            input,
            buf: vec![0; READ_CHUNK],
            pos: 0,
            len: 0,
            eof: false,
            finished: false,
            delimiter,
            quote,
            state: State::StartRecord,
            row: Vec::with_capacity(1024),
            ends: Vec::with_capacity(64),
            field_start: 0,
            field_chars: 0,
            pending_cr: false,
            line_open: false,
            records: 0,
        }
    }

    /// Number of records returned so far (blank ones included).
    pub fn records(&self) -> usize {
        self.records
    }

    /// Number of fields of the last record returned by [`next_record`].
    pub fn field_count(&self) -> usize {
        self.ends.len()
    }

    /// Bytes of field `i` of the last record returned by [`next_record`].
    pub fn field(&self, i: usize) -> &[u8] {
        let start = if i == 0 { 0 } else { self.ends[i - 1] };
        &self.row[start..self.ends[i]]
    }

    /// Reads the next record. `Ok(false)` at end of input.
    pub fn next_record(&mut self) -> Result<bool, Fallback> {
        if self.finished {
            return Ok(false);
        }
        self.row.clear();
        self.ends.clear();
        self.field_start = 0;
        self.field_chars = 0;
        loop {
            if self.pos == self.len {
                if !self.eof {
                    self.fill()?;
                    continue;
                }
                // End of input: flush the pending line, then apply CPython's EOF rule.
                if self.pending_cr || self.line_open {
                    self.pending_cr = false;
                    self.line_open = false;
                    self.process(None)?;
                    if self.state == State::StartRecord {
                        return Ok(self.emit());
                    }
                }
                if self.state == State::InQuotedField {
                    return Err(Fallback::EofInQuotedField { record: self.records });
                }
                self.finished = true;
                return Ok(false);
            }
            let c = self.buf[self.pos];
            if self.pending_cr {
                self.pending_cr = false;
                if c != b'\n' {
                    // "\r" alone ends the line before this byte.
                    self.line_open = false;
                    self.process(None)?;
                    if self.state == State::StartRecord {
                        return Ok(self.emit());
                    }
                }
            }
            self.pos += 1;
            self.line_open = true;
            self.process(Some(c))?;
            if c == b'\n' {
                self.line_open = false;
                self.process(None)?;
                if self.state == State::StartRecord {
                    return Ok(self.emit());
                }
            } else if c == b'\r' {
                self.pending_cr = true;
            }
        }
    }

    fn emit(&mut self) -> bool {
        self.records += 1;
        true
    }

    fn fill(&mut self) -> Result<(), Fallback> {
        loop {
            match self.input.read(&mut self.buf) {
                Ok(0) => {
                    self.eof = true;
                    self.pos = 0;
                    self.len = 0;
                    return Ok(());
                }
                Ok(n) => {
                    self.pos = 0;
                    self.len = n;
                    return Ok(());
                }
                Err(e) if e.kind() == std::io::ErrorKind::Interrupted => continue,
                Err(e) => return Err(Fallback::Io(e.to_string())),
            }
        }
    }

    #[inline]
    fn add_char(&mut self, c: u8) -> Result<(), Fallback> {
        // CPython counts characters; UTF-8 continuation bytes do not start one.
        if c & 0xC0 != 0x80 {
            if self.field_chars >= PY_FIELD_LIMIT {
                return Err(Fallback::FieldLimit { record: self.records });
            }
            self.field_chars += 1;
        }
        self.row.push(c);
        Ok(())
    }

    #[inline]
    fn save_field(&mut self) {
        self.ends.push(self.row.len());
        self.field_start = self.row.len();
        self.field_chars = 0;
    }

    /// One step of CPython's `parse_process_char`; `None` is the EOL event.
    fn process(&mut self, c: Option<u8>) -> Result<(), Fallback> {
        let is_nl = matches!(c, Some(b'\n') | Some(b'\r'));
        match self.state {
            State::StartRecord => match c {
                None => {}
                Some(b'\n') | Some(b'\r') => self.state = State::EatCrnl,
                Some(_) => {
                    self.state = State::StartField;
                    return self.process(c);
                }
            },
            State::StartField => {
                if is_nl || c.is_none() {
                    self.save_field();
                    self.state = if c.is_none() { State::StartRecord } else { State::EatCrnl };
                } else {
                    let ch = c.unwrap_or_default();
                    if ch == self.quote {
                        self.state = State::InQuotedField;
                    } else if ch == self.delimiter {
                        self.save_field();
                    } else {
                        self.add_char(ch)?;
                        self.state = State::InField;
                    }
                }
            }
            State::InField => {
                if is_nl || c.is_none() {
                    self.save_field();
                    self.state = if c.is_none() { State::StartRecord } else { State::EatCrnl };
                } else {
                    let ch = c.unwrap_or_default();
                    if ch == self.delimiter {
                        self.save_field();
                        self.state = State::StartField;
                    } else {
                        self.add_char(ch)?;
                    }
                }
            }
            State::InQuotedField => match c {
                None => {}
                Some(ch) if ch == self.quote => self.state = State::QuoteInQuotedField,
                Some(ch) => self.add_char(ch)?,
            },
            State::QuoteInQuotedField => {
                let ch = c.unwrap_or_default();
                if c.is_some() && ch == self.quote {
                    self.add_char(ch)?;
                    self.state = State::InQuotedField;
                } else if c.is_some() && ch == self.delimiter {
                    self.save_field();
                    self.state = State::StartField;
                } else if is_nl || c.is_none() {
                    self.save_field();
                    self.state = if c.is_none() { State::StartRecord } else { State::EatCrnl };
                } else {
                    // strict=False: the character is kept, the field continues unquoted.
                    self.add_char(ch)?;
                    self.state = State::InField;
                }
            }
            State::EatCrnl => match c {
                Some(b'\n') | Some(b'\r') => {}
                None => self.state = State::StartRecord,
                Some(_) => {
                    return Err(Fallback::NewlineInUnquotedField { record: self.records });
                }
            },
        }
        Ok(())
    }
}

/// Reasons for which a file must be read by the Python implementation from the
/// start (checked before the first record is returned).
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Precheck {
    Ok,
    /// UTF-8 byte order mark: Python keeps it in the first column name.
    Bom,
    /// Invalid UTF-8: Python raises while decoding, possibly before earlier rows.
    InvalidUtf8,
    /// NUL byte: rejected by `csv` before Python 3.11.
    Nul,
}

/// Streams the whole input once: UTF-8 validity, NUL bytes, BOM.
pub fn precheck<R: Read>(mut input: R) -> std::io::Result<Precheck> {
    let mut buf = vec![0u8; READ_CHUNK];
    let mut carry: Vec<u8> = Vec::new();
    let mut first = true;
    loop {
        let n = match input.read(&mut buf) {
            Ok(n) => n,
            Err(e) if e.kind() == std::io::ErrorKind::Interrupted => continue,
            Err(e) => return Err(e),
        };
        if n == 0 {
            return Ok(if carry.is_empty() { Precheck::Ok } else { Precheck::InvalidUtf8 });
        }
        let chunk = &buf[..n];
        if first {
            first = false;
            if chunk.starts_with(&[0xEF, 0xBB, 0xBF]) {
                return Ok(Precheck::Bom);
            }
        }
        if chunk.contains(&0) {
            return Ok(Precheck::Nul);
        }
        let data: Vec<u8>;
        let slice: &[u8] = if carry.is_empty() {
            chunk
        } else {
            data = [carry.as_slice(), chunk].concat();
            &data
        };
        match std::str::from_utf8(slice) {
            Ok(_) => carry.clear(),
            Err(e) => match e.error_len() {
                Some(_) => return Ok(Precheck::InvalidUtf8),
                None => {
                    // Incomplete sequence at the end of the chunk: keep it for the next one.
                    let valid = e.valid_up_to();
                    carry = slice[valid..].to_vec();
                }
            },
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn parse(s: &str) -> Result<Vec<Vec<String>>, Fallback> {
        let mut t = Tokenizer::new(s.as_bytes(), b',', b'"');
        let mut out = Vec::new();
        while t.next_record()? {
            out.push(
                (0..t.field_count())
                    .map(|i| String::from_utf8(t.field(i).to_vec()).unwrap())
                    .collect(),
            );
        }
        Ok(out)
    }

    fn rows(v: &[&[&str]]) -> Vec<Vec<String>> {
        v.iter().map(|r| r.iter().map(|s| s.to_string()).collect()).collect()
    }

    // Expected values below were produced by CPython 3.11
    // (`list(csv.reader(io.StringIO(s, newline="")))`).
    #[test]
    fn simple_and_blank_lines() {
        assert_eq!(parse("a,b\n1,2\n").unwrap(), rows(&[&["a", "b"], &["1", "2"]]));
        assert_eq!(parse("a\n\n\nb").unwrap(), rows(&[&["a"], &[], &[], &["b"]]));
        assert_eq!(parse("a,b,\n").unwrap(), rows(&[&["a", "b", ""]]));
        assert_eq!(parse("").unwrap(), rows(&[]));
    }

    #[test]
    fn quotes() {
        assert_eq!(parse("x,\"ab\"cd,e\n").unwrap(), rows(&[&["x", "abcd", "e"]]));
        assert_eq!(parse("a\"b,c\n").unwrap(), rows(&[&["a\"b", "c"]]));
        assert_eq!(parse("\"a\"\"b\",c\n").unwrap(), rows(&[&["a\"b", "c"]]));
        assert_eq!(parse(" \"a\",b\n").unwrap(), rows(&[&[" \"a\"", "b"]]));
        assert_eq!(parse("\"x\r\ny\",z\r\n").unwrap(), rows(&[&["x\r\ny", "z"]]));
    }

    #[test]
    fn line_endings() {
        assert_eq!(parse("a\rb\r").unwrap(), rows(&[&["a"], &["b"]]));
        assert_eq!(parse("a\r\nb\r\n").unwrap(), rows(&[&["a"], &["b"]]));
        assert_eq!(parse("a\r\rb").unwrap(), rows(&[&["a"], &[], &["b"]]));
    }

    #[test]
    fn eof_in_quoted_field_falls_back() {
        assert!(matches!(parse("a,\"bc\n"), Err(Fallback::EofInQuotedField { .. })));
    }

    #[test]
    fn field_limit() {
        let ok = "é".repeat(PY_FIELD_LIMIT);
        assert_eq!(parse(&ok).unwrap()[0][0].chars().count(), PY_FIELD_LIMIT);
        let too_long = "x".repeat(PY_FIELD_LIMIT + 1);
        assert!(matches!(parse(&too_long), Err(Fallback::FieldLimit { .. })));
    }

    #[test]
    fn prechecks() {
        assert_eq!(precheck("a,b\n".as_bytes()).unwrap(), Precheck::Ok);
        assert_eq!(precheck(&b"\xEF\xBB\xBFa\n"[..]).unwrap(), Precheck::Bom);
        assert_eq!(precheck(&b"a\x00b\n"[..]).unwrap(), Precheck::Nul);
        assert_eq!(precheck(&b"a\xFFb\n"[..]).unwrap(), Precheck::InvalidUtf8);
        assert_eq!(precheck(&b"a\xC3"[..]).unwrap(), Precheck::InvalidUtf8);
    }
}
