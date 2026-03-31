mod parsing;
mod rowbinary;
mod steps;
mod trends;
mod unordered_steps;
mod unordered_trends;

use serde::{Deserialize, Serialize};
use std::env;
use std::io::{self, BufRead, BufReader, BufWriter, Read, Write};

#[derive(Debug, Clone, PartialEq, Deserialize, Serialize)]
#[serde(untagged)]
enum PropVal {
    String(String),
    Vec(Vec<String>),
    Int(u64),
    VecInt(Vec<u64>),
}

#[cfg(test)]
mod tests {
    use super::*;
    use rstest::rstest;

    #[rstest]
    #[case(r#""hello""#, PropVal::String("hello".to_string()))]
    #[case(r#"42"#, PropVal::Int(42))]
    #[case(r#"4503599627370496"#, PropVal::Int(4503599627370496))] // 2^52 (NOT_IN_COHORT_ID)
    #[case(r#"["a","b"]"#, PropVal::Vec(vec!["a".to_string(), "b".to_string()]))]
    #[case(r#"[1, 2, 3]"#, PropVal::VecInt(vec![1, 2, 3]))]
    #[case(r#"[4503599627370496]"#, PropVal::VecInt(vec![4503599627370496]))]
    fn test_propval_deserialization(#[case] json: &str, #[case] expected: PropVal) {
        let result: PropVal = serde_json::from_str(json).unwrap();
        assert_eq!(result, expected);
    }
}

fn main() {
    let args: Vec<String> = env::args().collect();
    let arg = args.get(1).map(|x| x.as_str());

    let stdin = io::stdin();
    let stdout = io::stdout();
    let mut reader = BufReader::new(stdin.lock());
    let mut writer = BufWriter::new(stdout.lock());

    let is_json = starts_with_json(&mut reader);
    if is_json {
        run_json_mode(&mut reader, &mut writer, arg);
        return;
    }

    if arg == Some("trends") {
        panic!("RowBinary mode is not supported for trends UDF");
    }
    run_rowbinary_steps_mode(&mut reader, &mut writer);
}

fn starts_with_json(reader: &mut BufReader<impl Read>) -> bool {
    match reader.fill_buf() {
        Ok(buf) => matches!(buf.first(), Some(b'{')),
        Err(_) => false,
    }
}

fn run_json_mode(
    reader: &mut BufReader<impl Read>,
    writer: &mut BufWriter<impl Write>,
    arg: Option<&str>,
) {
    for line in reader.lines().map_while(Result::ok) {
        let output = match arg {
            Some("trends") => {
                let parsed: trends::Args =
                    serde_json::from_str(&line).expect("Invalid JSON trends input");
                serde_json::to_string(&trends::process_args(parsed))
                    .expect("Failed to serialize trends output")
            }
            _ => {
                let parsed: steps::Args =
                    serde_json::from_str(&line).expect("Invalid JSON steps input");
                serde_json::to_string(&steps::process_args(parsed))
                    .expect("Failed to serialize steps output")
            }
        };
        writeln!(writer, "{output}").expect("Failed to write JSON output");
        writer.flush().expect("Failed to flush JSON output");
    }
}

fn run_rowbinary_steps_mode(reader: &mut BufReader<impl Read>, writer: &mut BufWriter<impl Write>) {
    let mut rb_reader = rowbinary::RowBinaryReader::new(reader);
    let mut rb_writer = rowbinary::RowBinaryWriter::new(writer);

    loop {
        match rb_reader.read_steps_args() {
            Ok(input) => {
                let output = steps::process_args(input);
                rb_writer
                    .write_steps_output(&output)
                    .expect("Failed to write RowBinary steps output");
            }
            Err(err) if err.kind() == io::ErrorKind::UnexpectedEof => return,
            Err(err) => panic!("Failed to read RowBinary steps input: {err}"),
        }
    }
}
