"""Private, month-partitioned Supabase Storage archive for Alpaca ETF bars.

Credentials are supplied by Streamlit server secrets (never user-visible source).
Nothing in this module submits orders or persists brokerage API credentials.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, timedelta
from io import BytesIO
import gzip
import json
import re
from urllib.parse import quote, urlparse

import pandas as pd
import requests
from .data import ET, validate_bars

SYMBOLS = ('QQQ', 'TQQQ', 'SQQQ')


def month_windows(start: date, end: date):
    """Calendar-month windows; always use FULL months for cache identity."""
    if end < start:
        raise ValueError('End precedes start.')
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        next_month = date(cursor.year+1, 1, 1) if cursor.month == 12 else date(cursor.year, cursor.month+1, 1)
        yield cursor, next_month - timedelta(days=1)
        cursor = next_month


def month_key(month_start: date) -> str:
    return f'alpaca/sip/split/1min/qqq-tqqq-sqqq/{month_start:%Y-%m}.csv.gz'


def encode_bars(bars: pd.DataFrame) -> bytes:
    validated = validate_bars(bars)
    return gzip.compress(validated.to_csv(index=False, float_format='%.10g').encode('utf-8'), compresslevel=6, mtime=0)


def decode_bars(blob: bytes, expected_month: date) -> pd.DataFrame:
    if len(blob) > 15_000_000:
        raise ValueError('Archived month too large; refusing to deserialize.')
    try:
        df = validate_bars(pd.read_csv(BytesIO(gzip.decompress(blob))))
    except Exception as exc:
        raise ValueError('Archived price file failed integrity checks.') from exc
    days = df['timestamp'].dt.tz_convert(ET).dt.date
    if any(d.year != expected_month.year or d.month != expected_month.month for d in days):
        raise ValueError('Archived object contains observations from the wrong month.')
    return df


@dataclass
class SupabaseArchive:
    project_url: str
    secret_key: str
    bucket: str = 'market-edge-history'
    session: requests.Session = field(default_factory=requests.Session, repr=False)

    def __post_init__(self):
        p = urlparse(self.project_url.rstrip('/'))
        if p.scheme != 'https' or not p.hostname or not p.hostname.endswith('.supabase.co'):
            raise ValueError('Expected an HTTPS Supabase project URL (https://PROJECT.supabase.co).')
        if not re.fullmatch(r'[A-Za-z0-9_-]{3,63}', self.bucket):
            raise ValueError('Invalid Supabase bucket name.')
        if not self.secret_key:
            raise ValueError('Missing Supabase server-side secret key.')

    def _headers(self) -> dict:
        h = {'apikey': self.secret_key}
        # Legacy service_role JWT still uses Authorization; newer sb_secret_ API
        # keys are explicitly NOT JWTs and must only be sent as apikey.
        if self.secret_key.startswith('eyJ'):
            h['Authorization'] = 'Bearer ' + self.secret_key
        return h

    def _url(self, path: str) -> str:
        return (self.project_url.rstrip('/') + '/storage/v1/object/' +
                quote(self.bucket, safe='') + '/' + quote(path, safe='/'))

    @staticmethod
    def _storage_error(resp) -> tuple[str, str]:
        """Read Supabase's structured error, not just the HTTP status.

        Supabase's storage gateway can send HTTP 400 for a missing object
        while its JSON body reports code=NoSuchKey and statusCode=404.
        Do not confuse NoSuchBucket or AccessDenied with a cache miss.
        """
        try:
            payload = json.loads(resp.text)
            if not isinstance(payload, dict):
                return '', ''
            return str(payload.get('code', '')).strip(), str(payload.get('message', '')).strip()
        except (ValueError, TypeError):
            return '', ''

    def load(self, month: date) -> pd.DataFrame | None:
        resp = self.session.get(self._url(month_key(month)), headers=self._headers(), timeout=35)
        if resp.ok:
            return decode_bars(resp.content, month)
        code, message = self._storage_error(resp)
        if code == 'NoSuchKey' or (code in ('', 'not_found') and message.lower() == 'object not found'):
            return None  # Expected cache miss: download from Alpaca, then archive.
        if code == 'NoSuchBucket' or (code in ('', 'not_found') and message.lower() == 'bucket not found'):
            raise RuntimeError(f'Supabase storage bucket "{self.bucket}" not found or inaccessible. Create the PRIVATE bucket with this exact name.')
        if code in ('AccessDenied', 'InvalidJWT', 'InvalidSignature', 'Unauthorized'):
            raise RuntimeError(f'Supabase storage access denied ({code}). Verify the server-side key in Streamlit Secrets and bucket permissions.')
        raise RuntimeError(f'Cloud archive read failed (HTTP {resp.status_code}; storage code {code or "unavailable"}). Check Supabase project URL, bucket and server secrets.')

    def save(self, month: date, bars: pd.DataFrame) -> None:
        payload = encode_bars(bars)
        headers = {**self._headers(), 'Content-Type':'application/gzip', 'cache-control':'3600'}
        resp = self.session.post(self._url(month_key(month)), headers=headers, data=payload, timeout=90)
        if resp.ok:
            return
        code, message = self._storage_error(resp)
        if code in ('KeyAlreadyExists', 'ResourceAlreadyExists') or (code == '' and resp.status_code == 409 and 'already' in message.lower()):
            return  # Immutable archival objects: don't silently overwrite.
        if code == 'NoSuchBucket':
            raise RuntimeError(f'Cloud archive write failed: bucket "{self.bucket}" not found. Check Storage settings.')
        raise RuntimeError(f'Cloud archive write failed (HTTP {resp.status_code}; storage code {code or "unavailable"}). Check the private bucket and permissions.')


@dataclass
class ArchivedFetcher:
    """Cache-first range fetcher compatible with run_study(fetcher=...)."""
    archive: SupabaseArchive
    download_month: object | None = None  # None = strict read-only archive
    cache_hits: int = 0
    saved: int = 0
    read_rows: int = 0

    def __call__(self, start_iso: str, end_iso: str) -> pd.DataFrame:
        start, end = date.fromisoformat(start_iso), date.fromisoformat(end_iso)
        items = []
        for month_start, month_end in month_windows(start, end):
            bars = self.archive.load(month_start)
            if bars is None:
                if self.download_month is None:
                    raise ValueError(f'Historical archive missing {month_start:%Y-%m}. Run the archive download to fill this month before backtesting; no Alpaca request was made.')
                bars = self.download_month(month_start.isoformat(), month_end.isoformat())
                # Fail closed: never archive incomplete or mislabeled months.
                if bars.empty:
                    raise ValueError(f'No Alpaca bars for {month_start:%Y-%m}.')
                by_day = bars['timestamp'].dt.tz_convert(ET).dt.date
                if any(d.year != month_start.year or d.month != month_start.month for d in by_day):
                    raise ValueError('Alpaca returned data outside requested month.')
                self.archive.save(month_start, bars)
                self.saved += 1
            else:
                self.cache_hits += 1
            items.append(bars)
        result = pd.concat(items, ignore_index=True)
        dates = result['timestamp'].dt.tz_convert(ET).dt.date
        result = result.loc[(dates >= start) & (dates <= end)].copy()
        if result.empty:
            raise ValueError('No archived trading bars in selected range.')
        self.read_rows += len(result)
        return result.sort_values(['timestamp','symbol']).reset_index(drop=True)