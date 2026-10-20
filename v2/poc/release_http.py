"""Bounded GitHub metadata retries with allowlisted, credential-free evidence."""
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

PREFIX = 'Flow GitHub quota: '
MAX_ATTEMPTS = 4
MAX_WAIT = 3900


def _number(value):
    text = str(value or '')
    return int(text) if re.fullmatch(r'[0-9]{1,12}', text) else None


def _date(value):
    try:
        date = parsedate_to_datetime(value)
        return date.timestamp() if date.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


def _utc(epoch):
    try:
        return datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace('+00:00', 'Z')
    except (ValueError, OverflowError, OSError):
        return None


def _budget():
    value = _number(os.environ.get('FLOW_GITHUB_RETRY_WAIT_SECONDS', '300'))
    if value is None or value > MAX_WAIT:
        raise ValueError('FLOW_GITHUB_RETRY_WAIT_SECONDS must be an integer from 0 to 3900')
    return value


def github_json(request, *, evidence=None):
    """Retry only quota responses. Never retry before GitHub's advertised time.

    Interactive consumers wait at most five minutes; release verification can
    allow one full hourly reset. The budget covers all sleeps in this request,
    and four attempts also bound missing/stale-header secondary-limit retries.
    """
    budget = _budget()
    deadline = time.monotonic() + budget
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            headers = error.headers or {}
            remaining = _number(headers.get('X-RateLimit-Remaining'))
            reset = _number(headers.get('X-RateLimit-Reset'))
            retry_after = _number(headers.get('Retry-After'))
            retry_date = _date(headers.get('Retry-After')) if retry_after is None else None
            now = time.time()
            waits = []
            if retry_after is not None:
                waits.append(retry_after)
            if retry_date is not None:
                waits.append(retry_date - now + 1)
            if reset is not None and remaining == 0:
                waits.append(reset - now + 1)
            body_limited = False
            if error.code == 403 and remaining != 0 and retry_after is None and retry_date is None:
                # Secondary limits can leave primary quota available and omit
                # Retry-After. Inspect only GitHub's bounded JSON message for
                # classification; never retain or echo the body/message.
                try:
                    raw = error.read(8193)
                    payload = json.loads(raw) if len(raw) <= 8192 else {}
                    message = payload.get('message', '') if isinstance(payload, dict) else ''
                    body_limited = isinstance(message, str) and message.startswith((
                        'API rate limit exceeded', 'You have exceeded a secondary rate limit'))
                except (ValueError, OSError):
                    pass
            limited = error.code == 429 or (error.code == 403 and (
                remaining == 0 or retry_after is not None or retry_date is not None or body_limited))
            # Missing or already expired guidance: GitHub's secondary-limit
            # fallback is at least one minute, with bounded exponential backoff.
            wait = math.ceil(max(waits)) if waits else 60 * 2 ** (attempt - 1)
            if wait <= 0:
                wait = 60 * 2 ** (attempt - 1)
            retry = limited and attempt < MAX_ATTEMPTS and wait <= deadline - time.monotonic()
            endpoint = urllib.parse.urlsplit(request.full_url)
            safe_path = (endpoint.path if endpoint.hostname == 'api.github.com' and re.fullmatch(
                r'/repos/[\w.-]+/[\w.-]+/releases/(latest|tags/v\d+\.\d+\.\d+)', endpoint.path) else '[redacted]')
            server_date = _date(headers.get('Date'))
            row = {
                'status': error.code, 'attempt': attempt,
                'endpoint': safe_path,
                'auth_mode': 'token' if request.has_header('Authorization') else 'anonymous',
                'observed_at': _utc(now),
                'limit': _number(headers.get('X-RateLimit-Limit')),
                'remaining': remaining, 'used': _number(headers.get('X-RateLimit-Used')),
                'reset_epoch': reset, 'reset_at': _utc(reset) if reset is not None else None,
                'retry_after_seconds': retry_after,
                'retry_after_at': _utc(retry_date) if retry_date is not None else None,
                'server_date': _utc(server_date) if server_date is not None else None,
                'retry_in_seconds': wait if retry else None,
                'required_wait_seconds': wait if limited else None,
                'wait_budget_seconds': budget,
                'decision': ('retry' if retry else 'http-error' if not limited else
                             'quota-attempt-limit' if attempt == MAX_ATTEMPTS else 'quota-budget-exhausted'),
            }
            request_id = headers.get('X-GitHub-Request-Id', '')
            if re.fullmatch(r'[0-9A-F:]{1,80}', request_id):
                row['request_id'] = request_id
            if evidence is not None:
                evidence.append(row)
            print(PREFIX + json.dumps(row, sort_keys=True), file=sys.stderr, flush=True)
            error.close()
            if not retry:
                # Do not echo the reason, URL, headers, or response body. They
                # may contain credentials or arbitrary server-controlled text.
                raise ValueError('GitHub release metadata HTTP ' + str(error.code) +
                                 '; ' + row['decision'] + '. See Flow GitHub quota evidence above.') from None
            time.sleep(wait)
