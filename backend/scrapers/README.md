# ATS scrapers & company configs (from apply)

Company YAML configs and ATS-specific scrapers are pulled from [jonathanrao99/apply](https://github.com/jonathanrao99/apply) (fork of kesiee/apply).

- **Company configs:** `../../companies/` (200+ YAMLs: Greenhouse, Lever, Ashby, Workday, SmartRecruiters, generic).
- **Scrapers:** `get_scraper(company, config)` returns the right scraper; config is `ApplyScraperConfig` from `load_apply_config()` (reads project-root `config.yaml`).

Usage:

```python
from backend.scrapers import get_scraper, Job
from backend.scrapers.apply_config import load_apply_config
import yaml
from pathlib import Path

cfg = load_apply_config()  # uses project root config.yaml
companies_dir = Path(__file__).resolve().parents[2] / "companies"
for f in sorted(companies_dir.glob("*.yaml")):
    with open(f) as fh:
        company = yaml.safe_load(fh)
    scraper = get_scraper(company, cfg)
    jobs = scraper.scrape()  # list of Job
```

Copy `config.yaml.example` to `config.yaml` in the project root and edit as needed.
