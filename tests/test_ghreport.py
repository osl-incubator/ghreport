from pathlib import Path

from ghreport import GHReport
from ghreport.config import ArgsCLI


def test_ghreport():
    report = GHReport(
        ArgsCLI(
            **{
                "start_date": "2023-07-01",
                "end_date": "2023-07-31",
                "config_file": str(Path(__file__).parent / ".ghreport.yaml"),
            }
        )
    )
    report.run()
