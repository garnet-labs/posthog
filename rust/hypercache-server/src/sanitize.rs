//! Config sanitization for public-facing responses.
//!
//! Matches Python's `sanitize_config_for_public_cdn` behavior:
//! - Removes `siteAppsJS` (raw JS only needed for array.js bundle, not JSON API)
//! - Removes `sessionRecording.domains` (internal field, not needed by SDK)
//! - Sets `sessionRecording` to `false` if request origin not in permitted domains

use axum::http::HeaderMap;
use serde_json::{json, Value};

const AUTHORIZED_MOBILE_CLIENTS: &[&str] = &[
    "posthog-android",
    "posthog-ios",
    "posthog-react-native",
    "posthog-flutter",
];

/// Sanitize cached config before returning to clients.
pub fn sanitize_config_for_client(cached_config: &mut Value, headers: &HeaderMap) {
    if let Some(obj) = cached_config.as_object_mut() {
        obj.remove("siteAppsJS");
    }

    let session_recording = match cached_config.get_mut("sessionRecording") {
        Some(sr) => sr,
        None => return,
    };

    let obj = match session_recording.as_object_mut() {
        Some(o) => o,
        None => return,
    };

    let domains = obj.remove("domains");

    if let Some(domains_value) = domains {
        if let Some(domains_array) = domains_value.as_array() {
            let domain_strings: Vec<String> = domains_array
                .iter()
                .filter_map(|d| d.as_str().map(String::from))
                .collect();

            // Empty domains list means always permitted
            if !domain_strings.is_empty() && !on_permitted_domain(&domain_strings, headers) {
                *session_recording = json!(false);
            }
        }
    }
}

/// Checks if the request originates from a permitted recording domain.
///
/// Returns true if:
/// - Origin or Referer hostname matches one of the allowed domains (supports wildcards)
/// - User-Agent indicates an authorized mobile client (android, ios, react-native, flutter)
pub fn on_permitted_domain(recording_domains: &[String], headers: &HeaderMap) -> bool {
    let origin = headers.get("Origin").and_then(|v| v.to_str().ok());
    let referer = headers.get("Referer").and_then(|v| v.to_str().ok());
    let user_agent = headers.get("User-Agent").and_then(|v| v.to_str().ok());

    let origin_hostname = parse_domain(origin);
    let referer_hostname = parse_domain(referer);

    let is_authorized_web_client =
        hostname_in_allowed_url_list(recording_domains, origin_hostname.as_deref())
            || hostname_in_allowed_url_list(recording_domains, referer_hostname.as_deref());

    let is_authorized_mobile_client =
        user_agent.is_some_and(|ua| AUTHORIZED_MOBILE_CLIENTS.iter().any(|&kw| ua.contains(kw)));

    is_authorized_web_client || is_authorized_mobile_client
}

fn parse_domain(url: Option<&str>) -> Option<String> {
    url.and_then(|u| {
        if let Ok(parsed) = url::Url::parse(u) {
            parsed.host_str().map(|h| h.to_string())
        } else {
            None
        }
    })
}

fn hostname_in_allowed_url_list(allowed: &[String], hostname: Option<&str>) -> bool {
    let hostname = match hostname {
        Some(h) => h,
        None => return false,
    };

    let permitted_domains: Vec<String> = allowed
        .iter()
        .filter_map(|url| parse_domain(Some(url)))
        .collect();

    for permitted_domain in permitted_domains {
        if permitted_domain.contains('*') {
            let pattern = format!(
                "^{}$",
                regex::escape(&permitted_domain).replace("\\*", ".*")
            );
            if regex::Regex::new(&pattern).is_ok_and(|re| re.is_match(hostname)) {
                return true;
            }
        } else if permitted_domain == hostname {
            return true;
        }
    }
    false
}
