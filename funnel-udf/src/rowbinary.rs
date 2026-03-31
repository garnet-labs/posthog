use crate::steps::{Args, Event, Output, Result};
use crate::PropVal;
use std::io::{self, Read, Write};
use uuid::Uuid;

pub struct RowBinaryReader<R: Read> {
    inner: R,
}

impl<R: Read> RowBinaryReader<R> {
    pub fn new(inner: R) -> Self {
        Self { inner }
    }

    pub fn read_steps_args(&mut self) -> io::Result<Args> {
        let num_steps = self.read_u8()? as usize;
        let conversion_window_limit = self.read_u64()?;
        let breakdown_attribution_type = self.read_string()?;
        let funnel_order_type = self.read_string()?;
        let prop_vals = self.read_array(|reader| reader.read_nullable_string_prop_val())?;
        let optional_steps = self.read_array(|reader| reader.read_i8())?;
        let value = self.read_array(|reader| reader.read_steps_event())?;

        Ok(Args {
            num_steps,
            conversion_window_limit,
            breakdown_attribution_type,
            funnel_order_type,
            prop_vals,
            optional_steps,
            value,
        })
    }

    fn read_steps_event(&mut self) -> io::Result<Event> {
        let timestamp = self.read_nullable_f64()?;
        let uuid = self.read_uuid()?;
        let breakdown = self.read_nullable_string_prop_val()?;
        let steps = self.read_array(|reader| reader.read_i8())?;
        Ok(Event {
            timestamp,
            uuid,
            breakdown,
            steps,
        })
    }

    fn read_nullable_string_prop_val(&mut self) -> io::Result<PropVal> {
        let is_null = self.read_u8()?;
        if is_null == 1 {
            return Ok(PropVal::String(String::new()));
        }
        Ok(PropVal::String(self.read_string()?))
    }

    fn read_nullable_f64(&mut self) -> io::Result<f64> {
        let is_null = self.read_u8()?;
        if is_null == 1 {
            return Ok(0.0);
        }
        self.read_f64()
    }

    fn read_var_uint(&mut self) -> io::Result<u64> {
        let mut value: u64 = 0;
        let mut shift = 0;
        loop {
            let byte = self.read_u8()?;
            value |= ((byte & 0x7F) as u64) << shift;
            if byte & 0x80 == 0 {
                return Ok(value);
            }
            shift += 7;
            if shift > 63 {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    "varuint overflow",
                ));
            }
        }
    }

    fn read_array<T>(
        &mut self,
        mut item_reader: impl FnMut(&mut Self) -> io::Result<T>,
    ) -> io::Result<Vec<T>> {
        let len = self.read_var_uint()? as usize;
        let mut result = Vec::with_capacity(len);
        for _ in 0..len {
            result.push(item_reader(self)?);
        }
        Ok(result)
    }

    fn read_string(&mut self) -> io::Result<String> {
        let len = self.read_var_uint()? as usize;
        let mut buf = vec![0u8; len];
        self.inner.read_exact(&mut buf)?;
        String::from_utf8(buf).map_err(|err| io::Error::new(io::ErrorKind::InvalidData, err))
    }

    fn read_u8(&mut self) -> io::Result<u8> {
        let mut b = [0u8; 1];
        self.inner.read_exact(&mut b)?;
        Ok(b[0])
    }

    fn read_i8(&mut self) -> io::Result<i8> {
        Ok(self.read_u8()? as i8)
    }

    fn read_u64(&mut self) -> io::Result<u64> {
        let mut b = [0u8; 8];
        self.inner.read_exact(&mut b)?;
        Ok(u64::from_le_bytes(b))
    }

    fn read_f64(&mut self) -> io::Result<f64> {
        let mut b = [0u8; 8];
        self.inner.read_exact(&mut b)?;
        Ok(f64::from_le_bytes(b))
    }

    fn read_uuid(&mut self) -> io::Result<Uuid> {
        let mut b = [0u8; 16];
        self.inner.read_exact(&mut b)?;
        Ok(Uuid::from_u128_le(u128::from_le_bytes(b)))
    }
}

pub struct RowBinaryWriter<W: Write> {
    inner: W,
}

impl<W: Write> RowBinaryWriter<W> {
    pub fn new(inner: W) -> Self {
        Self { inner }
    }

    pub fn write_steps_output(&mut self, output: &Output) -> io::Result<()> {
        self.write_var_uint(output.result.len() as u64)?;
        for item in &output.result {
            self.write_steps_result(item)?;
        }
        self.inner.flush()
    }

    fn write_steps_result(&mut self, result: &Result) -> io::Result<()> {
        self.write_i8(result.0)?;
        self.write_nullable_string_prop_val(&result.1)?;
        self.write_var_uint(result.2.len() as u64)?;
        for timing in &result.2 {
            self.write_f64(*timing)?;
        }
        self.write_var_uint(result.3.len() as u64)?;
        for uuid_group in &result.3 {
            self.write_var_uint(uuid_group.len() as u64)?;
            for uuid in uuid_group {
                self.write_uuid(uuid)?;
            }
        }
        self.write_u32(result.4)
    }

    fn write_nullable_string_prop_val(&mut self, prop_val: &PropVal) -> io::Result<()> {
        match prop_val {
            PropVal::String(value) => {
                self.write_u8(0)?;
                self.write_string(value)
            }
            _ => Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "rowbinary aggregate_funnel only supports String breakdown values",
            )),
        }
    }

    fn write_var_uint(&mut self, mut value: u64) -> io::Result<()> {
        loop {
            let mut byte = (value & 0x7F) as u8;
            value >>= 7;
            if value != 0 {
                byte |= 0x80;
            }
            self.write_u8(byte)?;
            if value == 0 {
                return Ok(());
            }
        }
    }

    fn write_string(&mut self, value: &str) -> io::Result<()> {
        self.write_var_uint(value.len() as u64)?;
        self.inner.write_all(value.as_bytes())
    }

    fn write_u8(&mut self, value: u8) -> io::Result<()> {
        self.inner.write_all(&[value])
    }

    fn write_i8(&mut self, value: i8) -> io::Result<()> {
        self.write_u8(value as u8)
    }

    fn write_u32(&mut self, value: u32) -> io::Result<()> {
        self.inner.write_all(&value.to_le_bytes())
    }

    fn write_f64(&mut self, value: f64) -> io::Result<()> {
        self.inner.write_all(&value.to_le_bytes())
    }

    fn write_uuid(&mut self, value: &Uuid) -> io::Result<()> {
        self.inner.write_all(&value.as_u128().to_le_bytes())
    }
}
