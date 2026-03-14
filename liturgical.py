"""
Computes the Roman Catholic (Ordinary Form) liturgical Sunday name and year
for a given date. Used as fallback when Catholic.org scraping fails.
"""

import datetime


def _easter(year):
    """Butcher's algorithm for Easter Sunday date."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return datetime.date(year, month, day)


def _advent_start(year):
    """First Sunday of Advent: Sunday on or nearest to Nov 30."""
    nov30 = datetime.date(year, 11, 30)
    # weekday(): Monday=0, Sunday=6
    dow = nov30.weekday()
    # Days to subtract to get to Sunday
    # Sunday is weekday 6; days_since_sunday = (dow + 1) % 7
    days_since_sunday = (dow + 1) % 7
    return nov30 - datetime.timedelta(days=days_since_sunday)


def liturgical_year_letter(sunday_date):
    """Return 'A', 'B', or 'C' for the given Sunday's liturgical year."""
    # Liturgical year starts on First Sunday of Advent.
    # Year C: 2024-2025, Year A: 2025-2026, Year B: 2026-2027, etc.
    # Cycle: C=0, A=1, B=2 relative to (civil_year - 2025) % 3
    year = sunday_date.year
    # Liturgical year that ENDS in `year` starts on First Sunday of Advent of year-1.
    # If the date is on/after this Advent start, we are in that lit. year (ending in year).
    # If the date is before that Advent start (i.e. Jan–Nov before Advent), the lit. year
    # already ended the previous calendar year, so lit_year = year.
    # Exception: if the date is on/after Advent of the CURRENT year, lit_year = year + 1.
    advent_this_year = _advent_start(year)
    if sunday_date >= advent_this_year:
        lit_year = year + 1
    else:
        lit_year = year
    # lit_year is the civil year in which the liturgical year ENDS
    # Year A ends in 2026, Year B ends in 2027, Year C ends in 2025, etc.
    # (lit_year - 2026) % 3: 0=A, 1=B, 2=C
    cycle = (lit_year - 2026) % 3
    return ['A', 'B', 'C'][cycle]


