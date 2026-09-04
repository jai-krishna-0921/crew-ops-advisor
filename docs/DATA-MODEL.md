# DATA-RECON: dCortex Crew Ops Advisor dataset

Engineering reference for `data/crew-ops-advisor-dataset/`. Everything below was
read out of the shipped JSON and verified numerically. Nothing in `data/` was
modified.

Root: `/home/jk/Documents/Bessemer-Dcortex/agentic-crew-ops-dvisor/data/crew-ops-advisor-dataset/`
Data dir: `<root>/data/`

| File | Bytes | Top level |
|---|---|---|
| `data/flights.json` | 44,185 | array of 147 objects |
| `data/crew.json` | 29,491 | array of 150 objects |
| `data/rosters.json` | 27,930 | object, 3 keys |
| `data/duty_clocks.json` | 383,765 | array of 150 objects |
| `data/reserve_pool.json` | 5,538 | array of 16 objects |
| `data/certifications.json` | 71,702 | array of 600 objects |
| `data/rules.json` | 1,689 | object, 3 keys |
| `data/costs.json` | 408 | object, 9 keys |
| `data/risk_signals.json` | 20,522 | array of 150 objects |
| `data/scenarios.json` | 50,590 | array of 6 objects |
| `data/questions.json` | 24,423 | array of 38 objects |
| `internal/held_out_scenarios.json` | 5,007 | array of 2 objects (judging only) |
| `README.md`, `validate.py`, `generate.py` | | docs + tooling |

Global conventions, asserted by `rules.json` and confirmed everywhere:

- **All timestamps are UTC and carry a literal trailing `Z`**, format
  `%Y-%m-%dT%H:%M:%SZ`. There is no offset and no sub-minute precision. Parse
  as naive UTC by stripping the `Z`.
- Bare dates are `YYYY-MM-DD` (ISO), no time component.
- Clock-of-day strings in `reserve_pool.oncall_window_utc` are `HH:MM`, UTC.
- Currency INR, integers only in `costs.json`.
- Snapshot ("now") = `2026-09-14T18:00:00Z`. Schedule week =
  2026-09-14 through 2026-09-20 inclusive (7 days). Hub BLR.

---

## 1. File schemas

### 1.1 `flights.json`

Array of 147 objects. All 11 fields present on all 147 records. No nulls.

| Field | Type | Always? | Domain |
|---|---|---|---|
| `flight_id` | str | yes | 147 distinct; exactly `f"{flight_no}-{date}"` (verified True for all 147) |
| `flight_no` | str | yes | 24 values: DX401, DX402, DX403, DX404, DX412, DX413, DX421, DX422, DX423, DX424, DX431, DX432, DX433, DX434, DX451, DX452, DX453, DX454, DX461, DX462, DX588, DX589, DX590, DX591 |
| `date` | str (date) | yes | 2026-09-14 .. 2026-09-20, exactly 21 legs per date |
| `dep_station` | str | yes | BLR, BOM, CCU, COK, DEL, GOI, HYD, MAA (8 stations) |
| `arr_station` | str | yes | same 8 |
| `dep_utc` | str (dt) | yes | 115 distinct; `dep_utc[:10] == date` for all 147 |
| `arr_utc` | str (dt) | yes | 105 distinct; `arr_utc[:10] == date` for all 147 (no leg crosses midnight UTC) |
| `block_hours` | float | yes | {1.0, 1.25, 1.5, 1.75, 2.5, 2.75}; exactly equals `(arr_utc - dep_utc)` in hours for all 147 (0 tolerance) |
| `aircraft` | str | yes | VT-DXA, VT-DXB, VT-DXC, VT-DXD, VT-DXE, VT-DXF |
| `aircraft_type` | str | yes | A320, ATR72 |
| `seats` | int | yes | 162 (A320), 72 (ATR72). Determined solely by `aircraft_type` |

Verbatim example (record 0):

```json
{
  "flight_id": "DX401-2026-09-14",
  "flight_no": "DX401",
  "date": "2026-09-14",
  "dep_station": "BLR",
  "arr_station": "DEL",
  "dep_utc": "2026-09-14T02:30:00Z",
  "arr_utc": "2026-09-14T05:15:00Z",
  "block_hours": 2.75,
  "aircraft": "VT-DXA",
  "aircraft_type": "A320",
  "seats": 162
}
```

Full schedule table. Times repeat identically on every date a flight number
operates, so the timetable is fully described by 24 rows:

| No | Aircraft | Type | Route | Dep | Arr | Block h | Operates on (Sep) |
|---|---|---|---|---|---|---|---|
| DX401 | VT-DXA | A320 | BLR-DEL | 02:30 | 05:15 | 2.75 | 14-20 (7) |
| DX402 | VT-DXA | A320 | DEL-BLR | 06:00 | 08:45 | 2.75 | 14-20 (7) |
| DX403 | VT-DXA | A320 | BLR-MAA | 09:30 | 10:30 | 1.0 | 14-20 (7) |
| DX404 | VT-DXA | A320 | MAA-BLR | 11:15 | 12:15 | 1.0 | 14-20 (7) |
| DX421 | VT-DXB | A320 | BLR-CCU | 03:00 | 05:30 | 2.5 | 14-20 (7) |
| DX422 | VT-DXB | A320 | CCU-BLR | 06:15 | 08:45 | 2.5 | 14-20 (7) |
| DX423 | VT-DXB | A320 | BLR-HYD | 09:30 | 10:45 | 1.25 | 14-20 (7) |
| DX424 | VT-DXB | A320 | HYD-BLR | 11:30 | 12:45 | 1.25 | 14-20 (7) |
| DX431 | VT-DXD | A320 | BLR-BOM | 03:30 | 05:15 | 1.75 | 14-20 (7) |
| DX432 | VT-DXD | A320 | BOM-BLR | 06:00 | 07:45 | 1.75 | 14-20 (7) |
| DX433 | VT-DXD | A320 | BLR-GOI | 08:30 | 09:45 | 1.25 | 14-20 (7) |
| DX434 | VT-DXD | A320 | GOI-BLR | 10:30 | 11:45 | 1.25 | 14-20 (7) |
| DX451 | VT-DXE | ATR72 | BLR-COK | 04:00 | 05:15 | 1.25 | 14-20 (7) |
| DX452 | VT-DXE | ATR72 | COK-BLR | 06:00 | 07:15 | 1.25 | 14-20 (7) |
| DX453 | VT-DXE | ATR72 | BLR-MAA | 08:00 | 09:00 | 1.0 | 14-20 (7) |
| DX454 | VT-DXE | ATR72 | MAA-BLR | 09:45 | 10:45 | 1.0 | 14-20 (7) |
| DX461 | VT-DXF | ATR72 | BLR-HYD | 05:00 | 06:30 | 1.5 | 14-20 (7) |
| DX462 | VT-DXF | ATR72 | HYD-BLR | 07:15 | 08:45 | 1.5 | 14-20 (7) |
| DX412 | VT-DXC | A320 | BLR-BOM | 07:00 | 08:45 | 1.75 | **15, 17, 19** (odd, 3) |
| DX413 | VT-DXC | A320 | BOM-BLR | 09:30 | 11:15 | 1.75 | **15, 17, 19** (3) |
| DX588 | VT-DXC | A320 | BLR-DEL | 12:15 | 15:00 | 2.75 | **15, 17, 19** (3) |
| DX589 | VT-DXC | A320 | DEL-BLR | 05:00 | 07:45 | 2.75 | **14, 16, 18, 20** (even, 4) |
| DX590 | VT-DXC | A320 | BLR-CCU | 08:30 | 11:00 | 2.5 | **14, 16, 18, 20** (4) |
| DX591 | VT-DXC | A320 | CCU-BLR | 11:45 | 14:15 | 2.5 | **14, 16, 18, 20** (4) |

Legs per tail: VT-DXA 28, VT-DXB 28, VT-DXD 28, VT-DXE 28, VT-DXF 14, VT-DXC 21.
Total 147. VT-DXC is the only tail with an alternating two-day rotation
(BLR-BOM-BLR-DEL on odd dates, DEL-BLR-CCU-BLR on even dates), which is why the
only multi-day pairings in the dataset are VT-DXC pairings.

### 1.2 `crew.json`

Array of 150 objects. All 8 fields present on all 150. No nulls.

| Field | Type | Always? | Domain |
|---|---|---|---|
| `crew_id` | str | yes | 150 distinct, pattern `C-\d{4}` |
| `name` | str | yes | 143 distinct. **NOT unique**: `A. Nair`, `R. Iyer`, `H. Naidu`, `S. Kapoor`, `K. Rao`, `P. Sharma`, `N. Verma` each appear twice |
| `rank` | str | yes | `Captain` (28), `First Officer` (29), `Senior Cabin Crew` (26), `Cabin Crew` (67) |
| `base` | str | yes | `BLR` (138), `DEL` (12) |
| `ratings` | list[str] | yes | 1 or 2 of {`A320`, `ATR72`}. Combos: `["A320"]` 96, `["A320","ATR72"]` 27, `["ATR72"]` 27 |
| `seniority` | int | yes | 2 .. 22 |
| `reachability_minutes` | int | yes | {45: 43, 60: 40, 75: 27, 90: 40} |
| `status` | str | yes | `active` (142), `leave` (6), `training` (2) |

Verbatim example (record 0):

```json
{
  "crew_id": "C-1017",
  "name": "A. Verma",
  "rank": "Captain",
  "base": "BLR",
  "ratings": ["A320"],
  "seniority": 16,
  "reachability_minutes": 75,
  "status": "active"
}
```

Rank x base:

| Rank | BLR | DEL |
|---|---|---|
| Captain | 27 | 1 (`C-2210`) |
| First Officer | 25 | 4 |
| Senior Cabin Crew | 25 | 1 |
| Cabin Crew | 61 | 6 |

The 8 non-active crew: `C-1564` leave/Captain/BLR, `C-1606` leave/Cabin Crew/DEL,
`C-2442` leave/Captain/BLR, `C-2561` leave/Cabin Crew/BLR, `C-3816`
training/First Officer/DEL, `C-4104` training/First Officer/DEL, `C-4621`
leave/Cabin Crew/BLR, `C-5015` leave/Captain/BLR. None of them appear on any
pairing and none of them is a reserve.

### 1.3 `rosters.json`

Object with exactly three keys: `pairings`, `flagged_exceptions`, `note`.

`note` = `"Every assignment is legal under rules.json except the flagged exceptions listed here."`

**`pairings`**: array of 39 objects.

| Field | Type | Always? | Domain |
|---|---|---|---|
| `pairing_id` | str | yes | 39 distinct: P-2201..P-2235 (35 consecutive), plus P-2289, P-2291, P-2293, P-2295 |
| `aircraft` | str | yes | tail registration; always equals the `aircraft` of every leg in the pairing (0 mismatches) |
| `days` | list[obj] | yes | 1 day (36 pairings) or 2 days (3 pairings: P-2291, P-2293, P-2295) |
| `crew` | list[obj] | yes | 6 members (25 A320 pairings) or 4 members (14 ATR72 pairings) |

`days[i]` object:

| Field | Type | Domain |
|---|---|---|
| `date` | str (date) | 2026-09-14 .. 2026-09-20 |
| `flights` | list[str] | 2, 3 or 4 `flight_id`s, already in departure order |
| `report_utc` | str (dt) | **always exactly first departure minus 60 min** (42/42 duty days) |
| `release_utc` | str (dt) | **always exactly last arrival plus 30 min** (42/42 duty days) |

`crew[i]` object: `{"crew_id": str, "role": str}`. `role` is drawn from the same
four rank values and **always equals `crew.json[crew_id].rank`** (0 mismatches
across all 39 pairings). Role is not a separate concept from rank here.

Verbatim example (record 0):

```json
{
  "pairing_id": "P-2201",
  "aircraft": "VT-DXA",
  "days": [
    {
      "date": "2026-09-14",
      "flights": ["DX401-2026-09-14", "DX402-2026-09-14", "DX403-2026-09-14", "DX404-2026-09-14"],
      "report_utc": "2026-09-14T01:30:00Z",
      "release_utc": "2026-09-14T12:45:00Z"
    }
  ],
  "crew": [
    {"crew_id": "C-5837", "role": "Captain"},
    {"crew_id": "C-2791", "role": "First Officer"},
    {"crew_id": "C-5597", "role": "Senior Cabin Crew"},
    {"crew_id": "C-4679", "role": "Cabin Crew"},
    {"crew_id": "C-4462", "role": "Cabin Crew"},
    {"crew_id": "C-3757", "role": "Cabin Crew"}
  ]
}
```

**`flagged_exceptions`**: array of exactly 1 object, verbatim:

```json
[
  {
    "crew_id": "C-5417",
    "date": "2026-09-19",
    "rule": "RULE-CERT-06",
    "note": "recurrent_training expires 2026-09-17; assignment on 2026-09-19 is illegal and must be resolved (see scenario S5)."
  }
]
```

Required complements (exact, no variance):

