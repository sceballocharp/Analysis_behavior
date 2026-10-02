"""Plot lab work days as a highlighted calendar.

Examples
--------
Plot dates typed directly:
    python lab_work_calendar.py --dates 2026-01-03,2026-01-04,2026-02-12

Plot dates from a file with one date per line:
    python lab_work_calendar.py --dates-file lab_days.txt --year 2026
"""

from __future__ import annotations

import argparse
import calendar
from datetime import date, datetime
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def parse_date(value: str) -> date:
    """Parse common date formats into a date object."""
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(
        f"Could not parse date {value!r}. Use YYYY-MM-DD, DD/MM/YYYY, "
        "DD-MM-YYYY, or MM/DD/YYYY."
    )


def load_dates(
    dates_text: str | list[str] | tuple[str, ...] | None,
    dates_file: str | Path | None,
) -> set[date]:
    lab_days: set[date] = set()

    if dates_text:
        if isinstance(dates_text, str):
            date_items = dates_text.replace("\n", ",").split(",")
        else:
            date_items = dates_text

        for item in date_items:
            if item.strip():
                lab_days.add(parse_date(item))

    if dates_file:
        dates_file = Path(dates_file)
        for line in dates_file.read_text(encoding="utf-8").splitlines():
            item = line.split(",", maxsplit=1)[0].strip()
            if item and not item.startswith("#"):
                lab_days.add(parse_date(item))

    if not lab_days:
        raise ValueError("No lab dates were provided.")

    return lab_days


def draw_month(ax: plt.Axes, year: int, month: int, lab_days: set[date]) -> None:
    cal = calendar.Calendar(firstweekday=calendar.MONDAY)
    weeks = cal.monthdatescalendar(year, month)

    ax.set_xlim(0, 7)
    ax.set_ylim(0, 7.2)
    ax.axis("off")
    ax.set_title(calendar.month_name[month], fontsize=13, fontweight="bold", pad=8)

    for col, label in enumerate(WEEKDAY_LABELS):
        ax.text(
            col + 0.5,
            6.55,
            label,
            ha="center",
            va="center",
            fontsize=8,
            color="#555555",
        )

    for row, week in enumerate(weeks):
        y = 5.8 - row
        for col, day in enumerate(week):
            in_month = day.month == month
            is_lab_day = day in lab_days

            facecolor = "#2F80ED" if is_lab_day else "#F4F4F4"
            edgecolor = "#1B5FB8" if is_lab_day else "#DDDDDD"
            text_color = "white" if is_lab_day else ("#222222" if in_month else "#BBBBBB")

            ax.add_patch(
                Rectangle(
                    (col + 0.06, y - 0.42),
                    0.88,
                    0.78,
                    facecolor=facecolor,
                    edgecolor=edgecolor,
                    linewidth=1.2 if is_lab_day else 0.8,
                )
            )
            ax.text(
                col + 0.5,
                y,
                str(day.day),
                ha="center",
                va="center",
                fontsize=9,
                color=text_color,
                fontweight="bold" if is_lab_day else "normal",
            )


def plot_lab_calendar(
    lab_days: set[date],
    year: int | None = None,
    output: Path | None = None,
) -> None:
    if year is None:
        years = sorted({day.year for day in lab_days})
    else:
        years = [year]

    for selected_year in years:
        fig, axes = plt.subplots(3, 4, figsize=(14, 9), constrained_layout=True)
        fig.suptitle(
            f"Lab work days in {selected_year}",
            fontsize=18,
            fontweight="bold",
        )

        for month, ax in enumerate(axes.flat, start=1):
            draw_month(ax, selected_year, month, lab_days)

        total_days = sum(1 for day in lab_days if day.year == selected_year)
        fig.text(
            0.5,
            0.02,
            f"{total_days} highlighted lab day{'s' if total_days != 1 else ''}",
            ha="center",
            fontsize=11,
            color="#444444",
        )

        if output:
            if len(years) > 1:
                out_path = output.with_stem(f"{output.stem}_{selected_year}")
            else:
                out_path = output
            fig.savefig(out_path, dpi=200, bbox_inches="tight")
            print(f"Saved {out_path}")
        else:
            plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dates",
        help="Comma-separated dates, for example: 2026-01-03,2026-01-04",
    )
    parser.add_argument(
        "--dates-file",
        type=Path,
        help="Text/CSV file. The first value on each line should be a date.",
    )
    parser.add_argument(
        "--year",
        type=int,
        help="Calendar year to plot. Defaults to all years found in the dates.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("lab_work_calendar.png"),
        help="Output image path. Use --show if you prefer an interactive window.",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Show the figure interactively instead of saving it.",
    )
    args = parser.parse_args()

    lab_days = load_dates(args.dates, args.dates_file)
    plot_lab_calendar(lab_days, year=args.year, output=None if args.show else args.output)


if __name__ == "__main__":
    main()
