"""Validate KZ IIN (Individual Identification Number) and extract metadata."""

_WEIGHTS_1 = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
_WEIGHTS_2 = [3, 4, 5, 6, 7, 8, 9, 10, 11, 1, 2]

_MONTHS = {
    "01": "января", "02": "февраля", "03": "марта", "04": "апреля",
    "05": "мая", "06": "июня", "07": "июля", "08": "августа",
    "09": "сентября", "10": "октября", "11": "ноября", "12": "декабря",
}


def validate_kz_iin(iin: str) -> dict:
    """Validate KZ IIN and return metadata.

    IIN structure: YYMMDDGXXXXC
      YY   — year of birth (last 2 digits)
      MM   — month of birth
      DD   — day of birth
      G    — gender/century: 1-2=M/F born 1800-1899, 3-4=M/F born 1900-1999,
                             5-6=M/F born 2000-2099
      XXXX — sequence number
      C    — checksum digit

    Returns:
        {
            "valid": bool,
            "iin": str,
            "errors": list[str],
            "dob": str | None,       # "01.01.1990"
            "gender": "M" | "F" | None,
            "century": str | None,   # "1900-1999"
        }
    """
    errors: list[str] = []
    iin = iin.strip()

    if len(iin) != 12:
        return {"valid": False, "iin": iin, "errors": [f"Длина должна быть 12, получено {len(iin)}"],
                "dob": None, "gender": None, "century": None}

    if not iin.isdigit():
        return {"valid": False, "iin": iin, "errors": ["ИИН должен содержать только цифры"],
                "dob": None, "gender": None, "century": None}

    digits = [int(d) for d in iin]

    # Checksum
    s = sum(w * d for w, d in zip(_WEIGHTS_1, digits[:11])) % 11
    if s == 10:
        s = sum(w * d for w, d in zip(_WEIGHTS_2, digits[:11])) % 11
    if s != digits[11]:
        errors.append(f"Неверная контрольная сумма (ожидалось {digits[11]}, получено {s})")

    # Parse fields
    yy = iin[0:2]
    mm = iin[2:4]
    dd = iin[4:6]
    g = int(iin[6])

    century_map = {
        1: ("1800-1899", "M"), 2: ("1800-1899", "F"),
        3: ("1900-1999", "M"), 4: ("1900-1999", "F"),
        5: ("2000-2099", "M"), 6: ("2000-2099", "F"),
    }
    if g not in century_map:
        errors.append(f"Недопустимый код века/пола: {g}")
        century_str, gender = None, None
    else:
        century_str, gender = century_map[g]

    # Reconstruct full year
    if century_str:
        century_prefix = century_str[:2]
        full_year = century_prefix + yy
    else:
        full_year = "19" + yy

    # Validate date
    dob = None
    try:
        if int(mm) < 1 or int(mm) > 12:
            raise ValueError("invalid month")
        if int(dd) < 1 or int(dd) > 31:
            raise ValueError("invalid day")
        dob = f"{dd}.{mm}.{full_year}"
    except ValueError as e:
        errors.append(f"Некорректная дата рождения: {dd}.{mm}.{full_year}")

    return {
        "valid": len(errors) == 0,
        "iin": iin,
        "errors": errors,
        "dob": dob,
        "gender": gender,
        "century": century_str,
    }
