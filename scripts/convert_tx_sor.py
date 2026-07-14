#!/usr/bin/env python3
"""
Convert Texas DPS Public SOR BCP tab-delimited dump → flat CSV for import_csv().

Usage (from repo root):
    python scripts/convert_tx_sor.py
    python scripts/convert_tx_sor.py --source "C:\\Users\\Zero\\Downloads\\TX"
    python scripts/convert_tx_sor.py --import-db
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

NS = {"b": "http://schemas.microsoft.com/sqlserver/2004/bulkload/format"}
TX_SOURCE_URL = (
    "https://publicsite.dps.texas.gov/SexOffenderRegistry/Search/Rapsheet?sid={sid}"
)

# CRS / TX PERSON field codes not present in TableCodes.txt
_PERSON_FALLBACK: Dict[Tuple[str, str], str] = {
    ("SEX_COD", "M"): "MALE",
    ("SEX_COD", "F"): "FEMALE",
    ("SEX_COD", "U"): "UNKNOWN",
    ("ETH_COD", "H"): "HISPANIC",
    ("ETH_COD", "N"): "NOT HISPANIC",
    ("ETH_COD", "U"): "UNKNOWN",
    ("HAI_COD", "BLK"): "BLACK",
    ("HAI_COD", "BRO"): "BROWN",
    ("HAI_COD", "BLN"): "BLOND",
    ("HAI_COD", "BLU"): "BLUE",
    ("HAI_COD", "GRY"): "GRAY",
    ("HAI_COD", "GRN"): "GREEN",
    ("HAI_COD", "ONG"): "ORANGE",
    ("HAI_COD", "PLE"): "PURPLE",
    ("HAI_COD", "PNK"): "PINK",
    ("HAI_COD", "RED"): "RED",
    ("HAI_COD", "SDY"): "SANDY",
    ("HAI_COD", "WHI"): "WHITE",
    ("HAI_COD", "XXX"): "UNKNOWN",
    ("EYE_COD", "BLK"): "BLACK",
    ("EYE_COD", "BLU"): "BLUE",
    ("EYE_COD", "BRO"): "BROWN",
    ("EYE_COD", "GRY"): "GRAY",
    ("EYE_COD", "GRN"): "GREEN",
    ("EYE_COD", "HAZ"): "HAZEL",
    ("EYE_COD", "MAR"): "MAROON",
    ("EYE_COD", "MUL"): "MULTICOLORED",
    ("EYE_COD", "PNK"): "PINK",
    ("EYE_COD", "XXX"): "UNKNOWN",
}

CSV_FIELDS = [
    "first_name",
    "middle_name",
    "last_name",
    "full_name",
    "race",
    "ethnicity",
    "gender",
    "age",
    "date_of_birth",
    "height",
    "weight",
    "eye_color",
    "hair_color",
    "state",
    "county",
    "city",
    "address",
    "zip_code",
    "latitude",
    "longitude",
    "offense_type",
    "offense_description",
    "crime",
    "risk_level",
    "conviction_date",
    "registration_date",
    "last_verified",
    "source_state",
    "source_url",
    "external_id",
    "flags",
    "raw_data_json",
]


def _columns(fmt_dir: Path, table: str) -> List[str]:
    path = fmt_dir / f"{table}.xml"
    if not path.exists():
        return []
    root = ET.parse(path).getroot()
    row = root.find("b:ROW", NS)
    if row is None:
        return []
    return [c.get("NAME") or "" for c in row.findall("b:COLUMN", NS)]


def load_table(src: Path, fmt_dir: Path, table: str) -> List[Dict[str, str]]:
    data_path = src / f"{table}.txt"
    if not data_path.exists():
        return []
    cols = _columns(fmt_dir, table)
    if not cols:
        raise FileNotFoundError(f"No BCP format for {table} at {fmt_dir}")
    rows: List[Dict[str, str]] = []
    with open(data_path, encoding="latin-1", errors="replace") as f:
        for line in f:
            line = line.rstrip("\r\n")
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < len(cols):
                parts.extend([""] * (len(cols) - len(parts)))
            rows.append(dict(zip(cols, parts[: len(cols)])))
    return rows


def load_tablecodes(src: Path) -> Dict[Tuple[str, str, str], str]:
    path = src / "TableCodes.txt"
    out: Dict[Tuple[str, str, str], str] = {}
    if not path.exists():
        return out
    with open(path, encoding="latin-1", errors="replace") as f:
        for line in f:
            parts = line.rstrip("\r\n").split("\t")
            if len(parts) >= 5:
                out[(parts[1], parts[2], parts[3])] = parts[4]
    return out


def decode_code(
    codemap: Dict[Tuple[str, str, str], str],
    tbl: str,
    col: str,
    val: str,
    *,
    person_col: Optional[str] = None,
) -> str:
    v = (val or "").strip()
    if not v:
        return ""
    text = codemap.get((tbl, col, v))
    if text:
        return text
    if person_col:
        text = codemap.get(("PERSON", person_col, v))
        if text:
            return text
        fb = _PERSON_FALLBACK.get((person_col, v.upper()))
        if fb:
            return fb
    return v


def fmt_height(raw: str) -> str:
    v = (raw or "").strip()
    if len(v) == 3 and v.isdigit():
        return f"{int(v[0])}'{int(v[1:]):02d}\""
    return v


def fmt_date(raw: str) -> str:
    v = (raw or "").strip()
    if not v:
        return ""
    if len(v) >= 10 and v[4] == "-":
        return v[:10]
    for fmt in ("%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(v[:26], fmt).date().isoformat()
        except ValueError:
            continue
    return v[:10] if len(v) >= 10 else v


def age_from_dob(dob: str) -> Optional[int]:
    d = fmt_date(dob)
    if not d or len(d) < 10:
        return None
    try:
        born = date.fromisoformat(d[:10])
    except ValueError:
        return None
    today = date.today()
    years = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    return years if years >= 0 else None


def split_first_middle(fna: str) -> Tuple[str, str]:
    parts = (fna or "").strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def street_line(addr: Dict[str, str]) -> str:
    snu = (addr.get("SNU_NBR") or "").strip()
    sna = (addr.get("SNA_TXT") or "").strip()
    sud_c = (addr.get("SUD_COD") or "").strip()
    sud_n = (addr.get("SUD_NBR") or "").strip()
    unit = " ".join(x for x in [sud_c, sud_n] if x)
    parts = [x for x in [snu, sna] if x]
    line = " ".join(parts)
    if unit:
        line = f"{line} {unit}".strip()
    return line


def pick_name(names: Iterable[Dict[str, str]]) -> Dict[str, str]:
    items = list(names)
    if not items:
        return {}
    for pref in ("B", "S", "A"):
        for n in items:
            if (n.get("TYP_COD") or "").strip() == pref:
                return n
    return items[0]


def pick_dob(dobs: Iterable[Dict[str, str]]) -> str:
    items = list(dobs)
    if not items:
        return ""
    for pref in ("B", "S", "A"):
        for d in items:
            if (d.get("TYP_COD") or "").strip() == pref:
                return fmt_date(d.get("DOB_DTE") or "")
    return fmt_date(items[0].get("DOB_DTE") or "")


def offense_key(row: Dict[str, str]) -> Tuple[str, ...]:
    return (
        (row.get("COO_COD") or "").strip(),
        (row.get("COJ_COD") or "").strip(),
        (row.get("JOO_COD") or "").strip(),
        (row.get("OFF_COD") or "").strip(),
        (row.get("VER_NBR") or "").strip(),
    )


def build_offense_lookup(src: Path, fmt_dir: Path) -> Dict[Tuple[str, ...], Dict[str, str]]:
    rows = load_table(src, fmt_dir, "OFF_CODE_SOR")
    out: Dict[Tuple[str, ...], Dict[str, str]] = {}
    for r in rows:
        out[offense_key(r)] = r
    return out


def offense_text(
    off_row: Dict[str, str],
    code_row: Optional[Dict[str, str]],
    codemap: Dict[Tuple[str, str, str], str],
) -> str:
    parts: List[str] = []
    if code_row:
        for key in ("LEN_TXT", "CIT_TXT"):
            t = (code_row.get(key) or "").strip()
            if t:
                parts.append(t)
    off_cod = (off_row.get("OFF_COD") or "").strip()
    if off_cod and off_cod not in " ".join(parts):
        parts.append(off_cod)
    coo = decode_code(codemap, "Offense", "COO_COD", off_row.get("COO_COD") or "")
    coj = decode_code(codemap, "Offense", "COJ_COD", off_row.get("COJ_COD") or "")
    if coo:
        parts.insert(0, coo)
    if coj:
        parts.insert(1 if coo else 0, coj)
    goc = decode_code(codemap, "OFFENSE", "GOC_COD", off_row.get("GOC_COD") or "")
    if goc:
        parts.append(goc)
    ost = decode_code(codemap, "Offense", "OST_COD", off_row.get("OST_COD") or "")
    if ost:
        parts.append(f"Status: {ost}")
    cdd = fmt_date(off_row.get("CDD_DTE") or "")
    if cdd:
        parts.append(f"Conviction: {cdd}")
    return " | ".join(dict.fromkeys(p for p in parts if p))


def convert(
    source: Path,
    output: Path,
    *,
    import_db: bool = False,
    database: Optional[Path] = None,
) -> Dict[str, Any]:
    fmt_dir = source / "SqlBcpFormatFiles"
    if not fmt_dir.is_dir():
        raise FileNotFoundError(f"Missing SqlBcpFormatFiles under {source}")

    codemap = load_tablecodes(source)
    counties = {
        r["COU_COD"]: (r.get("COU_TXT") or "").strip()
        for r in load_table(source, fmt_dir, "Counties")
    }
    agencies = {
        (r.get("ORI_TXT") or "").strip(): (r.get("ATR_TXT") or "").strip()
        for r in load_table(source, fmt_dir, "AGENCY")
    }
    institutes = {
        r["InstituteId"]: (r.get("INS_TXT") or "").strip()
        for r in load_table(source, fmt_dir, "Institute")
    }
    campuses = {
        r["CampusId"]: {
            "campus": (r.get("CAM_TXT") or "").strip(),
            "institute_id": (r.get("InstituteId") or "").strip(),
        }
        for r in load_table(source, fmt_dir, "InstituteCampus")
    }
    offense_codes = build_offense_lookup(source, fmt_dir)

    indv_rows = load_table(source, fmt_dir, "INDV")
    person_by_ind = {r["IND_IDN"]: r for r in load_table(source, fmt_dir, "PERSON")}
    indv_sor_by_ind = {r["IND_IDN"]: r for r in load_table(source, fmt_dir, "INDV_SOR")}

    names_by_per: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for r in load_table(source, fmt_dir, "NAME"):
        names_by_per[r["PER_IDN"]].append(r)

    dobs_by_per: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for r in load_table(source, fmt_dir, "BRTHDATE"):
        dobs_by_per[r["PER_IDN"]].append(r)

    addr_by_id = {r["AddressId"]: r for r in load_table(source, fmt_dir, "Address")}

    addr_events_by_ind: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for r in load_table(source, fmt_dir, "AddressEvent"):
        addr_events_by_ind[r["IND_IDN"]].append(r)

    reg_events_by_ind: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for r in load_table(source, fmt_dir, "RegistrationEvent"):
        reg_events_by_ind[r["IND_IDN"]].append(r)

    edu_events_by_ind: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for r in load_table(source, fmt_dir, "EducationEvent"):
        edu_events_by_ind[r["IND_IDN"]].append(r)

    photos_by_ind: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for r in load_table(source, fmt_dir, "Photo"):
        photos_by_ind[r["IND_IDN"]].append(r)

    offenses_by_ind: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    offense_rows = load_table(source, fmt_dir, "Offense")
    for r in offense_rows:
        offenses_by_ind[r["IND_IDN"]].append(r)

    output.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with open(output, "w", newline="", encoding="utf-8") as fo:
        writer = csv.DictWriter(fo, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()

        for ind in indv_rows:
            ind_id = ind["IND_IDN"]
            dps = (ind.get("DPS_NBR") or "").strip()
            person = person_by_ind.get(ind_id, {})
            per_id = person.get("PER_IDN") or ind_id

            nm = pick_name(names_by_per.get(per_id, []))
            first, middle = split_first_middle(nm.get("FNA_TXT") or "")
            last = (nm.get("LNA_TXT") or "").strip()
            full = " ".join(x for x in [first, middle, last] if x)
            dob = pick_dob(dobs_by_per.get(per_id, []))

            # Latest address event (all statuses included)
            addr_events = sorted(
                addr_events_by_ind.get(ind_id, []),
                key=lambda r: int(r.get("EventId") or 0),
            )
            latest_addr_event = addr_events[-1] if addr_events else {}
            latest_addr = addr_by_id.get(latest_addr_event.get("AddressId") or "", {})

            reg_events = sorted(
                reg_events_by_ind.get(ind_id, []),
                key=lambda r: (r.get("EVT_DTE") or "", int(r.get("EventId") or 0)),
            )
            latest_reg = reg_events[-1] if reg_events else {}
            reg_date = fmt_date(latest_reg.get("EVT_DTE") or "")

            sor = indv_sor_by_ind.get(ind_id, {})
            risk = decode_code(
                codemap, "INDV", "RSK_COD", sor.get("RSK_COD") or ""
            )

            off_list = offenses_by_ind.get(ind_id, [])
            crime_parts: List[str] = []
            conviction_dates: List[str] = []
            offense_records: List[Dict[str, Any]] = []
            for off in off_list:
                code = offense_codes.get(offense_key(off))
                txt = offense_text(off, code, codemap)
                if txt:
                    crime_parts.append(txt)
                cdd = fmt_date(off.get("CDD_DTE") or "")
                if cdd:
                    conviction_dates.append(cdd)
                offense_records.append(
                    {
                        **off,
                        "offense_text": txt,
                        "off_code": dict(code) if code else None,
                    }
                )

            enriched_addr_events: List[Dict[str, Any]] = []
            for ae in addr_events:
                a = addr_by_id.get(ae.get("AddressId") or "", {})
                pdv = decode_code(
                    codemap, "AddressEvent", "PDV_COD", ae.get("PDV_COD") or ""
                )
                enriched_addr_events.append(
                    {
                        **ae,
                        "pdv_text": pdv,
                        "address": {
                            **a,
                            "street": street_line(a),
                            "county_name": counties.get(
                                (a.get("COU_COD") or "").strip(), ""
                            ),
                        },
                    }
                )

            enriched_reg_events: List[Dict[str, Any]] = []
            for re in reg_events:
                ori = (re.get("ORI_TXT") or "").strip()
                enriched_reg_events.append(
                    {
                        **re,
                        "evt_date": fmt_date(re.get("EVT_DTE") or ""),
                        "agency_name": agencies.get(ori, ""),
                    }
                )

            enriched_edu_events: List[Dict[str, Any]] = []
            for ee in edu_events_by_ind.get(ind_id, []):
                pdv = decode_code(
                    codemap, "EducationEvent", "PDV_COD", ee.get("PDV_COD") or ""
                )
                enriched_edu_events.append({**ee, "pdv_text": pdv})

            photo_records = [
                {
                    **p,
                    "pos_date": fmt_date(p.get("POS_DTE") or ""),
                }
                for p in photos_by_ind.get(ind_id, [])
            ]

            raw_blob = {
                "ind_idn": ind_id,
                "indv": ind,
                "person": person,
                "indv_sor": sor,
                "indv_sor_decoded": {
                    "risk_level": risk,
                    "ssz": decode_code(
                        codemap, "INDV", "SSZ_COD", sor.get("SSZ_COD") or ""
                    ),
                    "swd": decode_code(
                        codemap, "INDV", "SWD_COD", sor.get("SWD_COD") or ""
                    ),
                    "ert": decode_code(
                        codemap, "INDV", "ERT_COD", sor.get("ERT_COD") or ""
                    ),
                    "verification_period": decode_code(
                        codemap, "INDV", "VRP_COD", sor.get("VRP_COD") or ""
                    ),
                    "expiration_review_date": fmt_date(sor.get("ERD_DTE") or ""),
                },
                "names": names_by_per.get(per_id, []),
                "birthdates": dobs_by_per.get(per_id, []),
                "address_events": enriched_addr_events,
                "registration_events": enriched_reg_events,
                "education_events": enriched_edu_events,
                "photos": photo_records,
                "offenses": offense_records,
                "missing_tables": [
                    t
                    for t in (
                        "Offense",
                        "Education",
                        "Occupation",
                        "OccupationEvent",
                        "Email",
                        "EmailEvent",
                        "InternetIdentifier",
                        "InternetIdentifierEvent",
                        "Vehicle",
                        "VehicleEvent",
                        "OccupationalLicense",
                        "OccupationalLicenseEvent",
                    )
                    if not (source / f"{t}.txt").exists()
                ],
            }

            lat = (latest_addr.get("LAT_NBR") or "").strip()
            lon = (latest_addr.get("LON_NBR") or "").strip()
            try:
                lat_f = float(lat) if lat and float(lat) != 0.0 else ""
            except ValueError:
                lat_f = ""
            try:
                lon_f = float(lon) if lon and float(lon) != 0.0 else ""
            except ValueError:
                lon_f = ""

            row = {
                "first_name": first,
                "middle_name": middle,
                "last_name": last,
                "full_name": full,
                "race": decode_code(
                    codemap, "PERSON", "RAC_COD", person.get("RAC_COD") or ""
                ),
                "ethnicity": decode_code(
                    codemap,
                    "PERSON",
                    "ETH_COD",
                    person.get("ETH_COD") or "",
                    person_col="ETH_COD",
                ),
                "gender": decode_code(
                    codemap,
                    "PERSON",
                    "SEX_COD",
                    person.get("SEX_COD") or "",
                    person_col="SEX_COD",
                ),
                "age": age_from_dob(dob) or "",
                "date_of_birth": dob,
                "height": fmt_height(person.get("HGT_QTY") or ""),
                "weight": (person.get("WGT_QTY") or "").strip(),
                "eye_color": decode_code(
                    codemap,
                    "PERSON",
                    "EYE_COD",
                    person.get("EYE_COD") or "",
                    person_col="EYE_COD",
                ),
                "hair_color": decode_code(
                    codemap,
                    "PERSON",
                    "HAI_COD",
                    person.get("HAI_COD") or "",
                    person_col="HAI_COD",
                ),
                "state": (latest_addr.get("PLC_COD") or "").strip() or "TX",
                "county": counties.get(
                    (latest_addr.get("COU_COD") or "").strip(), ""
                ),
                "city": (latest_addr.get("CTY_TXT") or "").strip(),
                "address": street_line(latest_addr),
                "zip_code": (latest_addr.get("ZIP_TXT") or "").strip(),
                "latitude": lat_f,
                "longitude": lon_f,
                "offense_type": "",
                "offense_description": "",
                "crime": " | ".join(dict.fromkeys(crime_parts)),
                "risk_level": risk,
                "conviction_date": max(conviction_dates) if conviction_dates else "",
                "registration_date": reg_date,
                "last_verified": reg_date,
                "source_state": "TX",
                "source_url": TX_SOURCE_URL.format(sid=dps) if dps else "",
                "external_id": dps,
                "flags": "tx_bulk",
                "raw_data_json": json.dumps(raw_blob, ensure_ascii=False),
            }
            writer.writerow(row)
            written += 1
            if written % 10000 == 0:
                print(f"  converted {written} rows…", flush=True)

    summary = {
        "source": str(source),
        "output": str(output),
        "rows": written,
        "offense_rows_in_dump": len(offense_rows),
        "tables_loaded": sorted(
            p.stem
            for p in source.glob("*.txt")
            if p.is_file() and p.name != "TableCodes.txt"
        ),
    }
    print(f"Wrote {written} rows to {output}", flush=True)

    if import_db:
        from scraper.database import Database

        db_path = database or (ROOT / "data" / "offenders.db")
        print(f"\nImporting into {db_path}…", flush=True)
        db = Database(str(db_path))
        try:
            before = db._conn.execute("SELECT COUNT(*) FROM offenders").fetchone()[0]
            # TX rapsheet URLs use ?sid=<DPS number>; `sid` is treated as a
            # volatile session param by normalize_identity_url, so every TX URL
            # collapses to the same base and URL-based skip is invalid (and slow).
            # Identity merge (external_id/name+DOB) still runs via merge_sources.
            result = db.import_csv(
                str(output),
                state="TX",
                skip_existing_urls=False,
                merge_sources=True,
            )
            after = db._conn.execute("SELECT COUNT(*) FROM offenders").fetchone()[0]
            summary["import"] = result
            summary["db_rows_before"] = before
            summary["db_rows_after"] = after
            print(
                f"Import done: imported={result.get('imported', 0)} "
                f"merged={result.get('merged', 0)} skipped={result.get('skipped', 0)} "
                f"total_rows={result.get('total_rows', 0)} "
                f"(DB {before} → {after})",
                flush=True,
            )
        finally:
            db.close()

    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--source",
        default=r"C:\Users\Zero\Downloads\TX",
        help="TX BCP dump directory",
    )
    ap.add_argument(
        "--output",
        default=str(ROOT / "data" / "downloads" / "TX.csv"),
        help="Output CSV path",
    )
    ap.add_argument(
        "--import-db",
        action="store_true",
        help="Import CSV into data/offenders.db after conversion",
    )
    ap.add_argument(
        "--database",
        default=str(ROOT / "data" / "offenders.db"),
        help="SQLite path for --import-db",
    )
    args = ap.parse_args()

    convert(
        Path(args.source),
        Path(args.output),
        import_db=args.import_db,
        database=Path(args.database),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