| Aircraft type | Captain | First Officer | Senior Cabin Crew | Cabin Crew | Total | Pairings |
|---|---|---|---|---|---|---|
| A320 | 1 | 1 | 1 | 3 | 6 | 25 |
| ATR72 | 1 | 1 | 1 | 1 | 4 | 14 |

Full pairing table (42 duty days; duty h = release - report; FDP limit =
13.0 - 0.5 * max(0, sectors - 2)):

| Pairing | Tail | Type | Day | Date | Legs | Route | Report | Release | Duty h | Block h | FDP limit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| P-2201 | VT-DXA | A320 | 1/1 | 09-14 | DX401/402/403/404 | BLR-DEL-BLR-MAA-BLR | 01:30 | 12:45 | 11.25 | 7.50 | 12.0 |
| P-2202 | VT-DXA | A320 | 1/1 | 09-15 | DX401/402/403/404 | BLR-DEL-BLR-MAA-BLR | 01:30 | 12:45 | 11.25 | 7.50 | 12.0 |
| P-2203 | VT-DXA | A320 | 1/1 | 09-16 | DX401/402/403/404 | BLR-DEL-BLR-MAA-BLR | 01:30 | 12:45 | 11.25 | 7.50 | 12.0 |
| P-2204 | VT-DXA | A320 | 1/1 | 09-17 | DX401/402/403/404 | BLR-DEL-BLR-MAA-BLR | 01:30 | 12:45 | 11.25 | 7.50 | 12.0 |
| P-2205 | VT-DXA | A320 | 1/1 | 09-18 | DX401/402/403/404 | BLR-DEL-BLR-MAA-BLR | 01:30 | 12:45 | 11.25 | 7.50 | 12.0 |
| P-2206 | VT-DXA | A320 | 1/1 | 09-19 | DX401/402/403/404 | BLR-DEL-BLR-MAA-BLR | 01:30 | 12:45 | 11.25 | 7.50 | 12.0 |
| P-2207 | VT-DXA | A320 | 1/1 | 09-20 | DX401/402/403/404 | BLR-DEL-BLR-MAA-BLR | 01:30 | 12:45 | 11.25 | 7.50 | 12.0 |
| P-2208 | VT-DXB | A320 | 1/1 | 09-14 | DX421/422/423/424 | BLR-CCU-BLR-HYD-BLR | 02:00 | 13:15 | 11.25 | 7.50 | 12.0 |
| P-2209 | VT-DXB | A320 | 1/1 | 09-15 | DX421/422/423/424 | BLR-CCU-BLR-HYD-BLR | 02:00 | 13:15 | 11.25 | 7.50 | 12.0 |
| P-2210 | VT-DXB | A320 | 1/1 | 09-16 | DX421/422/423/424 | BLR-CCU-BLR-HYD-BLR | 02:00 | 13:15 | 11.25 | 7.50 | 12.0 |
| P-2211 | VT-DXB | A320 | 1/1 | 09-17 | DX421/422/423/424 | BLR-CCU-BLR-HYD-BLR | 02:00 | 13:15 | 11.25 | 7.50 | 12.0 |
| P-2212 | VT-DXB | A320 | 1/1 | 09-18 | DX421/422/423/424 | BLR-CCU-BLR-HYD-BLR | 02:00 | 13:15 | 11.25 | 7.50 | 12.0 |
| P-2213 | VT-DXB | A320 | 1/1 | 09-19 | DX421/422/423/424 | BLR-CCU-BLR-HYD-BLR | 02:00 | 13:15 | 11.25 | 7.50 | 12.0 |
| P-2214 | VT-DXB | A320 | 1/1 | 09-20 | DX421/422/423/424 | BLR-CCU-BLR-HYD-BLR | 02:00 | 13:15 | 11.25 | 7.50 | 12.0 |
| P-2215 | VT-DXD | A320 | 1/1 | 09-14 | DX431/432/433/434 | BLR-BOM-BLR-GOI-BLR | 02:30 | 12:15 | 9.75 | 6.00 | 12.0 |
| P-2216 | VT-DXD | A320 | 1/1 | 09-15 | DX431/432/433/434 | BLR-BOM-BLR-GOI-BLR | 02:30 | 12:15 | 9.75 | 6.00 | 12.0 |
| P-2217 | VT-DXD | A320 | 1/1 | 09-16 | DX431/432/433/434 | BLR-BOM-BLR-GOI-BLR | 02:30 | 12:15 | 9.75 | 6.00 | 12.0 |
| P-2218 | VT-DXD | A320 | 1/1 | 09-17 | DX431/432/433/434 | BLR-BOM-BLR-GOI-BLR | 02:30 | 12:15 | 9.75 | 6.00 | 12.0 |
| P-2219 | VT-DXD | A320 | 1/1 | 09-18 | DX431/432/433/434 | BLR-BOM-BLR-GOI-BLR | 02:30 | 12:15 | 9.75 | 6.00 | 12.0 |
| P-2220 | VT-DXD | A320 | 1/1 | 09-19 | DX431/432/433/434 | BLR-BOM-BLR-GOI-BLR | 02:30 | 12:15 | 9.75 | 6.00 | 12.0 |
| P-2221 | VT-DXD | A320 | 1/1 | 09-20 | DX431/432/433/434 | BLR-BOM-BLR-GOI-BLR | 02:30 | 12:15 | 9.75 | 6.00 | 12.0 |
| P-2222 | VT-DXE | ATR72 | 1/1 | 09-14 | DX451/452/453/454 | BLR-COK-BLR-MAA-BLR | 03:00 | 11:15 | 8.25 | 4.50 | 12.0 |
| P-2223 | VT-DXE | ATR72 | 1/1 | 09-15 | DX451/452/453/454 | BLR-COK-BLR-MAA-BLR | 03:00 | 11:15 | 8.25 | 4.50 | 12.0 |
| P-2224 | VT-DXE | ATR72 | 1/1 | 09-16 | DX451/452/453/454 | BLR-COK-BLR-MAA-BLR | 03:00 | 11:15 | 8.25 | 4.50 | 12.0 |
| P-2225 | VT-DXE | ATR72 | 1/1 | 09-17 | DX451/452/453/454 | BLR-COK-BLR-MAA-BLR | 03:00 | 11:15 | 8.25 | 4.50 | 12.0 |
| P-2226 | VT-DXE | ATR72 | 1/1 | 09-18 | DX451/452/453/454 | BLR-COK-BLR-MAA-BLR | 03:00 | 11:15 | 8.25 | 4.50 | 12.0 |
| P-2227 | VT-DXE | ATR72 | 1/1 | 09-19 | DX451/452/453/454 | BLR-COK-BLR-MAA-BLR | 03:00 | 11:15 | 8.25 | 4.50 | 12.0 |
| P-2228 | VT-DXE | ATR72 | 1/1 | 09-20 | DX451/452/453/454 | BLR-COK-BLR-MAA-BLR | 03:00 | 11:15 | 8.25 | 4.50 | 12.0 |
| P-2229 | VT-DXF | ATR72 | 1/1 | 09-14 | DX461/462 | BLR-HYD-BLR | 04:00 | 09:15 | 5.25 | 3.00 | 13.0 |
| P-2230 | VT-DXF | ATR72 | 1/1 | 09-15 | DX461/462 | BLR-HYD-BLR | 04:00 | 09:15 | 5.25 | 3.00 | 13.0 |
| P-2231 | VT-DXF | ATR72 | 1/1 | 09-16 | DX461/462 | BLR-HYD-BLR | 04:00 | 09:15 | 5.25 | 3.00 | 13.0 |
| P-2232 | VT-DXF | ATR72 | 1/1 | 09-17 | DX461/462 | BLR-HYD-BLR | 04:00 | 09:15 | 5.25 | 3.00 | 13.0 |
| P-2233 | VT-DXF | ATR72 | 1/1 | 09-18 | DX461/462 | BLR-HYD-BLR | 04:00 | 09:15 | 5.25 | 3.00 | 13.0 |
| P-2234 | VT-DXF | ATR72 | 1/1 | 09-19 | DX461/462 | BLR-HYD-BLR | 04:00 | 09:15 | 5.25 | 3.00 | 13.0 |
| P-2235 | VT-DXF | ATR72 | 1/1 | 09-20 | DX461/462 | BLR-HYD-BLR | 04:00 | 09:15 | 5.25 | 3.00 | 13.0 |
| P-2289 | VT-DXC | A320 | 1/1 | 09-14 | DX589/590/591 | DEL-BLR-CCU-BLR | 04:00 | 14:45 | 10.75 | 7.75 | 12.5 |
| P-2291 | VT-DXC | A320 | 1/2 | 09-15 | DX412/413/588 | BLR-BOM-BLR-DEL | 06:00 | 15:30 | 9.50 | 6.25 | 12.5 |
| P-2291 | VT-DXC | A320 | 2/2 | 09-16 | DX589/590/591 | DEL-BLR-CCU-BLR | 04:00 | 14:45 | 10.75 | 7.75 | 12.5 |
| P-2293 | VT-DXC | A320 | 1/2 | 09-17 | DX412/413/588 | BLR-BOM-BLR-DEL | 06:00 | 15:30 | 9.50 | 6.25 | 12.5 |
| P-2293 | VT-DXC | A320 | 2/2 | 09-18 | DX589/590/591 | DEL-BLR-CCU-BLR | 04:00 | 14:45 | 10.75 | 7.75 | 12.5 |
| P-2295 | VT-DXC | A320 | 1/2 | 09-19 | DX412/413/588 | BLR-BOM-BLR-DEL | 06:00 | 15:30 | 9.50 | 6.25 | 12.5 |
| P-2295 | VT-DXC | A320 | 2/2 | 09-20 | DX589/590/591 | DEL-BLR-CCU-BLR | 04:00 | 14:45 | 10.75 | 7.75 | 12.5 |

Only 8 distinct duty shapes exist. Duty length range 5.25 h to 11.25 h.

### 1.4 `duty_clocks.json`

