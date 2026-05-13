"""NCBI BLAST REST API client with per-sequence local caching.

Uses only stdlib: urllib, xml.etree.ElementTree, json, hashlib, time.
No additional pip packages required.
"""
from __future__ import annotations

import hashlib
import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BLAST_CGI = "https://blast.ncbi.nlm.nih.gov/blast/Blast.cgi"
_USER_AGENT = "local-rag-blast/1.0 (educational use)"
POLL_INTERVAL = 15   # seconds between status checks
MAX_POLLS = 40       # give up after ~10 minutes


def _md5(seq: str) -> str:
    return hashlib.md5(seq.strip().upper().encode()).hexdigest()


def _load_cache(cache_path: Path) -> dict:
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(cache_path: Path, cache: dict) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _submit(fasta: str, program: str, database: str, hitlist_size: int) -> tuple[str, int]:
    """Submit FASTA to NCBI BLAST. Returns (RID, RTOE)."""
    data = urlencode(
        {
            "CMD": "Put",
            "PROGRAM": program,
            "DATABASE": database,
            "QUERY": fasta,
            "HITLIST_SIZE": str(hitlist_size),
            "FORMAT_TYPE": "XML",
            "EXPECT": "1e-5",
        }
    ).encode("ascii")
    req = Request(
        BLAST_CGI,
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": _USER_AGENT,
        },
    )
    try:
        with urlopen(req, timeout=60) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except (URLError, OSError) as exc:
        raise RuntimeError(f"BLAST submission failed: {exc}") from exc

    rid = rtoe = None
    for line in html.splitlines():
        stripped = line.strip()
        if stripped.startswith("RID ="):
            rid = stripped.split("=", 1)[1].strip()
        elif stripped.startswith("RTOE ="):
            try:
                rtoe = int(stripped.split("=", 1)[1].strip())
            except ValueError:
                pass
    if not rid:
        raise RuntimeError("RID not found in BLAST submission response")
    return rid, rtoe or POLL_INTERVAL


def _poll(rid: str) -> str:
    """Poll until results are ready, return XML string."""
    url = BLAST_CGI + "?" + urlencode({"CMD": "Get", "RID": rid, "FORMAT_TYPE": "XML"})
    req = Request(url, headers={"User-Agent": _USER_AGENT})
    for _ in range(MAX_POLLS):
        time.sleep(POLL_INTERVAL)
        try:
            with urlopen(req, timeout=60) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
        except (URLError, OSError) as exc:
            raise RuntimeError(f"BLAST poll failed: {exc}") from exc
        if "Status=WAITING" in content:
            continue
        if "Status=FAILED" in content or "Status=UNKNOWN" in content:
            raise RuntimeError(f"BLAST job {rid} failed or expired")
        return content
    raise RuntimeError(f"BLAST timed out after {MAX_POLLS * POLL_INTERVAL}s (RID={rid})")


def _parse_xml(xml: str) -> dict[str, list[dict]]:
    """Parse multi-query BLAST XML. Returns {query_title: [hit, ...]}."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise RuntimeError(f"BLAST XML parse error: {exc}") from exc

    results: dict[str, list[dict]] = {}
    for iteration in root.iter("Iteration"):
        query_def = (iteration.findtext("Iteration_query-def") or "").split()[0]
        hits = []
        for hit in iteration.iter("Hit"):
            hit_def = hit.findtext("Hit_def") or ""
            accession = hit.findtext("Hit_accession") or ""
            # Extract species-level label: text before "[" organism tag
            if "[" in hit_def:
                species_label = hit_def.split("[")[0].strip()
            else:
                species_label = hit_def.split(",")[0].strip()
            # Best HSP identity %
            best: float | None = None
            for hsp in hit.iter("Hsp"):
                ident = hsp.findtext("Hsp_identity")
                length = hsp.findtext("Hsp_align-len")
                if ident and length:
                    try:
                        pct = round(float(ident) / float(length) * 100, 2)
                        if best is None or pct > best:
                            best = pct
                    except (ValueError, ZeroDivisionError):
                        pass
            hits.append(
                {
                    "accession": accession,
                    "hit_def": hit_def,
                    "species_label": species_label,
                    "identity_pct": best,
                }
            )
        results[query_def] = hits
    return results


def blast_entries(
    entries: list[dict],
    program: str = "blastn",
    database: str = "nt",
    hitlist_size: int = 10,
    cache_path: Path | None = None,
    force: bool = False,
) -> dict[str, list[dict]]:
    """BLAST multiple ASV entries against NCBI. Returns {asv_id: [hit, ...]}.

    Each entry must have 'asv_id' and 'sequence'.
    Uncached sequences are submitted as one multi-FASTA batch job.
    Results are cached per sequence MD5 in cache_path.
    """
    if cache_path is None:
        cache_path = Path("data/.blast_cache.json")

    cache = _load_cache(cache_path)
    results: dict[str, list[dict]] = {}
    to_submit: list[dict] = []

    for entry in entries:
        if not entry.get("sequence"):
            results[entry["asv_id"]] = []
            continue
        key = _md5(entry["sequence"])
        if not force and key in cache:
            results[entry["asv_id"]] = cache[key]
        else:
            to_submit.append(entry)

    if to_submit:
        fasta = "".join(f">{e['asv_id']}\n{e['sequence']}\n" for e in to_submit)
        rid, rtoe = _submit(fasta, program, database, hitlist_size)
        time.sleep(max(rtoe, 5))
        xml = _poll(rid)
        parsed = _parse_xml(xml)

        for entry in to_submit:
            hits = parsed.get(entry["asv_id"], [])
            results[entry["asv_id"]] = hits
            cache[_md5(entry["sequence"])] = hits

        _save_cache(cache_path, cache)

    return results
