"""Constants for the Tarif électricité FR integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "tarif_electricite_fr"

CONF_OPTION: Final = "option"
CONF_POWER: Final = "power"
CONF_OFFPEAK: Final = "offpeak_hours"

OPTION_BASE: Final = "base"
OPTION_HPHC: Final = "hphc"
OPTION_TEMPO: Final = "tempo"
OPTIONS: Final = (OPTION_BASE, OPTION_HPHC, OPTION_TEMPO)

# Subscribed powers offered by the "Tarif Bleu" residential grid, in kVA.
POWERS: Final = {
    OPTION_BASE: (3, 6, 9, 12, 15, 18, 24, 30, 36),
    OPTION_HPHC: (3, 6, 9, 12, 15, 18, 24, 30, 36),
    OPTION_TEMPO: (6, 9, 12, 15, 18, 24, 30, 36),
}

# Pricing periods of each option, in the order the grids list them.
PERIODS: Final = {
    OPTION_BASE: ("base",),
    OPTION_HPHC: ("hp", "hc"),
    OPTION_TEMPO: ("bleu_hc", "bleu_hp", "blanc_hc", "blanc_hp", "rouge_hc", "rouge_hp"),
}

DEFAULT_OFFPEAK: Final = "22:00-06:00"

# Tempo days run from 06:00 to 06:00 the next day; off-peak is 22:00-06:00.
TEMPO_DAY_START_HOUR: Final = 6
TEMPO_OFFPEAK_START_HOUR: Final = 22

TEMPO_COLOURS: Final = ("bleu", "blanc", "rouge")

# Regulated prices published by the CRE (Licence Ouverte), one file per option.
CRE_URLS: Final = {
    OPTION_BASE: "https://www.cre.fr/fileadmin/Documents/Open_data/Marches_de_detail/Option_Base.csv",
    OPTION_HPHC: "https://www.cre.fr/fileadmin/Documents/Open_data/Marches_de_detail/Option_HPHC.csv",
    OPTION_TEMPO: "https://www.cre.fr/fileadmin/Documents/Open_data/Marches_de_detail/Option_Tempo.csv",
}

# EDF's own price grid: fallback when the CRE lags behind or lacks a power.
EDF_GRID_URL: Final = (
    "https://particulier.edf.fr/content/dam/2-Actifs/Documents/Offres/Grille_prix_Tarif_Bleu.pdf"
)

# Tempo colours: RTE's public endpoint first, the community API as fallback.
RTE_TEMPO_URL: Final = "https://www.services-rte.com/cms/open_data/v1/tempoLight"
COULEUR_TEMPO_URL: Final = "https://www.api-couleur-tempo.fr/api"

UPDATE_INTERVAL: Final = timedelta(hours=1)
EDF_GRID_REFRESH: Final = timedelta(hours=12)

# Browsers only: particulier.edf.fr answers 403 to unknown user agents.
USER_AGENT: Final = "Mozilla/5.0 (X11; Linux x86_64) Home Assistant tarif_electricite_fr"

STORAGE_VERSION: Final = 1

# Entity ids are fixed, and in French, whatever the language of Home Assistant:
# this integration only ever serves the French regulated tariff, so an example
# copied from the documentation or a forum works as it is on every install.
# Labels stay translated. One meter per home, so no contract in the id.
OBJECT_IDS: Final = {
    "price_now": "prix_kwh_actuel",
    "period_now": "periode_actuelle",
    "subscription": "abonnement_mensuel",
    "valid_from": "prix_en_vigueur_depuis",
    "source": "source_des_prix",
    "offpeak": "heures_creuses",
    "colour_today": "couleur_du_jour",
    "colour_tomorrow": "couleur_de_demain",
    **{f"price_{p}": f"prix_kwh_{p}" for p in ("base", "hp", "hc")},
    **{
        f"price_{colour}_{slot}": f"prix_kwh_{colour}_{slot}"
        for colour in TEMPO_COLOURS
        for slot in ("hc", "hp")
    },
    **{f"remaining_{c}": f"jours_{c}s_restants" for c in TEMPO_COLOURS},
}
