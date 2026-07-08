"""
Configuration for all US sex offender registries.

Contains registry URLs, API endpoints, scraping parameters,
and state-specific configuration.
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class RegistryConfig:
    """Configuration for a single state's sex offender registry."""
    name: str                    # Full jurisdiction name
    abbr: str                    # Two-letter abbreviation (AL, TX, etc.)
    registry_url: str            # Main registry URL
    direct_downloads: List[str]  # Direct bulk download URLs
    download_page: Optional[str] = None  # Page with downloadable files
    scrape_method: str = "html"  # direct | api | html | hybrid
    search_api: Optional[str] = None  # Verified API endpoint only (do not invent)
    state_code_column: str = "state"  # Column name in CSV data
    notes: str = ""


# Registry configurations for all US states and territories
REGISTRIES = [
    RegistryConfig(
        name="National (NSOPW)", abbr="US",
        registry_url="https://www.nsopw.gov/",
        direct_downloads=[],
        scrape_method="hybrid",
        notes="Aggregated search interface across all jurisdictions. NOT a bulk download source."
    ),
    RegistryConfig(
        name="Alabama", abbr="AL",
        registry_url="https://www.alea.gov/node/270",
        direct_downloads=[],
        scrape_method="html"
    ),
    RegistryConfig(
        name="Alaska", abbr="AK",
        registry_url="https://sor.dps.alaska.gov/",
        direct_downloads=[],
        scrape_method="html",
        notes="Interactive search; no verified public bulk API."
    ),
    RegistryConfig(
        name="Arizona", abbr="AZ",
        registry_url="https://www.azdps.gov/services/public-services-center/sex-offender-compliance",
        direct_downloads=["https://icrimewatch.net/az_offenders.csv"],
        scrape_method="direct"
    ),
    RegistryConfig(
        name="Arkansas", abbr="AR",
        registry_url="https://sexoffenderregistry.ar.gov/",
        direct_downloads=[],
        scrape_method="html"
    ),
    RegistryConfig(
        name="California", abbr="CA",
        registry_url="https://oag.ca.gov/sex-offender-reg",
        direct_downloads=[],
        scrape_method="html",
        notes="Megan's Law search interface; no verified public bulk API."
    ),
    RegistryConfig(
        name="Colorado", abbr="CO",
        registry_url="https://apps.colorado.gov/apps/dps/sor/",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Connecticut", abbr="CT",
        registry_url="https://sheriffalerts.com/cap_office_disclaimer.php?office=54567",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Delaware", abbr="DE",
        registry_url="http://sexoffender.dsp.delaware.gov/",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="District of Columbia", abbr="DC",
        registry_url="https://sexoffender.dc.gov/",
        direct_downloads=[
            "https://opendata.dc.gov/api/download/v1/items/10e58174831e49a2aebaa129cc1c3bd5/csv?layers=20"
        ],
        scrape_method="direct"
    ),
    RegistryConfig(
        name="Florida", abbr="FL",
        registry_url="https://offender.fdle.state.fl.us/offender/sops/search.jsf",
        download_page="https://offender.fdle.state.fl.us/offender/sops/registryDownload.jsf",
        direct_downloads=[],
        scrape_method="hybrid"
    ),
    RegistryConfig(
        name="Georgia", abbr="GA",
        registry_url="https://gbi.georgia.gov/services/georgia-sex-offender-registry",
        direct_downloads=["https://state.sor.gbi.ga.gov/SORT_PUBLIC/sor.csv"],
        scrape_method="direct"
    ),
    RegistryConfig(
        name="Hawaii", abbr="HI",
        registry_url="https://sexoffenders.ehawaii.gov/",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Idaho", abbr="ID",
        registry_url="https://www.isp.idaho.gov/sor_id/",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Illinois", abbr="IL",
        registry_url="https://sor.isp.illinois.gov/",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Indiana", abbr="IN",
        registry_url="https://www.icrimewatch.net/indiana.php",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Iowa", abbr="IA",
        registry_url="https://www.iowasexoffender.gov/",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Kansas", abbr="KS",
        registry_url="https://www.kbi.ks.gov/registeredoffender/",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Kentucky", abbr="KY",
        registry_url="http://kspsor.state.ky.us/",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Louisiana", abbr="LA",
        registry_url="https://lsp.org/community-outreach/sex-offender-registry/",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Maine", abbr="ME",
        registry_url="http://sor.informe.org/cgi-bin/sor/index.pl",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Maryland", abbr="MD",
        registry_url="https://dpscs.maryland.gov/onlineservs/socem/default.shtml",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Massachusetts", abbr="MA",
        registry_url="https://www.mass.gov/orgs/sex-offender-registry-board",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Michigan", abbr="MI",
        registry_url="https://mspsor.com/",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Minnesota", abbr="MN",
        registry_url="https://coms.doc.state.mn.us/publicregistrantsearch",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Mississippi", abbr="MS",
        registry_url="https://state.sor.dps.ms.gov/",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Missouri", abbr="MO",
        registry_url="https://www.mshp.dps.missouri.gov/MSHPWeb/PatrolDivisions/CRID/SOR/SORPage.html",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Montana", abbr="MT",
        registry_url="https://app.doj.mt.gov/apps/svow/",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Nebraska", abbr="NE",
        registry_url="https://sor.nebraska.gov/",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Nevada", abbr="NV",
        registry_url="https://sexoffenders.nv.gov/",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="New Hampshire", abbr="NH",
        registry_url="https://business.nh.gov/nsor/",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="New Jersey", abbr="NJ",
        registry_url="https://www.njsp.org/sex-offender-registry/",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="New Mexico", abbr="NM",
        registry_url="https://sheriffalerts.com/cap_office_disclaimer.php?office=55290&fwd=aHR0cDovL2NvbW11bml0eW5vdGlmaWNhdGlvbi5jb20vY2FwX21haW4ucGhwP29mZmljZT01NTI5MA==",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="New York", abbr="NY",
        registry_url="https://www.criminaljustice.ny.gov/nsor/",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="North Carolina", abbr="NC",
        registry_url="https://sexoffender.ncsbi.gov/",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="North Dakota", abbr="ND",
        registry_url="https://www.sexoffender.nd.gov/",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Ohio", abbr="OH",
        registry_url="https://www.icrimewatch.net/index.php?AgencyID=55149&disc=",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Oklahoma", abbr="OK",
        registry_url="https://sors.doc.ok.gov/",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Oregon", abbr="OR",
        registry_url="https://sexoffenders.oregon.gov/",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Pennsylvania", abbr="PA",
        registry_url="https://www.pameganslaw.state.pa.us/",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Rhode Island", abbr="RI",
        registry_url="https://risp.ri.gov/safety-education/sex-offenders",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="South Carolina", abbr="SC",
        registry_url="https://scor.sled.sc.gov/",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="South Dakota", abbr="SD",
        registry_url="https://sor.sd.gov/",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Tennessee", abbr="TN",
        registry_url="https://sor.tbi.tn.gov/home",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Texas", abbr="TX",
        registry_url="https://publicsite.dps.texas.gov/SexOffenderRegistry",
        direct_downloads=[],
        scrape_method="html",
        notes="Search interface only; very large registry; no verified public bulk API."
    ),
    RegistryConfig(
        name="Utah", abbr="UT",
        registry_url="https://www.communitynotification.com/cap_office_disclaimer.php?office=54438",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Vermont", abbr="VT",
        registry_url="https://vcic.vermont.gov/sor",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Virginia", abbr="VA",
        registry_url="https://www.vsp.virginia.gov/sex-offender-registry/",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Washington", abbr="WA",
        registry_url="https://www.wasor.org/",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="West Virginia", abbr="WV",
        registry_url="https://apps.wv.gov/StatePolice/SexOffender",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Wisconsin", abbr="WI",
        registry_url="https://appsdoc.wi.gov/public/offenders",
        direct_downloads=[]
    ),
    RegistryConfig(
        name="Wyoming", abbr="WY",
        registry_url="https://wyomingdci.wyo.gov/criminal-justice-information-services-cjis/sex-offender-registry",
        direct_downloads=[]
    ),
]

# User-agent for polite scraping
USER_AGENT = (
    "Sex-Offender-Scraper/1.0 "
    "(legitimate data collection; respectful low-rate access)"
)

DEFAULT_DELAY = 2.0  # seconds between requests
MAX_RETRIES = 3
REQUEST_TIMEOUT = 60  # seconds


def get_registry_by_abbr(abbr: str) -> Optional[RegistryConfig]:
    """Look up a registry by its two-letter abbreviation."""
    for reg in REGISTRIES:
        if reg.abbr.lower() == abbr.lower():
            return reg
    return None


def get_registry_by_name(name: str) -> Optional[RegistryConfig]:
    """Look up a registry by full name (case-insensitive)."""
    for reg in REGISTRIES:
        if reg.name.lower() == name.lower():
            return reg
    return None


def get_direct_download_sources() -> List[RegistryConfig]:
    """Return registries that have direct download URLs."""
    return [r for r in REGISTRIES if r.direct_downloads]


def get_all_state_registries() -> List[RegistryConfig]:
    """Return all state registries (excluding National/US)."""
    return [r for r in REGISTRIES if r.abbr != "US"]