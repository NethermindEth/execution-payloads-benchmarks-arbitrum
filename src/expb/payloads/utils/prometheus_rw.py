"""Lightweight Prometheus remote write client using manual protobuf encoding."""

import struct
import time

import requests
import snappy


def _encode_varint(value: int) -> bytes:
    """Encode an integer as a protobuf varint."""
    result = b""
    while value > 127:
        result += bytes([(value & 0x7F) | 0x80])
        value >>= 7
    result += bytes([value])
    return result


def _encode_signed_varint(value: int) -> bytes:
    """Encode a signed integer as a protobuf varint (zigzag encoding not needed for timestamps)."""
    if value < 0:
        value += 1 << 64
    return _encode_varint(value)


def _encode_field(field_number: int, wire_type: int, data: bytes) -> bytes:
    """Encode a protobuf field tag + data."""
    tag = _encode_varint((field_number << 3) | wire_type)
    if wire_type == 2:  # length-delimited
        return tag + _encode_varint(len(data)) + data
    return tag + data


def _encode_label(name: str, value: str) -> bytes:
    """Encode a prometheus_prompb.Label message."""
    msg = _encode_field(1, 2, name.encode("utf-8"))
    msg += _encode_field(2, 2, value.encode("utf-8"))
    return msg


def _encode_sample(value: float, timestamp_ms: int) -> bytes:
    """Encode a prometheus_prompb.Sample message."""
    msg = _encode_field(1, 1, struct.pack("<d", value))
    msg += _encode_field(2, 0, b"")  # placeholder
    # Re-encode field 2 properly as varint
    msg = _encode_field(1, 1, struct.pack("<d", value))
    msg += _encode_signed_varint((2 << 3) | 0)  # field 2, wire type 0
    msg = _encode_field(1, 1, struct.pack("<d", value))
    # Simpler approach: build sample manually
    result = b""
    # field 1: double value (wire type 1 = 64-bit)
    result += _encode_varint((1 << 3) | 1)
    result += struct.pack("<d", value)
    # field 2: int64 timestamp (wire type 0 = varint)
    result += _encode_varint((2 << 3) | 0)
    result += _encode_signed_varint(timestamp_ms)
    return result


def _encode_timeseries(labels: list[tuple[str, str]], samples: list[tuple[float, int]]) -> bytes:
    """Encode a prometheus_prompb.TimeSeries message."""
    msg = b""
    for name, value in labels:
        label_bytes = _encode_label(name, value)
        msg += _encode_field(1, 2, label_bytes)
    for value, timestamp_ms in samples:
        sample_bytes = _encode_sample(value, timestamp_ms)
        msg += _encode_field(2, 2, sample_bytes)
    return msg


def _encode_write_request(timeseries_list: list[bytes]) -> bytes:
    """Encode a prometheus_prompb.WriteRequest message."""
    msg = b""
    for ts in timeseries_list:
        msg += _encode_field(1, 2, ts)
    return msg


def push_metrics(
    endpoint: str,
    metrics: dict[str, float],
    labels: dict[str, str],
    basic_auth: tuple[str, str] | None = None,
    extra_tags: list[str] | None = None,
) -> bool:
    """Push gauge metrics to a Prometheus remote write endpoint.

    Args:
        endpoint: Prometheus remote write URL
        metrics: dict of metric_name -> value (e.g. {"k6_http_req_duration_avg": 5.09})
        labels: common labels for all metrics (e.g. {"testid": "...", "group": "..."})
        basic_auth: optional (username, password) tuple
        extra_tags: optional list of "key=value" tag strings

    Returns:
        True if push succeeded, False otherwise
    """
    timestamp_ms = int(time.time() * 1000)

    # Build common labels
    common_labels = [("__name__", "")]  # placeholder, replaced per metric
    for k, v in labels.items():
        common_labels.append((k, v))
    if extra_tags:
        for tag in extra_tags:
            if "=" in tag:
                k, v = tag.split("=", 1)
                common_labels.append((k, v))

    timeseries_list = []
    for metric_name, value in metrics.items():
        metric_labels = [(k, v) for k, v in common_labels]
        metric_labels[0] = ("__name__", metric_name)
        ts = _encode_timeseries(metric_labels, [(value, timestamp_ms)])
        timeseries_list.append(ts)

    write_request = _encode_write_request(timeseries_list)
    compressed = snappy.compress(write_request)

    headers = {
        "Content-Type": "application/x-protobuf",
        "Content-Encoding": "snappy",
        "X-Prometheus-Remote-Write-Version": "0.1.0",
    }

    auth = None
    if basic_auth:
        auth = basic_auth

    try:
        response = requests.post(
            endpoint,
            data=compressed,
            headers=headers,
            auth=auth,
            timeout=10,
        )
        return response.status_code in (200, 204)
    except Exception:
        return False
