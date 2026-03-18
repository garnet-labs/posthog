use anyhow::{bail, ensure, Result};
use governor::Quota;
use std::num::NonZeroU32;

/// Parse a Django SimpleRateThrottle-style rate string into a governor Quota
///
/// Supported formats:
/// - "N/second" - N requests per second
/// - "N/minute" - N requests per minute
/// - "N/hour" - N requests per hour
/// - "N/day" - N requests per day
///
/// Only the first character of the period is significant ('s', 'm', 'h', 'd').
///
/// Examples:
/// ```
/// use feature_flags::api::rate_parser::parse_rate_string;
/// use std::num::NonZeroU32;
///
/// let quota = parse_rate_string("600/minute").unwrap();
/// let quota = parse_rate_string("1200/hour").unwrap();
/// let quota = parse_rate_string("100/second").unwrap();
/// ```
pub fn parse_rate_string(rate_str: &str) -> Result<Quota> {
    let rate_str = rate_str.trim();

    // Split on '/' to get number and period
    let (num_str, period_str) = rate_str
        .split_once('/')
        .filter(|(_, rest)| !rest.contains('/'))
        .ok_or_else(|| {
            anyhow::anyhow!(
                "invalid rate format: '{rate_str}'. Expected format: 'N/period' (e.g., '600/minute')"
            )
        })?;

    // Parse the number part
    let num_str = num_str.trim();
    let num: u32 = num_str
        .parse()
        .map_err(|_| anyhow::anyhow!("invalid rate number: '{num_str}'"))?;

    ensure!(num > 0, "rate must be greater than zero");

    // Safe: we just verified num > 0
    let num = NonZeroU32::new(num).unwrap();

    // Parse the period part (only first character matters)
    let period_str = period_str.trim().to_lowercase();
    let period_char = period_str.chars().next().ok_or_else(|| {
        anyhow::anyhow!(
            "invalid time period: '{}'. Valid periods: second, minute, hour, day",
            period_str
        )
    })?;

    // Create quota based on period
    let quota = match period_char {
        's' => Quota::per_second(num),
        'm' => Quota::per_minute(num),
        'h' => Quota::per_hour(num),
        'd' => Quota::with_period(std::time::Duration::from_secs(86400))
            .ok_or_else(|| anyhow::anyhow!("invalid time period: 'day'"))?
            .allow_burst(num),
        _ => bail!(
            "invalid time period: '{}'. Valid periods: second, minute, hour, day",
            period_str
        ),
    };

    Ok(quota)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_valid_rate_strings() {
        assert!(parse_rate_string("600/minute").is_ok());
        assert!(parse_rate_string("1200/hour").is_ok());
        assert!(parse_rate_string("100/second").is_ok());
        assert!(parse_rate_string("2400/day").is_ok());
    }

    #[test]
    fn test_parse_with_whitespace() {
        assert!(parse_rate_string(" 600 / minute ").is_ok());
        assert!(parse_rate_string("600/minute ").is_ok());
        assert!(parse_rate_string(" 600/minute").is_ok());
    }

    #[test]
    fn test_parse_first_char_only() {
        // Only first character of period matters (Django behavior)
        assert!(parse_rate_string("600/m").is_ok());
        assert!(parse_rate_string("600/min").is_ok());
        assert!(parse_rate_string("600/minutes").is_ok());
        assert!(parse_rate_string("100/s").is_ok());
        assert!(parse_rate_string("100/sec").is_ok());
        assert!(parse_rate_string("100/seconds").is_ok());
        assert!(parse_rate_string("1200/h").is_ok());
        assert!(parse_rate_string("1200/hr").is_ok());
        assert!(parse_rate_string("1200/hours").is_ok());
        assert!(parse_rate_string("2400/d").is_ok());
        assert!(parse_rate_string("2400/day").is_ok());
        assert!(parse_rate_string("2400/days").is_ok());
    }

    #[test]
    fn test_parse_case_insensitive() {
        assert!(parse_rate_string("600/MINUTE").is_ok());
        assert!(parse_rate_string("600/Minute").is_ok());
        assert!(parse_rate_string("100/SECOND").is_ok());
    }

    #[test]
    fn test_invalid_format_no_slash() {
        let err = parse_rate_string("600").unwrap_err();
        assert!(err.to_string().contains("invalid rate format"));
    }

    #[test]
    fn test_invalid_format_multiple_slashes() {
        let err = parse_rate_string("600/minute/extra").unwrap_err();
        assert!(err.to_string().contains("invalid rate format"));
    }

    #[test]
    fn test_invalid_format_empty_period() {
        let err = parse_rate_string("600/").unwrap_err();
        assert!(err.to_string().contains("invalid time period"));
    }

    #[test]
    fn test_invalid_number() {
        let err = parse_rate_string("abc/minute").unwrap_err();
        assert!(err.to_string().contains("invalid rate number"));
    }

    #[test]
    fn test_invalid_number_negative() {
        let err = parse_rate_string("-600/minute").unwrap_err();
        assert!(err.to_string().contains("invalid rate number"));
    }

    #[test]
    fn test_invalid_number_float() {
        let err = parse_rate_string("600.5/minute").unwrap_err();
        assert!(err.to_string().contains("invalid rate number"));
    }

    #[test]
    fn test_zero_rate() {
        let err = parse_rate_string("0/minute").unwrap_err();
        assert!(err.to_string().contains("rate must be greater than zero"));
    }

    #[test]
    fn test_invalid_period() {
        let err = parse_rate_string("600/invalid").unwrap_err();
        assert!(err.to_string().contains("invalid time period"));
    }

    #[test]
    fn test_invalid_period_year() {
        // 'y' for year is not supported
        let err = parse_rate_string("600/year").unwrap_err();
        assert!(err.to_string().contains("invalid time period"));
    }

    #[test]
    fn test_quota_values() {
        let quota = parse_rate_string("600/minute").unwrap();
        assert!(format!("{quota:?}").contains("600"));
    }
}