def get_liturgical_name(date):
    """
    Return the liturgical Sunday name for the given date (must be a Sunday).
    Returns a string like "Fourth Sunday of Lent, Year C" or None if not determinable.
    """
    if date.weekday() != 6:  # Not a Sunday
        return None

    year = date.year
    easter = _easter(year)
    year_letter = liturgical_year_letter(date)
    suffix = ", Year " + year_letter

    # --- Triduum / Easter Season ---
    easter_sunday = easter
    if date == easter_sunday:
        return "Easter Sunday" + suffix

    # Easter season: 7 weeks (Sundays 2–7 of Easter + Pentecost)
    for week in range(1, 7):
        sunday = easter + datetime.timedelta(weeks=week)
        if date == sunday:
            ordinals = ["Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh"]
            return ordinals[week - 1] + " Sunday of Easter" + suffix

    pentecost = easter + datetime.timedelta(weeks=7)
    if date == pentecost:
        return "Pentecost Sunday" + suffix

    trinity = pentecost + datetime.timedelta(weeks=1)
    if date == trinity:
        return "Trinity Sunday" + suffix

    # Corpus Christi (Sunday after Trinity in OF)
    corpus = trinity + datetime.timedelta(weeks=1)
    if date == corpus:
        return "Corpus Christi" + suffix

    # --- Lent: Ash Wednesday is 46 days before Easter ---
    ash_wednesday = easter - datetime.timedelta(days=46)
    lent_start_sunday = ash_wednesday - datetime.timedelta(days=ash_wednesday.weekday() + 1)
    # First Sunday of Lent
    first_lent_sunday = ash_wednesday + datetime.timedelta(days=(6 - ash_wednesday.weekday()) % 7)
    if first_lent_sunday.weekday() != 6:
        first_lent_sunday = ash_wednesday + datetime.timedelta(days=(13 - ash_wednesday.weekday()) % 7)

    lent_names = [
        "First Sunday of Lent",
        "Second Sunday of Lent",
        "Third Sunday of Lent",
        "Fourth Sunday of Lent",
        "Fifth Sunday of Lent",
        "Palm Sunday of the Passion of the Lord",
    ]
    for i, name in enumerate(lent_names):
        sunday = first_lent_sunday + datetime.timedelta(weeks=i)
        if date == sunday:
            return name + suffix

    # --- Advent ---
    advent_year = year if date.month >= 11 else year - 1
    advent1 = _advent_start(advent_year)
    advent_names = [
        "First Sunday of Advent",
        "Second Sunday of Advent",
        "Third Sunday of Advent",
        "Fourth Sunday of Advent",
    ]
    for i, name in enumerate(advent_names):
        sunday = advent1 + datetime.timedelta(weeks=i)
        if date == sunday:
            return name + suffix

    # --- Christmas Season ---
    christmas = datetime.date(year if date.month >= 11 else year - 1, 12, 25)
    # Holy Family: Sunday after Christmas (or Dec 30 if no Sunday between 25-30)
    for d in range(26, 32):
        try:
            candidate = datetime.date(christmas.year, 12, d)
        except ValueError:
            break
        if candidate.weekday() == 6:
            if date == candidate:
                return "The Holy Family of Jesus, Mary and Joseph" + suffix
            break
    else:
        # No Sunday; Holy Family falls on Dec 30
        dec30 = datetime.date(christmas.year, 12, 30)
        if date == dec30:
            return "The Holy Family of Jesus, Mary and Joseph" + suffix

    # Mary, Mother of God (Jan 1) — not a Sunday name but Octave
    # Epiphany Sunday
    jan6 = datetime.date(christmas.year + 1, 1, 6)
    # Epiphany observed on Sunday between Jan 2-8
    for d in range(2, 9):
        candidate = datetime.date(christmas.year + 1, 1, d)
        if candidate.weekday() == 6:
            if date == candidate:
                return "The Epiphany of the Lord" + suffix
            break

    # Baptism of the Lord: Sunday after Epiphany
    epiphany_sunday = None
    for d in range(2, 9):
        candidate = datetime.date(christmas.year + 1, 1, d)
        if candidate.weekday() == 6:
            epiphany_sunday = candidate
            break
    if epiphany_sunday:
        baptism = epiphany_sunday + datetime.timedelta(weeks=1)
        if date == baptism:
            return "The Baptism of the Lord" + suffix

    # --- Ordinary Time ---
    # OT begins after Baptism of the Lord, ends before Ash Wednesday
    # OT resumes after Pentecost until Advent
    # Sunday numbering in OT is complex; use a simple week counter
    if epiphany_sunday:
        ot_start = epiphany_sunday + datetime.timedelta(weeks=1)  # Baptism week is OT week 1
        ot_week = 2  # Week 2 starts the Sunday after Baptism of the Lord
        current = ot_start + datetime.timedelta(weeks=1)
        while current < first_lent_sunday:
            if date == current:
                return _ordinal(ot_week) + " Sunday in Ordinary Time" + suffix
            current += datetime.timedelta(weeks=1)
            ot_week += 1

        # Resume OT after Pentecost
        # The OT week number resumes where it left off based on how many Sundays
        # have elapsed since OT started (counting forward from week 1)
        # Week count from ot_start
        corpus_end = corpus + datetime.timedelta(weeks=1)
        # Next Sunday after Corpus Christi
        resume_sunday = corpus + datetime.timedelta(weeks=1)

        # Calculate what week OT is at when it resumes
        # Count how many OT Sundays passed before Lent
        weeks_before_lent = (first_lent_sunday - ot_start).days // 7
        # After Pentecost the week number jumps to account for what would have been
        # used. Standard: count from week 1 at Baptism forward through whole year,
        # skip the liturgical seasons.
        # Simpler: just count from ot_start to date and add week offset
        if date >= resume_sunday and date < _advent_start(year):
            weeks_from_start = (date - ot_start).days // 7 + 1
            # Subtract the Lent+Easter+Triduum block
            lent_easter_weeks = (pentecost - first_lent_sunday).days // 7 + 2  # +2 for Trinity+Corpus
            ot_week_num = weeks_from_start - lent_easter_weeks + 1
            if 2 <= ot_week_num <= 34:
                return _ordinal(ot_week_num) + " Sunday in Ordinary Time" + suffix

    return None  # Could not determine


def _ordinal(n):
    ordinals = [
        "", "First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh",
        "Eighth", "Ninth", "Tenth", "Eleventh", "Twelfth", "Thirteenth",
        "Fourteenth", "Fifteenth", "Sixteenth", "Seventeenth", "Eighteenth",
        "Nineteenth", "Twentieth", "Twenty-First", "Twenty-Second", "Twenty-Third",
        "Twenty-Fourth", "Twenty-Fifth", "Twenty-Sixth", "Twenty-Seventh",
        "Twenty-Eighth", "Twenty-Ninth", "Thirtieth", "Thirty-First",
        "Thirty-Second", "Thirty-Third", "Thirty-Fourth",
    ]
    if 0 <= n < len(ordinals):
        return ordinals[n]
    return str(n) + "th"


def next_sunday(today=None):
    """Return the date of the upcoming Sunday (or today if today is Sunday)."""
    if today is None:
        today = datetime.date.today()
    days_ahead = (6 - today.weekday()) % 7
    return today + datetime.timedelta(days=days_ahead)