Array of 150 objects, one per crew (`crew_id` set is exactly `crew.json`'s).
All 6 fields present on all 150. No nulls (`last_rest_ended` is non-null for all
150, though the generator could produce `null`).

| Field | Type | Always? | Domain |
|---|---|---|---|
| `crew_id` | str | yes | 150 distinct |
| `as_of_utc` | str (dt) | yes | constant `2026-09-14T18:00:00Z` |
| `duty_hours_7d` | float | yes | 0.0 .. 56.4 (137 distinct); 2 dp |
| `flight_hours_28d` | float | yes | 0.0 .. 79.24 (119 distinct); 2 dp |
| `last_rest_ended` | str (dt) | yes | 19 distinct values, `2026-09-03T02:00:00Z` .. `2026-09-15T02:45:00Z` |
| `daily_history` | list[obj] | yes | exactly 28 entries for all 150 crew |

`daily_history[i]` object:

| Field | Type | Domain |
|---|---|---|
| `date` | str (date) | `2026-08-18` .. `2026-09-14`, 28 consecutive days, identical sequence for all 150 crew |
| `duty_hours` | float | 0.0 .. 12.0; 27.7% of the 4200 cells are non-zero |
| `flight_hours` | float | 0.0 .. 8.4 |

Verbatim example (`C-1042`, abbreviated history; the full array has 28 entries):

```json
{
  "crew_id": "C-1042",
  "as_of_utc": "2026-09-14T18:00:00Z",
  "duty_hours_7d": 20.93,
  "flight_hours_28d": 64.27,
  "last_rest_ended": "2026-09-13T02:00:00Z",
  "daily_history": [
    {"date": "2026-08-18", "duty_hours": 0.0, "flight_hours": 0.0},
    {"date": "2026-08-19", "duty_hours": 9.66, "flight_hours": 6.96},
    {"date": "2026-09-12", "duty_hours": 10.94, "flight_hours": 7.88},
    {"date": "2026-09-13", "duty_hours": 0.0, "flight_hours": 0.0},
    {"date": "2026-09-14", "duty_hours": 0.0, "flight_hours": 0.0}
  ]
}
```

Note: `daily_history` days with `duty_hours > 0` and `flight_hours == 0` exist
(228 cells across the dataset). These are non-flying duties (training, ground).
On flying days the ratio duty/flight is one of 1.39, 1.42, 1.43 (synthetic).

### 1.5 `reserve_pool.json`

Array of 16 objects. All 5 fields present on all 16.

| Field | Type | Domain |
|---|---|---|
| `crew_id` | str | C-1329, C-1622, C-2111, C-2210, C-2248, C-2341, C-3305, C-3310, C-3311, C-3312, C-3315, C-3316, C-3555, C-3677, C-4809, C-5418 |
| `base` | str | BLR (12), DEL (4). Always equals `crew.json[crew_id].base` |
| `dates` | list[str] | all 16 carry the full week 2026-09-14 .. 2026-09-20 (7 entries). No reserve has a partial week |
| `oncall_window_utc` | object | `{"start": "HH:MM", "end": "HH:MM"}` |
| `note` | str | constant: `"Callout time must fall inside the on-call window (RULE-BASE-07 applies for base)."` |

Verbatim example (record 0):

```json
{
  "crew_id": "C-3305",
  "base": "BLR",
  "dates": ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18", "2026-09-19", "2026-09-20"],
  "oncall_window_utc": {"start": "00:00", "end": "05:30"},
  "note": "Callout time must fall inside the on-call window (RULE-BASE-07 applies for base)."
}
```

Full reserve roster (joined with `crew.json` and `duty_clocks.json`):

| Crew | Base | Rank | Ratings | Window (UTC) | Reach min | Sen | duty_7d | flight_28d |
|---|---|---|---|---|---|---|---|---|
| C-3305 | BLR | Captain | A320 | 00:00-05:30 | 45 | 10 | **56.40** | 33.60 |
| C-3312 | BLR | First Officer | A320 | 00:00-12:00 | 60 | 6 | 8.39 | 31.46 |
| C-4809 | BLR | Cabin Crew | A320+ATR72 | 00:00-12:00 | 45 | 7 | 6.69 | 16.33 |
| C-3315 | BLR | Captain | ATR72 | 03:00-15:00 | 45 | 5 | 15.15 | 51.93 |
| C-3316 | BLR | First Officer | ATR72 | 03:00-15:00 | 45 | 19 | 0.00 | 18.30 |
| C-1329 | BLR | Cabin Crew | A320+ATR72 | 04:00-16:00 | 45 | 8 | 0.00 | 25.23 |
| C-2111 | BLR | Senior Cabin Crew | A320+ATR72 | 04:00-16:00 | 90 | 8 | 15.22 | 26.33 |
| C-2248 | BLR | Cabin Crew | A320+ATR72 | 04:00-16:00 | 60 | 20 | 14.39 | 30.06 |
| C-3677 | BLR | Senior Cabin Crew | A320+ATR72 | 04:00-16:00 | 45 | 17 | 7.92 | 13.83 |
| C-5418 | BLR | Cabin Crew | A320+ATR72 | 04:00-16:00 | 45 | 9 | 6.92 | 28.84 |
| C-3310 | BLR | Captain | A320 | 06:00-18:00 | 45 | 9 | 0.00 | 9.34 |
| C-3311 | BLR | First Officer | A320 | 06:00-18:00 | 45 | 9 | 17.09 | 39.50 |
| C-1622 | DEL | Cabin Crew | A320 | 03:00-15:00 | 75 | 15 | 0.00 | 13.51 |
| C-2210 | DEL | Captain | A320 | 03:00-15:00 | 60 | 2 | 15.06 | 36.15 |
| C-2341 | DEL | First Officer | A320 | 03:00-15:00 | 45 | 20 | 6.14 | 14.02 |
| C-3555 | DEL | Senior Cabin Crew | A320 | 03:00-15:00 | 60 | 14 | 0.00 | 33.42 |

No reserve is rostered on any pairing (0/16). All 16 are `status: active`.
No window wraps midnight, so window comparison is a plain same-date interval test.

**There is no `standby status` field.** The problem-statement PDF says
`reserve_pool.json` contains "Reserve crew with on-call windows and standby
status". The shipped file has no such field. The only status is
`crew.json.status`, whose enum is `active` / `leave` / `training`.

### 1.6 `certifications.json`

Array of 600 objects = 150 crew x 4 cert types. All 4 fields present on all 600.

| Field | Type | Domain |
|---|---|---|
| `crew_id` | str | 150 distinct, 4 rows each |
| `cert_type` | str | `licence`, `medical_class1`, `recurrent_training`, `dangerous_goods` (150 each) |
| `valid_from` | str (date) | 2024-12-16 .. 2030-02-28 |
| `valid_to` | str (date) | 2026-09-17 .. 2032-02-28 |

Verbatim example (records 0-3, one crew's full set):

```json
[
  {"crew_id": "C-1042", "cert_type": "licence",            "valid_from": "2030-01-24", "valid_to": "2032-01-24"},
  {"crew_id": "C-1042", "cert_type": "medical_class1",     "valid_from": "2025-12-31", "valid_to": "2027-12-31"},
  {"crew_id": "C-1042", "cert_type": "recurrent_training", "valid_from": "2025-05-23", "valid_to": "2027-05-23"},
  {"crew_id": "C-1042", "cert_type": "dangerous_goods",    "valid_from": "2026-05-25", "valid_to": "2028-05-24"}
]
```

**`valid_from` is garbage and must be ignored.** It is generated as
`valid_to - 730 days`, then some `valid_to` values are overwritten with
engineered expiries and `valid_from` is not touched. Consequences:

- `C-1042`'s licence has `valid_from` 2030-01-24, in the future relative to the
  snapshot, yet the crew flies.
- Exactly **1 record has `valid_from > valid_to`**: `C-2087` licence,
  `valid_from` 2028-11-06, `valid_to` 2026-09-18.
- The dataset's own validator (`validate.py`) and the answer keys check
  `valid_to` only, with the test `valid_to >= duty_date` (inclusive: a cert
  expiring on the duty date is still valid that day).

All certs with `valid_to` inside the schedule week or shortly after:

| Crew | Cert type | valid_to | Notes |
|---|---|---|---|
| C-5417 | recurrent_training | 2026-09-17 | the single flagged exception; rostered 09-19 |
| C-2087 | licence | 2026-09-18 | C-2087 is not rostered anywhere in the week, so no base-roster violation |
| C-2091 | medical_class1 | 2026-09-23 | after the week, no violation |
| C-3116 | dangerous_goods | 2026-09-28 | |
| C-5020 | recurrent_training | 2026-10-03 | |
| C-2993 | medical_class1 | 2026-10-08 | |

The last three appear only in the Q04 answer (30-day expiry list).

### 1.7 `rules.json`

Object with three keys: `time_convention` (str), `definitions` (object, 4 keys),
`rules` (array of 7). Reproduced verbatim in section 3.

### 1.8 `costs.json`

Object with 9 keys, all scalar. Reproduced verbatim in section 5.

### 1.9 `risk_signals.json`

Array of 150 objects, one per crew. All 4 fields present on all 150.

| Field | Type | Domain |
|---|---|---|
| `crew_id` | str | 150 distinct |
| `as_of_utc` | str (dt) | constant `2026-09-14T18:00:00Z` |
| `disruption_risk_score` | float | 0.02 .. 0.78, 2 dp, 39 distinct |
| `drivers` | list[str] | 1 or 2 entries from a closed set of 6 strings |

Driver strings and frequency: `baseline` (141), `moderate recent duty load` (5),
`elevated sick-call likelihood: cluster pattern at base` (2), `short-rest
pattern over last 14 days` (1), `two fatigue reports this month` (1),
`certification lapse risk: recurrent_training expiring` (1).

Verbatim example (record 0):

```json
{
  "crew_id": "C-1042",
  "as_of_utc": "2026-09-14T18:00:00Z",
  "disruption_risk_score": 0.78,
  "drivers": ["short-rest pattern over last 14 days", "two fatigue reports this month"]
}
```

Only four crew are given engineered high scores, and they are exactly the four
scenario protagonists:

| Crew | Score | Drivers | Scenario |
|---|---|---|---|
| C-1042 | 0.78 | short-rest pattern over last 14 days; two fatigue reports this month | S2 |
| C-3940 | 0.71 | elevated sick-call likelihood: cluster pattern at base | S6 (VT-DXA) |
| C-1938 | 0.69 | elevated sick-call likelihood: cluster pattern at base | S6 (VT-DXB) |
| C-5417 | 0.64 | certification lapse risk: recurrent_training expiring | S5 |

The next highest score is 0.41 (`C-5392`). There is a clean gap between 0.41 and
0.64, so a "high risk" threshold anywhere in (0.41, 0.64] selects exactly the
four scenario crew. Scores are a **provided input**, never computed.

### 1.10 `scenarios.json`

Array of 6 objects. Every object has exactly `scenario_id`, `difficulty`,
`title`, `event`, `answer_key`. The `event` and `answer_key` shapes differ per
scenario type. Full detail in section 6.

### 1.11 `questions.json`

Array of 38 objects. All 6 fields present on all 38.

| Field | Type | Domain |
|---|---|---|
| `question_id` | str | Q01 .. Q38 |
| `tier` | int | 1 (16 questions), 2 (14), 3 (8) |
| `prompt` | str | 38 distinct |
| `expected_answer` | list \| object \| int \| str | shape varies per question |
| `explanation` | str | 38 distinct |
| `rules_ref` | list[str] | 0 to 2 rule ids |

Verbatim example (Q05, small enough to show whole):

```json
{
  "question_id": "Q05",
  "tier": 1,
  "prompt": "Which aircraft operates DX412 on 2026-09-15, and how many seats does it have?",
  "expected_answer": {"aircraft": "VT-DXC", "aircraft_type": "A320", "seats": 162},
  "explanation": "Lookup in flights.json.",
  "rules_ref": []
}
```

### 1.12 `internal/held_out_scenarios.json`

Array of 2 objects, same shape as `scenarios.json` minus `difficulty`:
`H1` "ATR First Officer sick, 16 Sep" (`answer_key` keys: `options`,
`excluded_candidates`, `expected_choice`) and `H2` "HYD closed 05:00-09:00Z,
19 Sep" (`answer_key` key: `affected_flights`). This is judging material. Treat
as a generalisation check, never as a target.

---

## 2. Relational map

### 2.1 Foreign keys

| From | Field | To | Cardinality | Dangling refs found |
|---|---|---|---|---|
| `rosters.pairings[].days[].flights[]` | flight_id | `flights.flight_id` | 147 refs -> 147 flights, each exactly once | 0 |
| `rosters.pairings[].crew[]` | crew_id | `crew.crew_id` | 210 refs -> 102 distinct crew | 0 |
| `rosters.flagged_exceptions[]` | crew_id | `crew.crew_id` | 1 | 0 |
| `duty_clocks[]` | crew_id | `crew.crew_id` | 150, bijective | 0 |
| `certifications[]` | crew_id | `crew.crew_id` | 600 -> 150, exactly 4 per crew | 0 |
| `risk_signals[]` | crew_id | `crew.crew_id` | 150, bijective | 0 |
| `reserve_pool[]` | crew_id | `crew.crew_id` | 16 -> 16 distinct, strict subset | 0 |
| `scenarios[].event.crew_id`, `.pairing_id` | | crew / pairings | | 0 |
| `scenarios[].answer_key.*[].crew_id` | | `crew.crew_id` | | 0 |
| `questions[].expected_answer` embedded ids | | crew / flights | | 0 |

`flights.aircraft` is not a foreign key to any file; there is no aircraft table.
Tail to type and seats is derivable from any leg (consistent across all legs of
a tail).

**Every referential check passes. Zero orphans, zero dangling references.**
Additional invariants verified:

- `reserve_pool[].base == crew[crew_id].base` for all 16.
- `rosters.pairings[].crew[].role == crew[crew_id].rank` for all 210.
- `rosters.pairings[].aircraft == flights[leg].aircraft` for all 147 legs.
- No crew appears on two pairings on the same calendar date (0 cases).
- No non-active crew (`leave`/`training`) appears on any pairing (0 cases).
- Every one of the 147 legs is covered by exactly one pairing-day. There are no
  uncovered flights and no double-covered flights.

### 2.2 Cardinalities

```
aircraft (6) --< flight (147)
flight (147) --1:1-- pairing-day leg slot (147)
pairing (39) --< pairing-day (42)          1 day x36, 2 days x3
pairing-day (42) --< leg (147)             2 legs x7, 3 legs x7, 4 legs x28
pairing (39) --< crew member (210)         6 members x25 (A320), 4 members x14 (ATR72)
crew (150) --1:1-- duty_clock (150)
duty_clock (150) --< daily_history (4200)  exactly 28 per crew
crew (150) --< certification (600)         exactly 4 per crew, one per cert_type
crew (150) --1:1-- risk_signal (150)
crew (150) --0..1-- reserve_pool entry (16)
```

Crew coverage: 102 of 150 crew appear on at least one pairing. Of the 48 who do
not: 16 are reserves, 8 are `leave`/`training`, and 24 are spare active line
crew (14 Cabin Crew, 4 Senior Cabin Crew, 4 First Officers, 2 Captains).
Roster days per rostered crew: 1 day (6 crew), 2 days (70 crew), 3 days (26).

### 2.3 How a crew member connects to everything

```
crew_id
  |-- crew.json                 rank, base, ratings, seniority, reachability, status
  |-- duty_clocks.json          summary 7d/28d, last_rest_ended, 28-day daily_history
  |-- certifications.json       4 rows -> valid_to per cert_type (valid_from is junk)
  |-- risk_signals.json         provided disruption score + drivers
  |-- reserve_pool.json         present  => reserve, has on-call window
  |                             absent   => line crew or spare; callout is "day-off"
  \-- rosters.json              scan every pairing's crew[] for this crew_id
        \-- pairing_id, and for each days[]:
              date, report_utc, release_utc, flights[]
                \-- flights.json  dep/arr station, dep/arr utc, block_hours,
                                  aircraft, aircraft_type, seats
```

There is **no reverse index** from crew to pairing in the data. A loader must
build `crew_id -> [(date, report, release, duty_h, block_h, pairing_id)]` by
scanning all 39 pairings. Call this the crew's **week duties**. Every downstream
computation (rest, overlap, 7-day duty window, 28-day flight window) needs it.

---

## 3. The seven rules, decoded

`rules.json` shipped verbatim:

```json
{
 "time_convention": "All times UTC. Duty windows use calendar days (UTC dates), inclusive of the duty date.",
 "definitions": {
  "duty_period": "report_utc to release_utc. Report = first departure minus 60 min; release = last arrival plus 30 min.",
  "fdp": "Flight Duty Period = duty period length in hours.",
  "sector": "One flight leg.",
  "reserve_callout": "A reserve may be called out only if the callout time falls inside their on-call window. Once assigned, they operate as line crew (window no longer applies)."
 },
 "rules": [
  {
   "rule_id": "RULE-FDP-01",
   "text": "Max flight duty period 13h, reduced 0.5h per sector beyond the 2nd.",
   "params": {
    "base_fdp_hours": 13.0,
    "reduction_per_extra_sector_hours": 0.5,
    "free_sectors": 2
   }
  },
  {
   "rule_id": "RULE-DUTY-02",
   "text": "Max 60 duty hours in any 7 consecutive calendar days (inclusive of duty date).",
   "params": {
    "max_duty_hours": 60,
    "window_days": 7
   }
  },
  {
   "rule_id": "RULE-FLT-03",
   "text": "Max 100 flight (block) hours in any 28 consecutive calendar days.",
   "params": {
    "max_flight_hours": 100,
    "window_days": 28
   }
  },
  {
   "rule_id": "RULE-REST-04",
   "text": "Min 12h rest between release and next report.",
   "params": {
    "min_rest_hours": 12
   }
  },
  {
   "rule_id": "RULE-QUAL-05",
   "text": "Crew must hold a valid rating for the assigned aircraft type."
  },
  {
   "rule_id": "RULE-CERT-06",
   "text": "All certifications must be valid on the duty date."
  },
  {
   "rule_id": "RULE-BASE-07",
   "text": "Reserve callout from own base only; covering from another base requires deadhead positioning (cost applies)."
  }
 ]
}
```

Note: `RULE-QUAL-05`, `RULE-CERT-06` and `RULE-BASE-07` carry **no `params`
key at all**. A typed loader must make `params` optional.

### RULE-FDP-01, max flight duty period

Params: `base_fdp_hours = 13.0`, `reduction_per_extra_sector_hours = 0.5`,
`free_sectors = 2`.

```
fdp_limit(n_sectors) = 13.0 - 0.5 * max(0, n_sectors - 2)
fdp_actual           = (release_utc - report_utc) in hours
breach               <=> fdp_actual > fdp_limit    (strict >, equality is legal)
```

Sector-reduction table, complete (n = legs in the duty day):

| Sectors | Limit (h) | Present in data |
|---|---|---|
| 1 | 13.0 | no |
| 2 | 13.0 | yes (P-2229..P-2235) |
| 3 | 12.5 | yes (P-2289, P-2291, P-2293, P-2295) |
| 4 | 12.0 | yes (all other pairings) |
| 5 | 11.5 | no |
| 6 | 11.0 | no |
| 7 | 10.5 | no |
| 8 | 10.0 | no |
| n | 13.0 - 0.5*(n-2) | |

Data needed: the duty day's leg count, `report_utc`, `release_utc`.
Confirmed inclusive: S3 rates `DX454-2026-09-17` at `crew_fdp_after_delay 12.0`
against `fdp_limit 12.0` as **"delay (crew legal)"**.

### RULE-DUTY-02, 60 duty hours per rolling 7 calendar days

Params: `max_duty_hours = 60`, `window_days = 7`.

```
window(end_date) = [end_date - 6 days, end_date]      inclusive, UTC calendar dates
duty_window_hours(crew, end_date) =
      SUM over d in window of duty_clocks.daily_history[d].duty_hours
    + SUM over d in window of (release_utc - report_utc) for each rostered duty day on d
breach <=> round(total, 2) > 60          (strict >)
```

Data needed: the crew's full `daily_history` and their week duties. See
section 4 for the numeric proof and the day-boundary overlap.

### RULE-FLT-03, 100 block hours per rolling 28 calendar days

Params: `max_flight_hours = 100`, `window_days = 28`.

Identical shape to RULE-DUTY-02, with `daily_history[d].flight_hours` and
`sum(block_hours of the day's legs)`:

```
flight_window_hours(crew, end_date) =
      SUM daily_history[d].flight_hours          for d in [end-27, end]
    + SUM block hours of rostered legs on d      for d in [end-27, end]
breach <=> total > 100
```

**This rule never binds anywhere in this dataset.** The maximum
`flight_window_hours` over all 150 crew and all 7 week dates is **79.28 h**
(`C-2143` on 2026-09-20), against a 100 h limit. Second highest 79.24
(`C-2143` on 09-14), third 77.57 (`C-4296` on 09-14). The shipped answer keys
list `RULE-FLT-03` in `rules_checked` but the reference implementation that
produced the keys does not actually evaluate it. Implement it anyway (it is
cheap and it is one of the seven), but do not expect it to change any answer.

### RULE-REST-04, minimum 12 h rest

Params: `min_rest_hours = 12`.

```
For a crew's duty periods sorted by report time, for each consecutive pair (a, b):
    rest_hours = (b.report_utc - a.release_utc) in hours
    breach <=> rest_hours < 12          (strict <, exactly 12.0 is legal)
    overlap (double booking) <=> b.report_utc < a.release_utc, which shows up
        as a negative rest value
```

Data needed: all duty periods of the crew across the week, including any
proposed cover duty, merged and sorted. The reference implementation reports
both a rest issue and a separate `double-booked:` issue when the periods
overlap, so a negative rest value is not a bug, it is the encoding.

Directional labelling used in the shipped `excluded_candidates` strings:

- `... rest before COVER on <date> (rest conflict)`: the candidate's own
  existing duty runs too close before the proposed cover.
- `... rest before <PAIRING-ID> on <date> (downstream conflict)`: the proposed
  cover runs too close before one of the candidate's later existing duties.

### RULE-QUAL-05, aircraft rating

No params. Text: "Crew must hold a valid rating for the assigned aircraft type."

```
actype = flights[first leg of first day].aircraft_type
legal  <=> actype in crew.ratings
```

Data needed: `crew.ratings`, `flights.aircraft_type`. This is checked **first**
in the reference implementation and short-circuits: a QUAL failure suppresses
every other reason for that candidate. That is why S1's exclusion list shows
`C-1042` with only `"RULE-QUAL-05: no ATR72 rating"` and nothing else.

`C-2091` (Captain, BLR, `ratings: ["ATR72"]`) is the canonical exclusion case:
it is excluded from every A320 cover and eligible for ATR72 covers.

### RULE-CERT-06, certification validity

No params. Text: "All certifications must be valid on the duty date."

```
legal <=> for every one of the crew's 4 certifications:
              date.fromisoformat(cert.valid_to) >= duty_date
```

`valid_from` is **not** checked (and cannot be, see 1.6). The comparison is
`>=`, so a cert whose `valid_to` equals the duty date is valid that day. For a
multi-day cover, check each day independently.

### RULE-BASE-07, base and deadhead positioning

No params. Text: "Reserve callout from own base only; covering from another base
requires deadhead positioning (cost applies)."

```
base_needed = flights[first leg of first day].dep_station
deadhead    = (crew.base != base_needed)
```

If `deadhead` is false, no positioning applies. If true, the only supported
positioning in this dataset is **DEL to BLR**:

```
positioning arrival = 07:45 if cover_start_date in {09-14, 09-16, 09-18, 09-20}   (DX589)
                      08:45 otherwise                                             (DX402)
new first departure = positioning arrival + 75 min     (15 min transit + 60 min report)
new report time     = positioning arrival + 15 min     ( == new departure - 60 min)
delay_hours         = max(0, new first departure - original first departure) in hours
```

Any other cross-base pairing (that is, a BLR-based crew asked to cover a
DEL-origin duty) is excluded outright with the reason
`"RULE-BASE-07: no same-day positioning flight from base"`. In practice the only
DEL-origin pairing days are `P-2289` day 1 and the day-2 halves of P-2291 /
P-2293 / P-2295, and covers are always evaluated from day 1, so this branch is
rarely exercised.

**Reserve on-call window test** (from `definitions.reserve_callout`, and this is
where the README wording matters):

```
required_report = pairing.days[0].report_utc + delay_hours     (delay from deadhead, if any)
window_start    = date(required_report) at oncall_window_utc.start
window_end      = date(required_report) at oncall_window_utc.end
eligible <=> window_start <= required_report <= window_end      (inclusive on both ends)
```

The window is tested against the **required report time**, **not** against the
scenario's `reported_utc` callout time. The `reported_utc` in each scenario
event is narrative only and never enters the eligibility test. Windows do not
wrap midnight in this dataset, so the same-date construction is safe.

Once assigned, a reserve operates as line crew and the window no longer applies
to later days of a multi-day cover: only day 1's report time is tested.

---

## 4. Clock arithmetic (verified numerically)

### 4.1 The field exists and is named `daily_history`

`duty_clocks.json[i].daily_history` is present on all 150 crew, always 28
entries, always the same 28 dates `2026-08-18` through `2026-09-14`, each entry
`{"date", "duty_hours", "flight_hours"}`. No renaming needed.

### 4.2 The hypothesis, tested

```
duty_window_hours(crew, end_date, days) =
      sum(duty_clocks.daily_history[d].duty_hours  for end-days+1 <= d <= end)
    + sum(roster day duty length (release - report) for end-days+1 <= d <= end)
```

Script: `<scratchpad>/clocks.py`. Actual output:

```
### HYPOTHESIS TEST: duty_hours_7d == wsum(cid, 2026-09-14, 7, duty)
  PASS 150/150  FAIL 0

### HYPOTHESIS TEST: flight_hours_28d == wsum(cid, 2026-09-14, 28, flight)
  PASS 150/150  FAIL 0

### HIST-ONLY variant (no roster contribution)
  duty_hours_7d hist-only PASS 118/150 ; flight_hours_28d hist-only PASS 118/150

### OVERLAP: crew with BOTH history and roster contribution on 2026-09-14
  count=11
    ('C-1326', (9.25, 6.66), [5.25, 3.0])
    ('C-1594', (8.17, 5.88), [8.25, 4.5])
    ('C-1671', (10.16, 7.32), [8.25, 4.5])
    ('C-2083', (10.65, 7.67), [9.75, 6.0])
    ('C-2143', (8.76, 6.31), [11.25, 7.5])
    ('C-2875', (9.44, 6.8), [9.75, 6.0])
    ('C-3897', (8.49, 6.11), [5.25, 3.0])
    ('C-4296', (9.12, 6.57), [10.75, 7.75])
  crew with nonzero roster duty on 09-14: 32
  crew with nonzero history duty on 09-14: 43
  history date range: 2026-08-18 -> 2026-09-14
  roster date range: 2026-09-14 -> 2026-09-20

### C-1042 worked example
  shipped duty_hours_7d = 20.93 flight_hours_28d = 64.27
   2026-09-08 hist=(0.0, 0.0) roster=[0, 0]
   2026-09-09 hist=(9.99, 7.19) roster=[0, 0]
   2026-09-10 hist=(0.0, 0.0) roster=[0, 0]
   2026-09-11 hist=(0.0, 0.0) roster=[0, 0]
   2026-09-12 hist=(10.94, 7.88) roster=[0, 0]
   2026-09-13 hist=(0.0, 0.0) roster=[0, 0]
   2026-09-14 hist=(0.0, 0.0) roster=[0, 0]
  sum7 duty = 20.93
```

**Result: the hypothesis is exactly correct, 150/150 for both summary fields**
(tolerance 0.05, and every case is within float rounding of a 2 dp value).

### 4.3 The deliberate 2026-09-14 overlap

`daily_history` runs to 2026-09-14 inclusive and the roster week starts
2026-09-14, so **2026-09-14 is the only date that can contribute from both
sources**, and it does.

- 43 crew have a non-zero `daily_history` entry on 2026-09-14.
- 32 crew have a rostered duty on 2026-09-14 (P-2201, P-2208, P-2215, P-2222,
  P-2229, P-2289 = 6+6+6+4+4+6 = 32 seats).
- 11 crew have **both** and are therefore double-counted on that date.

The shipped summary fields **do reproduce the double count**: dropping the
roster contribution reproduces `duty_hours_7d` for only 118 of 150 crew, and
those 118 are exactly `150 - 32`. So double counting is the dataset's own
convention, not a bug. Do not "correct" it: doing so will move 32 crew's
`duty_hours_7d` and break every answer key that depends on a 7-day window.

Worked overlap case, `C-2143`: history 09-14 duty 8.76 h, roster 09-14 duty
11.25 h (P-2215, VT-DXD), so 2026-09-14 contributes 20.01 h to that crew's
7-day window.

### 4.4 The general window function

```python
def window_hours(crew_id, end_date, days, kind):   # kind: "duty" or "flight"
    start = end_date - timedelta(days=days - 1)
    total = 0.0
    for entry in duty_clocks[crew_id].daily_history:      # dates <= 2026-09-14
        if start <= entry.date <= end_date:
            total += entry.duty_hours if kind == "duty" else entry.flight_hours
    for wd in week_duties[crew_id]:                       # dates 2026-09-14 .. 09-20
        if start <= wd.date <= end_date:
            total += wd.duty_hours if kind == "duty" else wd.block_hours
    return round(total, 2)

duty_hours_7d    == window_hours(cid, date(2026,9,14), 7,  "duty")     # 150/150
flight_hours_28d == window_hours(cid, date(2026,9,14), 28, "flight")   # 150/150
```

Round to 2 dp **before** comparing to the 60 / 100 thresholds. The reference
implementation rounds the total, then tests `> 60 + 1e-6`.

### 4.5 Simulating a cover (the part that catches people out)

When testing whether candidate X can cover pairing P, for **each** day `d` of
the cover:

```
base7  = window_hours(X, d, 7, "duty")
       - sum(duty hours of X's own duties on pairing P inside [d-6, d])   # remove the pairing being replaced
add    = sum(duty length of every cover day whose date <= d)              # CUMULATIVE, not just this day
total7 = round(base7 + add, 2)
breach <=> total7 > 60
```

The `add` term is cumulative: on day 2 of a two-day cover, day 1's cover duty is
already inside the 7-day window and must be counted. This is exactly why
`C-2087` breaches on both days of P-2291 and why `C-3305` passes day 1 and fails
day 2. Verified numerically:

```
== Q24: C-3305 covers full P-2291 ==
  2026-09-15: base7=50.0 + cumulative cover 9.5  = 59.5   OK
  2026-09-16: base7=48.0 + cumulative cover 20.25 = 68.25  excess=8.25 (8h15m)
```

Breach message formatting used in the keys:
`excess = total7 - 60; f"RULE-DUTY-02: would exceed 60h/7d by {int(excess)}h{round((excess-int(excess))*60):02d}m on {d} (total {total7}h)"`.

### 4.6 Duty period, report and sign-off padding, block vs duty

| Concept | Definition in this dataset | Where it lives |
|---|---|---|
| Report time | first departure of the day **minus 60 min** | `rules.json.definitions.duty_period`, matches `report_utc` 42/42 |
| Release time | last arrival of the day **plus 30 min** | same, matches `release_utc` 42/42 |
| Duty period / FDP | `release_utc - report_utc` | the two fields above |
| Flight time (block) | `arr_utc - dep_utc` per leg, summed over the day | `flights.block_hours`, exact to 0 tolerance |
| Turnaround / ground time | implicit gap between legs, counted in duty but not in block | derived |

There is a fixed **60 min briefing buffer** before the first departure and a
fixed **30 min debriefing buffer** after the last arrival, so
`duty_hours = block_hours + ground_time + 1.5 h`. There is no per-leg briefing
allowance and no separate sign-off field anywhere in the data. Nothing in
`costs.json` encodes a buffer.

Example, P-2291 day 1: legs 07:00-08:45, 09:30-11:15, 12:15-15:00. Block =
1.75 + 1.75 + 2.75 = 6.25 h. Report 06:00, release 15:30, duty 9.50 h. Ground
time between legs = 0.75 + 1.00 = 1.75 h. 6.25 + 1.75 + 1.5 = 9.50. Checks out.

The `daily_history` rows do **not** follow that relation (their duty/flight
ratio is a synthetic 1.39 to 1.43, and 228 rows have duty > 0 with flight = 0).
History is opaque pre-computed accrual, not reconstructible from flights.

### 4.7 `last_rest_ended`

Derived, and verified against all 150 crew:

- If the crew has a rostered duty on or before 2026-09-14 (32 crew):
  `last_rest_ended = that duty's release_utc + 12 h`. Matched 32/32.
- Otherwise (118 crew): `last_rest_ended = (last daily_history date with
  duty_hours > 0) at 14:00Z + 12 h`, that is, that date at 02:00Z the next
  morning. Matched 118/118.

It is therefore the earliest legal next report under RULE-REST-04 given the
crew's most recent known duty. It is a convenience field, not an independent
input, and it is stale the moment you simulate a new assignment.

---

## 5. Cost model

`costs.json` shipped verbatim:

```json
{
 "currency": "INR",
 "reserve_callout_pilot": 18500,
 "reserve_callout_cabin": 9500,
 "dayoff_callout_pilot": 24000,
 "dayoff_callout_cabin": 12500,
 "deadhead_positioning": 6500,
 "delay_cost_per_duty_hour": 5400,
 "cancellation_per_flight": 250000,
 "hotel_overnight": 4200,
 "notes": "delay_cost_per_duty_hour is charged per hour the duty's first departure is delayed. Cancellation is per flight leg."
}
```

| Key | Value | Unit | Applies when |
|---|---|---|---|
| `reserve_callout_pilot` | 18,500 | INR per assignment (whole cover, not per day) | candidate is in `reserve_pool` and rank in {Captain, First Officer} |
| `reserve_callout_cabin` | 9,500 | INR per assignment | candidate is in `reserve_pool` and rank in {Senior Cabin Crew, Cabin Crew} |
| `dayoff_callout_pilot` | 24,000 | INR per assignment | candidate is NOT in `reserve_pool`, pilot rank |
| `dayoff_callout_cabin` | 12,500 | INR per assignment | candidate is NOT in `reserve_pool`, cabin rank |
| `deadhead_positioning` | 6,500 | INR per positioning | `crew.base != required departure station` |
| `delay_cost_per_duty_hour` | 5,400 | INR per hour of delay to the duty's **first departure** | any positive `delay_hours` |
| `cancellation_per_flight` | 250,000 | INR per **leg** | cancellation option |
| `hotel_overnight` | 4,200 | INR per overnight | **never used in any shipped answer key** |

### Pricing formula

```
pilot = rank in {"Captain", "First Officer"}

cost = (reserve_callout_pilot if pilot else reserve_callout_cabin)   if candidate is a reserve
       else (dayoff_callout_pilot if pilot else dayoff_callout_cabin)

if deadhead:
    cost += deadhead_positioning + round(delay_hours * delay_cost_per_duty_hour)

cancel_cost = cancellation_per_flight * (total legs across all days of the pairing)
```

Ranking: sort legal options by `(cost_inr, crew_id)` ascending, then **append
the cancellation option last regardless of its cost**, then assign
`rank = index + 1`. Cancellation is always the highest rank number even though
it is nominally "legal".

There is **no overtime rate** despite the problem-statement PDF calling
`costs.json` "Callout, overtime, deadhead and penalty rates". The
`hotel_overnight` rate exists but is never charged in any answer key, including
for the overnight-at-DEL two-day pairings. Do not add it to a cover price.
Callout is charged **once per assignment**, not per duty day: covering the
full two-day P-2291 with reserve C-3310 costs 18,500, not 37,000.

### Worked example: C-2210 covering P-2291 (the deadhead case)

```
Candidate: C-2210, Captain, base DEL, ratings ["A320"], in reserve_pool, window 03:00-15:00Z
Pairing:   P-2291 day 1, 2026-09-15, first leg DX412-2026-09-15 dep BLR 07:00Z, report 06:00Z

base_needed = BLR, crew.base = DEL          -> deadhead = True
2026-09-15 is an odd date                   -> positioning is DX402, arr BLR 08:45Z
new first departure = 08:45 + 75 min        = 10:00Z
delay_hours = 10:00 - 07:00                 = 3.0 h
new required report = 06:00 + 3.0 h         = 09:00Z
window test: 03:00 <= 09:00 <= 15:00        -> eligible

cost = reserve_callout_pilot     18500
     + deadhead_positioning       6500
     + round(3.0 * 5400)         16200
     ------------------------------------
     total                       41200 INR      matches the shipped answer key exactly
```

### Other cost values that appear in the keys, decomposed

| Where | Value | Decomposition |
|---|---|---|
| S1 / S2 / S6 clean reserve captain | 18,500 | `reserve_callout_pilot` |
| S1 / S2 / S6 day-off captain | 24,000 | `dayoff_callout_pilot` |
| S5 reserve cabin crew C-4809 | 9,500 | `reserve_callout_cabin` |
| S5 day-off cabin crew | 12,500 | `dayoff_callout_cabin` |
| S5 DEL reserve cabin deadhead (C-1622) | 53,800 | 9,500 + 6,500 + round(7.0 * 5,400 = 37,800) |
| S5 DEL day-off cabin deadhead (x4) | 56,800 | 12,500 + 6,500 + 37,800 |
| S6 DXA deadhead C-2210 | 60,100 | 18,500 + 6,500 + round(6.5 * 5,400 = 35,100) |
| S6 DXB deadhead C-2210 | 57,400 | 18,500 + 6,500 + round(6.0 * 5,400 = 32,400) |
| S1 cancel whole pairing (4 legs) | 1,000,000 | 4 x 250,000 |
| S2 cancel whole pairing (6 legs, 2 days) | 1,500,000 | 6 x 250,000 |
| S4 full reserve set for one leg | 75,000 | 2 x 18,500 (CPT+FO) + 4 x 9,500 (SCC + 3 CC) |
| S4 cancel DX404 | 250,000 | 1 x 250,000 |
| S6 optimal joint plan | 42,500 | 18,500 (C-3305 on DXA) + 24,000 (C-1017 on DXB) |

---

## 6. Scenarios and questions

### 6.1 The 6 scenarios

Common answer-key sub-object, the **option**:

```json
{"action": str, "crew_id": str|null, "legal": bool,
 "rules_checked": [7 rule ids] or [],
 "cost_inr": int, "delay_hours": float, "rank": int}
```

`rules_checked` is always the full 7-rule list for crew options and `[]` for the
cancellation option. `delay_hours` is 0.0 except for deadhead options.
Common **exclusion** sub-object: `{"crew_id": str, "reason": str}`, where
`reason` is a `"; "`-joined list of issue strings.

S4 uses a different option shape: `{"rank", "action", "legal", "cost_inr",
"reasoning"}` with no `crew_id` / `rules_checked` / `delay_hours`.

| ID | Difficulty | Title | Event type | `answer_key` keys |
|---|---|---|---|---|
| S1 | easy | ATR captain sick call | SICK_CREW | `uncovered_flights`, `options` (7), `excluded_candidates` (18), `expected_choice` |
| S2 | medium | Flagship: Captain C-1042 sick, 2-day pairing | SICK_CREW | `uncovered_flights_day1`, `uncovered_flights_day2`, `passengers_at_risk_day1`, `options` (6), `excluded_candidates` (19), `expected_choice` |
| S3 | medium | BLR station closure 08:00-14:00Z, 17 Sep | STATION_CLOSURE | `affected_flights` (13), `per_flight_assessment` (13), `note` |
| S4 | medium-hard | Tech delay cascades into an FDP breach | DELAY | `fdp_after_delay`, `fdp_limit`, `breach`, `breach_detail`, `options` (2), `expected_choice` |
| S5 | medium | Certification lapse discovered pre-flight | CERT_EXPIRY | `illegal_assignment`, `options` (43), `excluded_candidates` (21), `expected_choice` |
| S6 | hard | Two simultaneous captain sick calls | MULTI_SICK | `options_dxa` (13), `excluded_dxa` (12), `options_dxb` (13), `excluded_dxb` (12), `optimal_joint_plan`, `note` |

**S1** event: `{"type": "SICK_CREW", "crew_id": "C-3231", "pairing_id": "P-2224",
"reported_utc": "2026-09-16T01:30:00Z", "narrative": "..."}`.
Uncovered: DX451/452/453/454-2026-09-16.
Expected choice: `Assign Captain C-3315 (reserve callout)`, 18,500, rank 1.
Ranks 2-6 are day-off captains at 24,000 (C-1600, C-1671, C-2091, C-2221,
C-3721). Rank 7 is cancel all 4 flights at 1,000,000. C-3310 excluded on window
(06:00-18:00 does not cover required report 03:00Z); 14 captains excluded on
`RULE-QUAL-05: no ATR72 rating`; C-5392 excluded on rest plus double booking.

**S2** event: `{"type": "SICK_CREW", "crew_id": "C-1042", "pairing_id": "P-2291",
"reported_utc": "2026-09-15T05:00:00Z", ...}`. The narrative states the cover
must take the **full remaining pairing** because the aircraft overnights at DEL.
- `uncovered_flights_day1` = DX412/DX413/DX588-2026-09-15
- `uncovered_flights_day2` = DX589/DX590/DX591-2026-09-16
- `passengers_at_risk_day1` = 486 (= 3 legs x 162 seats, day 1 only)
- Options: rank 1 C-3310 reserve 18,500; ranks 2-4 C-1526 / C-3983 / C-5566
  day-off 24,000; rank 5 C-2210 reserve + deadhead 41,200, `delay_hours` 3.0;
  rank 6 cancel all 6 flights 1,500,000.
- Key exclusions: C-2087 (DUTY-02 on both days), C-3305 (window 00:00-05:30 does
  not cover required report 06:00Z), 8 captains on QUAL, 8 on REST-04.

**S3** event: `{"type": "STATION_CLOSURE", "station": "BLR", "window_utc":
{"start": "2026-09-17T08:00:00Z", "end": "2026-09-17T14:00:00Z"}, ...}`.

Affected-flight test (verified to reproduce the shipped 13-flight set exactly):

```
affected <=> (dep_station == "BLR" and w_start <= dep_utc <  w_end)
          or (arr_station == "BLR" and w_start <= arr_utc <  w_end)
```

Note the **half-open interval, end exclusive**. `DX588-2026-09-17` departs BLR
at 12:15 (in window, affected); `DX412-2026-09-17` departs BLR at 07:00 (before
the window, not affected) even though it is on the same tail as an affected leg.
A flight arriving BLR exactly at 14:00 would not be affected (no such flight
exists on 09-17).

Per-flight assessment arithmetic (all 13 rows reproduce):

```
anchor = dep_utc if (dep_station == "BLR" and dep in window) else arr_utc
min_delay_hours       = (w_end + 30 min) - anchor                # reopen 14:00 + 30 min turnaround = 14:30
crew_fdp_after_delay  = original duty length + min_delay_hours   # release slides, report does not
fdp_limit             = 13.0 - 0.5 * max(0, legs_in_that_duty_day - 2)
action = "delay (crew legal)" if crew_fdp_after_delay <= fdp_limit
         else "delay exceeds crew FDP - re-crew tail legs from reserves or cancel"
```

String-match warning: in the shipped JSON the separator between `FDP` and
`re-crew` in that `action` string is a **U+2014 em dash surrounded by single
spaces**, not the hyphen shown above. The same character appears in S3's `note`,
in S4's `breach_detail` and `reasoning`, and in several scenario titles and
narratives. Any exact-match assertion against the answer keys must reproduce
U+2014 there.

| flight_id | pairing | min_delay_h | fdp_after | limit | action |
|---|---|---|---|---|---|
| DX402-2026-09-17 | P-2204 | 5.75 | 17.00 | 12.0 | exceeds |
| DX422-2026-09-17 | P-2211 | 5.75 | 17.00 | 12.0 | exceeds |
| DX462-2026-09-17 | P-2232 | 5.75 | 11.00 | 13.0 | legal |
| DX453-2026-09-17 | P-2225 | 6.50 | 14.75 | 12.0 | exceeds |
| DX433-2026-09-17 | P-2218 | 6.00 | 15.75 | 12.0 | exceeds |
| DX403-2026-09-17 | P-2204 | 5.00 | 16.25 | 12.0 | exceeds |
| DX413-2026-09-17 | P-2293 | 3.25 | 12.75 | 12.5 | exceeds |
| DX423-2026-09-17 | P-2211 | 5.00 | 16.25 | 12.0 | exceeds |
| DX454-2026-09-17 | P-2225 | 3.75 | 12.00 | 12.0 | **legal** (equality) |
| DX434-2026-09-17 | P-2218 | 2.75 | 12.50 | 12.0 | exceeds |
| DX404-2026-09-17 | P-2204 | 2.25 | 13.50 | 12.0 | exceeds |
| DX424-2026-09-17 | P-2211 | 1.75 | 13.00 | 12.0 | exceeds |
| DX588-2026-09-17 | P-2293 | 2.25 | 11.75 | 12.5 | legal |

`note`: "Delays are measured to reopen +30min turnaround. Where the extended
duty exceeds RULE-FDP-01, tail legs need reserve re-crew or cancellation."

**S4** event: `{"type": "DELAY", "aircraft": "VT-DXA", "date": "2026-09-16",
"delay_hours": 1.5, ...}`. Pairing P-2203, duty 11.25 h, 4 sectors.
- `fdp_after_delay` = 11.25 + 1.5 = **12.75**, `fdp_limit` = **12.0**,
  `breach` = true.
- Option 1 (expected, 75,000): original crew flies DX401-DX403 delayed. New
  report 03:00, DX403 arrives 12:00 (10:30 + 1.5), release 12:30, duty 9.5 h vs
  a 3-sector limit of 12.5 h. Legal. A full reserve set (CPT, FO, SCC, 3 CC)
  takes DX404. Cost 2 x 18,500 + 4 x 9,500.
- Option 2 (250,000): cancel DX404, 162 passengers stranded.

**S5** event: `{"type": "CERT_EXPIRY", "crew_id": "C-5417", "pairing_id":
"P-2213", "reported_utc": "2026-09-18T10:00:00Z", ...}`.
- `illegal_assignment` = `{"crew_id": "C-5417", "date": "2026-09-19", "rule": "RULE-CERT-06"}`
- 43 options: rank 1 C-4809 reserve cabin 9,500; ranks 2-37 are 36 day-off cabin
  crew at 12,500; rank 38 C-1622 DEL reserve deadhead 53,800; ranks 39-42 four
  DEL day-off cabin deadheads at 56,800; rank 43 cancel 4 flights 1,000,000.
- 21 exclusions: 3 reserves on window (04:00-16:00 does not cover required
  report 02:00Z: C-5418, C-1329, C-2248), 6 on QUAL (no A320 rating), 12 on
  rest / double booking.

**S6** event: `{"type": "MULTI_SICK", "events": [{"crew_id": "C-3940",
"pairing_id": "P-2205", "reported_utc": "2026-09-18T00:30:00Z"}, {"crew_id":
"C-1938", "pairing_id": "P-2212", "reported_utc": "2026-09-18T00:30:00Z"}], ...}`.
- Both pairings are on 2026-09-18. P-2205 report 01:30Z, P-2212 report 02:00Z.
- Each side has 13 options: C-3305 at 18,500 (the only reserve captain whose
  00:00-05:30 window covers those early reports), 10 day-off captains at 24,000,
  C-2210 deadhead (60,100 for DXA, 57,400 for DXB), cancel at 1,000,000.
- Joint allocation: enumerate all (a, b) pairs from the two option lists,
  forbid `a.crew_id == b.crew_id` when non-null, minimise `a.cost + b.cost`.
  Result `total_cost_inr` **42,500** = C-3305 on DXA (18,500) plus C-1017 on DXB
  (24,000).
- `note` explicitly says equal-cost mirror assignments (swapping which pairing
  each candidate covers) are equally correct. Any 18,500 + 24,000 split of
  C-3305 plus one of the 10 day-off captains is an acceptable answer.

### 6.2 Candidate enumeration, the exact algorithm behind every cover answer key

Reconstructed from the answer keys and confirmed against
`<root>/generate.py:479-531`. This is the single most reusable thing in the
dataset:

```
for each crew c in crew.json:
    skip if c.crew_id == the sick crew
    skip if c.rank != the required role          # exact rank match, SCC != CC
    skip if c.status != "active"                 # leave/training silently dropped, not listed
    is_reserve = c.crew_id in reserve_pool
    deadhead   = c.base != required departure station of day 1
    delay_h    = 0.0
    if deadhead:
        if c.base == "DEL" and required base == "BLR":
            delay_h = deadhead delay per section 3 RULE-BASE-07
        else:
            EXCLUDE "RULE-BASE-07: no same-day positioning flight from base"
    if is_reserve:
        required_report = day1.report_utc + delay_h
        if not (window_start <= required_report <= window_end):
            EXCLUDE "reserve on-call window HH:MM-HH:MMZ does not cover required report HH:MMZ"
    run check_cover(c, pairing days, exclude_pairing, delay_h):
        1. RULE-QUAL-05  -> immediate return, short-circuits all other reasons
        2. per cover day: RULE-CERT-06
        3. per cover day: RULE-FDP-01 on (release + delay) - (report + delay)
        4. merge candidate's own week duties (minus exclude_pairing) with the
           cover days, sort by report, check RULE-REST-04 pairwise
        5. same sorted list, check overlaps -> "double-booked: A overlaps B on date"
        6. per cover day: RULE-DUTY-02 with the cumulative rule of section 4.5
        (RULE-FLT-03 is listed in rules_checked but not evaluated)
    if any issue: EXCLUDE with "; ".join(issues)
    else: price it and add to options

sort options by (cost_inr, crew_id)
append the cancellation option (cost = 250000 * total legs) LAST
rank = index + 1
```

Ordering of the FDP check matters for message fidelity: FDP is evaluated on the
delayed duty, so a deadhead candidate's FDP is unchanged in length (report and
release both slide by `delay_h`).

### 6.3 All 38 questions

Counts: **Tier 1 = 16 (Q01-Q16), Tier 2 = 14 (Q17-Q30), Tier 3 = 8 (Q31-Q38).**

#### Tier 1, lookup and retrieval (16)

| Q | Prompt (abridged) | Expected answer | rules_ref |
|---|---|---|---|
| Q01 | Who is on reserve at BLR on 2026-09-15, and their on-call windows? | list of 12 `{crew_id, rank, window}`, in reserve_pool file order: C-3305, C-3310, C-3311, C-3312, C-3315, C-3316, C-2111, C-3677, C-5418, C-1329, C-2248, C-4809 | [] |
| Q02 | C-1042 duty hours in 7 days ending 2026-09-14 and headroom under RULE-DUTY-02 | `{"duty_hours_7d": 20.93, "headroom_hours": 39.07}` | RULE-DUTY-02 |
| Q03 | Which flights depart DEL on 2026-09-15? | `["DX402"]` (flight **numbers**, not ids) | [] |
| Q04 | Certifications expiring within 30 days of 2026-09-15 | 6 rows: C-2087 licence 2026-09-18, C-2091 medical_class1 2026-09-23, C-5417 recurrent_training 2026-09-17, C-3116 dangerous_goods 2026-09-28, C-5020 recurrent_training 2026-10-03, C-2993 medical_class1 2026-10-08 | RULE-CERT-06 |
| Q05 | Aircraft and seats for DX412 on 2026-09-15 | `{"aircraft": "VT-DXC", "aircraft_type": "A320", "seats": 162}` | [] |
| Q06 | C-3310's window and reachability | `{"window": {"start": "06:00", "end": "18:00"}, "reachability_minutes": 45}` | [] |
| Q07 | C-2210's base and rating | `{"base": "DEL", "ratings": ["A320"]}` | [] |
| Q08 | Crew on pairing P-2291 and roles | 6 `{crew_id, role}`: C-1042 Captain, C-1694 FO, C-3005 SCC, C-4395/C-4273/C-1873 CC | [] |
| Q09 | Flights BLR to BOM on 2026-09-17 | `["DX431", "DX412"]` (flight numbers; note the order is DX431 first) | [] |
| Q10 | Flights operating on 2026-09-16 | `21` | [] |
| Q11 | Captains based at DEL | `["C-2210"]` | [] |
| Q12 | Longest block time and which flights | `{"block_hours": 2.75, "flights": ["DX401", "DX402", "DX588", "DX589"]}` | [] |
| Q13 | C-2087's rank and 28-day flight hours | `{"rank": "Captain", "flight_hours_28d": 23.5}` | [] |
| Q14 | Stations served nonstop from BLR | `["BOM", "CCU", "COK", "DEL", "GOI", "HYD", "MAA"]` | [] |
| Q15 | SCC on VT-DXB's pairing on 2026-09-16 | `"C-3171"` | [] |
| Q16 | C-1042's disruption-risk score and drivers | `{"score": 0.78, "drivers": ["short-rest pattern over last 14 days", "two fatigue reports this month"]}` | [] |

#### Tier 2, consequence and simulation (14)

| Q | Prompt (abridged) | Expected answer | rules_ref |
|---|---|---|---|
| Q17 | C-1042 sick 05:00Z 15 Sep for P-2291, which flights uncrewed? | `{"day1": [DX412/DX413/DX588-2026-09-15], "day2_also_at_risk": [DX589/DX590/DX591-2026-09-16], "passengers_day1": 486}` | RULE-QUAL-05 |
| Q18 | Does C-2087 covering P-2291 breach? | `{"legal": false, "issues": ["RULE-DUTY-02: would exceed 60h/7d by 1h20m on 2026-09-15 (total 61.33h)", "RULE-DUTY-02: would exceed 60h/7d by 1h05m on 2026-09-16 (total 61.08h)"]}` | RULE-DUTY-02 |
| Q19 | BLR closed 08:00-14:00Z 17 Sep, which flights affected? | the 13 flight_ids of S3, in S3's order | [] |
| Q20 | VT-DXA delayed 90 min before DX401 16 Sep, breach? | `{"breach": true, "fdp_after_delay": 12.75, "fdp_limit": 12.0}` | RULE-FDP-01 |
| Q21 | Can C-2210 cover P-2291 positioned to BLR on 15 Sep? | `{"legal": true, "consequence": "Deadhead positioning on DX402 (arr 08:45Z) delays the first departure by ~3h; RULE-BASE-07 deadhead cost applies."}` | RULE-BASE-07, RULE-REST-04 |
| Q22 | Can C-5417 legally operate their 19 Sep VT-DXB duty? | `{"legal": false, "rule": "RULE-CERT-06", "detail": "recurrent_training expired 2026-09-17"}` | RULE-CERT-06 |
| Q23 | Released 15:30Z 16 Sep, earliest next report? | `"2026-09-17T03:30:00Z"` | RULE-REST-04 |
| Q24 | Can reserve C-3305 cover the FULL P-2291? | `{"legal": false, "issues": ["RULE-DUTY-02: would exceed 60h/7d by 8h15m on 2026-09-16 (total 68.25h)"]}` | RULE-DUTY-02 |
| Q25 | DX404 16 Sep cancelled, passengers and cost? | `{"passengers": 162, "cost_inr": 250000}` | [] |
| Q26 | Crew with >= 45 duty hours in 7 days ending 2026-09-15 | `[{"crew_id": "C-2087", "duty_hours_7d_incl_15sep_plan": 51.83}, {"crew_id": "C-3305", "duty_hours_7d_incl_15sep_plan": 50.0}]` | RULE-DUTY-02 |
| Q27 | VT-DXE captain sick 16 Sep (called 01:30Z), which reserve captains? | `{"eligible": ["C-3315"], "excluded_examples": [{"crew_id": "C-3305", "reason": "RULE-QUAL-05: no ATR72 rating"}, {"crew_id": "C-3310", "reason": "reserve on-call window 06:00-18:00Z does not cover required report 03:00Z"}]}` | RULE-QUAL-05, RULE-BASE-07 |
| Q28 | Is C-5837 legal to cover P-2291? | `{"legal": false, "issues": ["RULE-REST-04: only 10.75h rest before P-2204 on 2026-09-17 (downstream conflict)"]}` | RULE-REST-04 |
| Q29 | HYD closed 05:00-09:00Z 19 Sep, which flights? | `["DX461-2026-09-19", "DX462-2026-09-19"]` | [] |
| Q30 | Which single leg has the most seats at risk? | `{"flights": "any A320 leg (162 seats)", "vs": "ATR72 legs (72 seats)"}` | [] |

#### Tier 3, recommendation and action (8)

| Q | Prompt (abridged) | Expected answer | rules_ref |
|---|---|---|---|
| Q31 | C-1042 out for P-2291, ranked resolution options | the full 6-option list of S2 (C-3310 18,500 rank 1 through cancel 1,500,000 rank 6) | RULE-DUTY-02, RULE-BASE-07 |
| Q32 | Both A320 captains sick 00:30Z 18 Sep, optimal joint plan | `{"total_cost_inr": 42500, "assign_dxa": C-3305 reserve 18500, "assign_dxb": C-1017 day-off 24000}` | RULE-BASE-07, RULE-DUTY-02 |
| Q33 | What to do about the VT-DXA 16 Sep FDP breach | the 2-option list of S4 (re-crew DX404 with a full reserve set at 75,000; cancel DX404 at 250,000) | RULE-FDP-01 |
| Q34 | Resolve C-5417's 19 Sep assignment | first 3 options of S5: C-4809 reserve 9,500; C-1021 day-off 12,500; C-1385 day-off 12,500 | RULE-CERT-06 |
| Q35 | BLR closure recovery plan across pairings | the 13-row `per_flight_assessment` of S3 | RULE-FDP-01 |
| Q36 | Draft the callout notification to C-3310 for P-2291 | `{"must_include": ["crew_id and pairing_id", "report time/place: 06:00Z 15 Sep, BLR crew room", "flights day 1: DX412/DX413/DX588; overnight DEL (hotel arranged)", "flights day 2: DX589/DX590/DX591, report 04:00Z at DEL", "acknowledgement request with deadline", "contact for questions"]}` graded on completeness, not wording | [] |
| Q37 | Cheapest legal cover for VT-DXF FO on 20 Sep, sick at 03:30Z | `{"action": "Assign First Officer C-3316 (reserve callout)", "crew_id": "C-3316", "legal": true, "cost_inr": 18500, "delay_hours": 0.0, "rank": 1}` | RULE-QUAL-05 |
| Q38 | Three data points per aircraft line for a morning briefing | `{"suggested": ["crew legality headroom (7d duty) for today's rostered crew", "reserve availability by window and rating for the day", "risk_signals for today's rostered crew (provided input)"], "note": "Open-ended; judged on operational reasoning, not exact match."}` | [] |

### 6.4 Question to required computation

| Q | Tier | Required tool / computation |
|---|---|---|
| Q01 | 1 | `reserves_on(date, base)` join `crew` for rank |
| Q02 | 1 | `duty_window_hours(crew, 2026-09-14, 7)` plus `60 - value` |
| Q03 | 1 | `flights_filter(date, dep_station)` project `flight_no` distinct |
| Q04 | 1 | `certs_expiring_between(from, from+30d)` on `valid_to` |
| Q05 | 1 | `flight_lookup(flight_no, date)` |
| Q06 | 1 | `reserve_lookup(crew)` join `crew_lookup(crew)` |
| Q07 | 1 | `crew_lookup(crew)` |
| Q08 | 1 | `pairing_lookup(pairing_id)` project crew |
| Q09 | 1 | `flights_filter(date, dep_station, arr_station)` |
| Q10 | 1 | `flights_filter(date)` count |
| Q11 | 1 | `crew_filter(rank, base)` |
| Q12 | 1 | `max(block_hours)` plus argmax over distinct `flight_no` |
| Q13 | 1 | `crew_lookup` plus `duty_clocks.flight_hours_28d` |
| Q14 | 1 | distinct `arr_station where dep_station == BLR` |
| Q15 | 1 | `pairing_for(aircraft, date)` then role filter |
| Q16 | 1 | `risk_lookup(crew)` |
| Q17 | 2 | `pairing_lookup` + uncovered-leg expansion over **all days** + `sum(seats)` for day 1 |
| Q18 | 2 | `simulate_cover(candidate, pairing)` -> RULE-DUTY-02 per day with cumulative add |
| Q19 | 2 | `station_closure_affected(station, window)` with half-open interval |
| Q20 | 2 | `fdp_after_delay(pairing_day, delay)` vs `fdp_limit(sectors)` |
| Q21 | 2 | `deadhead_plan(crew, pairing)` -> delay hours, then full `simulate_cover` |
| Q22 | 2 | `certs_valid_on(crew, date)` |
| Q23 | 2 | `release + 12h` |
| Q24 | 2 | `simulate_cover` over both days, cumulative RULE-DUTY-02 |
| Q25 | 2 | `flight_lookup.seats` plus `costs.cancellation_per_flight` |
| Q26 | 2 | `duty_window_hours(crew, 2026-09-15, 7)` for all 150, threshold filter |
| Q27 | 2 | `reserve_eligible(role, required_report)` plus RULE-QUAL-05 |
| Q28 | 2 | `simulate_cover` -> RULE-REST-04 downstream conflict |
| Q29 | 2 | `station_closure_affected("HYD", window)` |
| Q30 | 2 | seats by `aircraft_type` |
| Q31 | 3 | full `cover_options(pairing, role)` with ranking and costing |
| Q32 | 3 | two `cover_options` runs plus joint minimisation with a distinctness constraint |
| Q33 | 3 | delay simulation, partial-duty FDP recompute, reserve-set costing |
| Q34 | 3 | `cover_options` for a Cabin Crew role |
| Q35 | 3 | S3 per-flight delay and FDP assessment across pairings |
| Q36 | 3 | `pairing_lookup` for times and legs, then template generation (no arithmetic beyond lookup) |
| Q37 | 3 | `cover_options` for the VT-DXF FO on 2026-09-20, cheapest legal |
| Q38 | 3 | open-ended, no computation required |

Coverage summary: Tier 1 needs only typed lookups and one window sum
(Q02, Q13). Tier 2 needs the window sums, the FDP calculation, the rest
calculation, the closure filter and one full cover simulation. Tier 3 needs the
complete candidate enumerator plus costing, ranking and joint allocation.

---

## 7. Verified anchor facts

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 1 | `C-1042` is A. Nair, Captain, BLR, A320 | **CONFIRMED with a correction to seniority** | `{"crew_id":"C-1042","name":"A. Nair","rank":"Captain","base":"BLR","ratings":["A320"],"seniority":22,"reachability_minutes":90,"status":"active"}`. The problem-statement PDF sample shows `seniority: 14` and no `status` field: **the PDF sample is stale**, the shipped value is 22. |
| 2 | `C-1042` operates 2-day pairing `P-2291`, day 1 DX412/DX413/DX588 on 15 Sep, day 2 DX589/DX590/DX591 on 16 Sep | **CONFIRMED** | P-2291, tail VT-DXC. Day 1 2026-09-15 report 06:00Z release 15:30Z (9.50 h, 3 sectors, limit 12.5). Day 2 2026-09-16 report 04:00Z release 14:45Z (10.75 h, 3 sectors, limit 12.5). Day 1 ends at DEL, day 2 starts at DEL. |
| 3 | Covering `P-2291` with `C-2087` breaches RULE-DUTY-02 by 1h20m (61.33 h vs 60 h) | **CONFIRMED, with a nuance** | C-2087 has zero rostered duties this week; the 7-day window ending 2026-09-15 sums to 51.83 h from `daily_history` alone (09-09 11.0, 09-10 10.5, 09-11 8.0, 09-12 12.0, 09-13 6.0, 09-14 4.33). 51.83 + 9.50 = **61.33**, excess **1.33 h**, which the key formats as `1h20m` (1.33 h = 1 h 19.8 min, rounded to the nearest minute). The nuance: the breach also recurs on **day 2**, 40.83 + 9.50 + 10.75 = **61.08 h**, formatted `1h05m`. Both strings are in the shipped answer for Q18 and S2. |
| 4 | Reserve `C-3310` covers `P-2291` cleanly at INR 18,500 | **CONFIRMED** | C-3310, Captain, BLR, A320, reserve window 06:00-18:00Z. Required report 06:00Z is exactly on the window boundary and the test is inclusive. `duty_hours_7d` 0.0, `flight_hours_28d` 9.34, no rostered duties. Cost = `reserve_callout_pilot` = 18,500, `delay_hours` 0.0, rank 1, and it is `expected_choice` for both S2 and Q31. |
| 5 | `C-2210` (DEL) is legal via deadhead at INR 41,200 with a ~3h delay to DX412 | **CONFIRMED** | See the worked example in section 5. 18,500 + 6,500 + round(3.0 x 5,400) = 41,200; `delay_hours` 3.0; positioning DX402 arriving BLR 08:45Z on 2026-09-15; new report 09:00Z, inside C-2210's 03:00-15:00 window; rank 5 in S2. |
| 6 | `C-3305` is legal for day 1 alone and breaches on day 2 | **CONFIRMED** | Recomputed: 2026-09-15 base7 = 50.0 + cover 9.50 = 59.50, legal. 2026-09-16 base7 = 48.0 + cumulative cover 20.25 = **68.25**, excess 8.25 h, formatted `8h15m`. This is the Q24 answer verbatim. Separately, C-3305 is excluded from S2 before the duty check even runs, because its 00:00-05:30Z window does not cover the 06:00Z report. |
| 7 | `C-2091` is ATR-only, the RULE-QUAL-05 exclusion case | **CONFIRMED** | `{"crew_id":"C-2091","name":"H. Naidu","rank":"Captain","base":"BLR","ratings":["ATR72"],"seniority":4,"reachability_minutes":75,"status":"active"}`. Excluded from S2 with `"RULE-QUAL-05: no A320 rating"`; eligible in S1 as a 24,000 day-off ATR captain at rank 4. |
| 8 | `C-5417` is the single flagged roster exception, `recurrent_training` expired 2026-09-17 while rostered 2026-09-19 | **CONFIRMED** | `rosters.flagged_exceptions` has exactly 1 entry, for C-5417 on 2026-09-19, rule RULE-CERT-06. C-5417 is Cabin Crew, BLR, A320, `recurrent_training` `valid_to` 2026-09-17. C-5417 is rostered on 2026-09-16 (P-2210) and 2026-09-19 (P-2213). The 09-16 duty is legal (17 >= 16); the 09-19 duty is not. |
| 9 | Snapshot 2026-09-14T18:00:00Z, week 2026-09-14 to 2026-09-20, hub BLR, currency INR | **CONFIRMED** | `as_of_utc` is the constant `2026-09-14T18:00:00Z` in both `duty_clocks.json` (150/150) and `risk_signals.json` (150/150). `flights.date` spans exactly 09-14 to 09-20 with 21 legs on each of the 7 days. BLR appears in 8 of 8 station values and is the endpoint of every rotation. `costs.currency == "INR"`. |
| 10 | 147 flights, 150 crew, 39 pairings, 16 reserves, 7 rules | **CONFIRMED** | `validate.py` prints: `flights=147 crew=150 pairings=39 reserves=16 certs=600 scenarios=6 questions=38 tiers={1: 16, 2: 14, 3: 8}`. `rules.json.rules` has 7 entries. Also: 42 pairing-days, 600 certifications, 4200 `daily_history` cells. |

### Validator output

`python3 validate.py` run from `<root>`, verbatim:

```
flights=147 crew=150 pairings=39 reserves=16 certs=600 scenarios=6 questions=38 tiers={1: 16, 2: 14, 3: 8}
PASS - dataset is internally consistent (schedule continuity, complements, FDP/duty/flight-hour windows, rest, ratings, certifications, clocks, references).
```

(The real stdout uses a U+2014 em dash after `PASS`; substituted with a hyphen
here to keep this document em-dash free. Same substitution applies to the two
literal dataset strings quoted below.)

What `validate.py` checks (these are the dataset's own invariants, worth
mirroring in a test suite):

1. **Flights**: per-aircraft schedule continuity (arrival station of leg N equals
   departure station of leg N+1; no departure before the previous arrival) and
   `block_hours == arr - dep` within 0.02 h.
2. **Rosters**: every crew_id and flight_id resolves; `role == rank`; the crew
   complement exactly matches `{A320: 1 CPT, 1 FO, 1 SCC, 3 CC}` /
   `{ATR72: 1 CPT, 1 FO, 1 SCC, 1 CC}`; report at least 60 min before the first
   departure and release not before the last arrival; leg continuity inside a
   day; FDP under `13 - 0.5 * (sectors - 2)`; overnight station continuity
   across the two days of a multi-day pairing; every flight is covered.
3. **Per crew**: no overlapping duties; at least 12 h rest between consecutive
   duties; the aircraft type of every assigned pairing is in `ratings`; no
   certification with `valid_to < duty_date` unless the (crew, date) pair is in
   `flagged_exceptions`, and conversely a flagged pair must actually have an
   invalid cert.
4. **Duty windows**: `daily_history` has exactly 28 entries per crew; no crew
   exceeds 60 h in any 7-day window ending on a rostered date; none exceeds
   100 h flight in any 28-day window; and `duty_hours_7d` recomputes to within
   0.05 from history plus roster over 2026-09-08 to 2026-09-14. **This last
   check is the codified proof of the section 4 formula, including the
   09-14 overlap.**
5. **Reserves and status**: every reserve exists and is `active`; no
   `leave`/`training` crew is rostered.
6. **References**: recursive walk of `scenarios.json` and `questions.json`
   checking every `crew_id` and `flight_id` resolves.

The validator does **not** check: `valid_from` sanity, `flight_hours_28d`
against the summary field (only `duty_hours_7d`), `last_rest_ended`,
`risk_signals` values, or anything in `costs.json`.

---

## 8. Traps and edge cases

### Time and date handling

1. **Trailing `Z` with naive parsing.** Every timestamp ends in `Z` but the
   intended parse is `datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")`, producing a
   naive datetime treated as UTC. `datetime.fromisoformat` rejects the `Z` on
   Python < 3.11. Do not attach a tzinfo halfway through: mixing aware and naive
   values throws.
2. **No leg crosses midnight UTC.** `dep_utc[:10] == arr_utc[:10] == date` for
   all 147 legs, and every duty period sits inside one UTC date. Do not build
   midnight-rollover logic; there is none to exercise, and inventing it risks
   getting the calendar-day windows wrong.
3. **Calendar-day windows, not rolling 168 hours.** RULE-DUTY-02 and RULE-FLT-03
   operate on **UTC dates**, inclusive of the duty date:
   `[end - 6 days, end]` and `[end - 27 days, end]`. A 168-hour rolling clock
   gives different, wrong answers.
4. **The 2026-09-14 double count.** `daily_history` ends on 2026-09-14 and the
   roster starts on 2026-09-14, so 11 crew are counted twice on that date. The
   shipped summary fields include the double count and the validator asserts it.
   Treat it as the convention, never as a bug to fix. Section 4.3.

### Rule evaluation

5. **Strict versus inclusive comparisons.** FDP breach is `fdp > limit`
   (12.0 h against a 12.0 h limit is legal, see `DX454-2026-09-17` in S3). Rest
   breach is `rest < 12` (exactly 12.0 h is legal). Cert validity is
   `valid_to >= duty_date` (a cert expiring on the duty date is valid that day).
   Reserve windows are inclusive on both ends (`C-3310`'s 06:00 window start
   exactly covers a 06:00Z report and it is the S2 expected choice). Getting any
   of these backwards flips a headline answer.
6. **A candidate must be legal on every day of a multi-day cover.** `C-3305`
   passes day 1 of P-2291 and fails day 2. Never accept a candidate on the
   strength of day 1.
7. **The 7-day duty add is cumulative across cover days.** On day 2, day 1's
   cover duty is already inside the window. `C-2087` breaches on both days
   (61.33 then 61.08) precisely because of this. Section 4.5.
8. **The pairing being replaced must be subtracted.** If the candidate is
   themselves rostered on the pairing being covered (a role swap), their own
   duties on that pairing are removed from the base window before the cover is
   added.
9. **RULE-QUAL-05 short-circuits.** In the shipped `excluded_candidates`
   strings, a rating failure suppresses every other reason. If you emit all
   reasons, your text will not match the keys even though your verdict does.
10. **RULE-FLT-03 is inert.** It appears in every `rules_checked` list but the
    maximum 28-day block total across the whole dataset is 79.28 h against a
    100 h limit. Implement it, but no test will exercise a breach.
11. **`valid_from` is unusable.** Generated as `valid_to - 730 days` and never
    fixed up after engineered expiries, so 1 record has `valid_from > valid_to`
    (`C-2087` licence) and many have a future `valid_from` for a currently
    flying crew member. Check `valid_to` only.
12. **Rank equals role, exactly.** `Senior Cabin Crew` is not substitutable for
    `Cabin Crew`, and vice versa. A candidate must have `rank == required role`.
13. **Non-active crew are silently dropped.** `leave` and `training` crew are
    filtered before any rule runs and never appear in `excluded_candidates`.
    Do not report them as rule failures.

### Reserves and positioning

14. **The reserve window is tested against the required REPORT time, not the
    callout time.** Every scenario carries a `reported_utc` and it is narrative
    only. Using it produces different eligibility sets (for example S1's
    `reported_utc` is 01:30Z but the required report is 03:00Z, and the
    exclusion string for `C-3310` quotes 03:00Z).
15. **After a deadhead, the window is tested against the DELAYED report.**
    `required_report = day1.report_utc + delay_hours`. `C-2210` covering P-2291
    is tested at 09:00Z, not 06:00Z. This changes who is eligible.
16. **Only day 1's report is window-tested.** Once activated, a reserve operates
    as line crew; day 2 of a multi-day cover has no window test.
17. **Windows never wrap midnight** in this data (00:00-05:30, 00:00-12:00,
    03:00-15:00, 04:00-16:00, 06:00-18:00), so a same-date interval test is
    safe. Do not over-engineer wraparound.
18. **All 16 reserves are on call all 7 days.** The `dates` array is always the
    full week, so it never discriminates. The only discriminator is the window.
19. **Deadhead exists only DEL to BLR.** Positioning is DX402 (arrives 08:45Z,
    used on odd dates) or DX589 (arrives 07:45Z, used on even dates 14/16/18/20).
    Any other cross-base request is excluded with
    `"RULE-BASE-07: no same-day positioning flight from base"`. The date parity
    is what selects the flight, not availability: DX402 operates all 7 days but
    the reference implementation only reaches for it on odd dates.
20. **The 75-minute positioning constant.** `new first departure = positioning
    arrival + 75 min` (15 min transit plus the standard 60 min report lead), and
    `new report = arrival + 15 min`. Getting this wrong shifts the delay hours
    and therefore the cost.
21. **`reachability_minutes` is never used in any legality or cost
    computation.** It appears only in Q06 (a lookup) and as narrative colour in
    the problem-statement's example reasoning. Surface it, do not gate on it.

### Cascade and impact

22. **A sick crew member breaks every day of their pairing, not just today.**
    S2 and Q17 both list day 2 explicitly. For P-2291, day 1 loses its captain
    and day 2 is at risk because the aircraft overnights at DEL and the cover
    must take the whole remaining pairing.
23. **`passengers_at_risk` in S2 is day 1 only** (486 = 3 legs x 162 seats),
    even though six legs are at risk. Do not sum both days for that field.
24. **Station-closure windows are half-open, `[start, end)`.** Verified against
    S3's 13-flight answer. A departure exactly at the reopen time is not
    affected.
25. **Closure delay anchors on the BLR event, not the flight's own departure.**
    `anchor = dep_utc if the BLR departure is in the window else arr_utc`, and
    the target is `window_end + 30 min` (reopen plus one turnaround).
26. **Delay extends release, never report.** In S3,
    `crew_fdp_after_delay = original duty length + min_delay_hours`. In S4 (a
    pre-departure tech delay) both report and release slide, so the duty length
    also grows by the delay. These are two different models and both appear in
    the keys: S3 delays a mid-duty leg, S4 delays the whole duty.
27. **Partial-duty re-crew changes the sector count and therefore the FDP
    limit.** In S4, dropping DX404 takes the duty from 4 sectors (limit 12.0) to
    3 sectors (limit 12.5) and the FDP from 12.75 h to 9.5 h. Recompute the
    limit, do not reuse the original.
28. **Cancellation is priced per leg, not per pairing.** 6 legs of P-2291 is
    1,500,000, not 250,000.
29. **Cancellation is always ranked last** even when it is not the most
    expensive option in some hypothetical. The reference implementation appends
    it after sorting.
30. **Joint allocation forbids the same person twice, and ties are acceptable.**
    S6's note says equal-cost mirror assignments are equally correct, so an
    evaluator must accept any 18,500 + 24,000 split rather than a single
    hard-coded pairing.
31. **Callout is charged once per assignment, not per day.** Covering the
    two-day P-2291 costs 18,500 total. `hotel_overnight` (4,200) is never
    charged, even for a DEL overnight.

### Documentation drift (problem statement PDF versus the shipped dataset)

The PDF at `problem-statement/problem_explanation_k66g3nx88t.pdf` disagrees with
the data in several places. The **data wins** every time.

| PDF says | Shipped data |
|---|---|
| "FO C-2087" in the Tier-2 example | `C-2087` is a **Captain** (the dataset README flags this as a doc bug to fix) |
| `crew.json` sample: C-1042 `seniority: 14`, no `status` field | `seniority: 22`, `status: "active"` present |
| `duty_clocks.json` sample: C-1042 `duty_hours_7d: 48.5`, `flight_hours_28d: 82.0`, `last_rest_ended: 2026-09-14T22:00:00Z`, no `daily_history` | `20.93`, `64.27`, `2026-09-13T02:00:00Z`, plus `as_of_utc` and a 28-entry `daily_history` |
| `reserve_pool.json` has "on-call windows and **standby status**" | there is no standby-status field anywhere |
| `costs.json` has "Callout, **overtime**, deadhead and penalty rates" | there is no overtime rate |
| Tier-3 option shape includes `coverage` and `reasoning` | shipped options carry `action`, `crew_id`, `legal`, `rules_checked`, `cost_inr`, `delay_hours`, `rank`; only S4's two options carry `reasoning`, and nothing carries `coverage` |
| "~140 flights", "~40 questions", "~8 stations" | exactly 147, 38, 8 |
| RULE-BASE-07 phrased "Reserve callout from base only, unless deadhead cost is applied" | "Reserve callout from own base only; covering from another base requires deadhead positioning (cost applies)" |

### Two data quirks that are not traps but will look like bugs

32. **Crew names are not unique.** Seven names are shared by two crew each
    (`A. Nair`, `R. Iyer`, `H. Naidu`, `S. Kapoor`, `K. Rao`, `P. Sharma`,
    `N. Verma`). Never key on, or resolve a user's question by, name alone.
33. **`daily_history` is not reconstructible from flights.** Its duty/flight
    ratio is a synthetic 1.39 to 1.43, and 228 cells carry duty with zero flight
    hours. It is opaque prior accrual. Only the current week's duty is derivable
    from `report_utc`/`release_utc` and `block_hours`.

---

## Appendix: scratchpad scripts used

All under
`/tmp/claude-1000/-home-jk-Documents-Bessemer-Dcortex-agentic-crew-ops-dvisor/6d7889c6-b79d-4b3b-87eb-b8cbfe6e5ca7/scratchpad/`:

| Script | What it proves |
|---|---|
| `schema.py` | field presence, types and value domains for every array-shaped file |
| `clocks.py` | the 150/150 clock-formula proof and the 09-14 overlap |
| `stats.py` | counts, distributions, roster invariants, report/release padding |
| `anchors.py` | the anchor-fact checks including the C-2087 61.33 h derivation |
| `verify2.py` | Q24 / Q26 recomputation, the deadhead formula, S3 window semantics, `last_rest_ended` derivation |

Nothing was written to `data/` or anywhere in the repository.
