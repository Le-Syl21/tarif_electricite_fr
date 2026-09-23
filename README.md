# Tarif électricité FR

<img src=".github/flags/gb.svg" height="14" alt="GB"> [English](#english) | <img src=".github/flags/fr.svg" height="14" alt="FR"> [Français](#français)

A Home Assistant integration for the French regulated electricity prices (EDF "Tarif Bleu": Base, Heures Creuses, Tempo), with the Tempo day colours.
Une intégration Home Assistant pour les tarifs réglementés de l'électricité (« Tarif Bleu » d'EDF : Base, Heures Creuses, Tempo), avec les couleurs Tempo.

<a name="français"></a>
## <img src=".github/flags/fr.svg" height="14" alt="FR"> Français

### Ce que ça donne

Pour une option et une puissance souscrite, l'intégration crée :

| Entité | Option | Quoi | Exemple |
|---|---|---|---|
| `sensor.prix_kwh_actuel` | toutes | Prix du kWh TTC, à brancher dans le tableau de bord Énergie | 0,1589 |
| `binary_sensor.heures_creuses` | toutes | Allumé pendant les heures creuses ; attribut `next_change` = prochaine bascule | Allumé, jusqu'à 06:00 |
| `sensor.periode_actuelle` | toutes | Période en cours | `rouge_hp` |
| `sensor.abonnement_mensuel` | toutes | Abonnement mensuel TTC | 15,86 € |
| `sensor.prix_en_vigueur_depuis` · `sensor.source_des_prix` | toutes | Diagnostic | 01/08/2026, CRE |
| `sensor.prix_kwh_hp` · `sensor.prix_kwh_hc` | Heures Creuses | Prix de chaque période | 0,2142 · 0,1589 |
| `sensor.prix_kwh_bleu_hc` · `sensor.prix_kwh_bleu_hp` · `sensor.prix_kwh_blanc_hc` · `sensor.prix_kwh_blanc_hp` · `sensor.prix_kwh_rouge_hc` · `sensor.prix_kwh_rouge_hp` | Tempo | Les six prix Tempo | 0,7295 |
| `sensor.couleur_du_jour` · `sensor.couleur_de_demain` | Tempo | Couleur Tempo | Bleu / Blanc / Rouge |
| `sensor.jours_bleus_restants` · `sensor.jours_blancs_restants` · `sensor.jours_rouges_restants` | Tempo | Jours restants dans la saison | 281 / 43 / 22 |

En option Base il n'y a qu'un prix : c'est `sensor.prix_kwh_actuel`, sans capteur de période supplémentaire.

Les identifiants sont **les mêmes chez tout le monde**, quelle que soit la langue de Home Assistant : les exemples ci-dessous marchent tels quels. Les libellés affichés, eux, sont traduits. Le capteur binaire existe aussi en option Base, où il reste éteint, pour qu'une automatisation écrite pour un contrat fonctionne avec les autres.

Le prix actuel change à la minute près : à l'heure creuse que vous avez indiquée, et à 6 h / 22 h pour Tempo. Une journée Tempo va de 6 h à 6 h le lendemain : à 3 h du matin, c'est encore la couleur de la veille qui s'applique, et l'intégration en tient compte.

La couleur de demain est publiée par RTE la veille vers 11 h ; avant, le capteur « Couleur Tempo de demain » est inconnu. RTE ne publie rien plus à l'avance.

Exemple : la veille d'un jour rouge, chauffer à fond pendant les heures creuses, jusqu'à 6 h.

```yaml
automation:
  - alias: Préchauffer avant un jour rouge
    triggers:
      - trigger: state
        entity_id: binary_sensor.heures_creuses
        to: "on"
    conditions:
      - condition: state
        entity_id: sensor.couleur_de_demain
        state: rouge
    actions:
      - action: climate.set_temperature
        target:
          entity_id: climate.salon
        data:
          temperature: 23
  - alias: Fin du préchauffage
    triggers:
      - trigger: state
        entity_id: binary_sensor.heures_creuses
        to: "off"
    actions:
      - action: climate.set_temperature
        target:
          entity_id: climate.salon
        data:
          temperature: 19
```

### Mise à jour depuis la 0.2

Jusqu'à la 0.2, l'identifiant était fabriqué à partir du nom de l'appareil et du libellé traduit : il changeait donc avec le contrat, la puissance et la langue de Home Assistant.

| Avant (0.2) | Depuis la 1.0 |
|---|---|
| `sensor.tarif_bleu_tempo_9_kva_prix_actuel` | `sensor.prix_kwh_actuel` |
| `sensor.tarif_bleu_tempo_9_kva_prix_jour_rouge_heures_pleines` | `sensor.prix_kwh_rouge_hp` |
| `sensor.tarif_bleu_heures_creuses_6_kva_prix_heures_creuses` | `sensor.prix_kwh_hc` |
| `binary_sensor.tarif_bleu_heures_creuses_6_kva_heures_creuses` | `binary_sensor.heures_creuses` |

Les entités sont renommées au premier démarrage, **sans perdre l'historique**. Un identifiant déjà pris par autre chose est laissé tranquille : l'ancienne entité garde alors son nom. Les automatisations, scripts et cartes qui citent les anciens identifiants sont à corriger à la main — Home Assistant ne les suit pas.

### Installation

1. HACS → *Dépôts personnalisés* → `https://github.com/Le-Syl21/tarif_electricite_fr`, catégorie *Intégration*.
2. Installez *Tarif électricité FR*, redémarrez Home Assistant.
3. *Paramètres* → *Appareils et services* → *Ajouter une intégration* → *Tarif électricité FR*.
4. Choisissez l'option, puis la puissance (en kVA, sur votre facture). Pour Heures Creuses, recopiez vos heures creuses telles qu'écrites sur la facture : `22:00-06:00`, `1h/7h30 & 13h/14h30` ou `HC (22H30-6H30)` sont acceptés. Elles se modifient ensuite dans *Configurer*.

### D'où viennent les prix

Aucun compte ni clé n'est nécessaire.

1. **La CRE** (Commission de régulation de l'énergie) publie l'historique des tarifs réglementés en [données ouvertes](https://www.cre.fr/documents/open-data/historique-des-tarifs-reglementes-de-vente-delectricite-pour-les-consommateurs-residentiels.html). L'intégration prend la ligne en vigueur *à la date du jour* : un changement de prix au 1er février ou au 1er août est appliqué ce jour-là, pas avant.
2. **La grille tarifaire d'EDF** ([PDF](https://particulier.edf.fr/content/dam/2-Actifs/Documents/Offres/Grille_prix_Tarif_Bleu.pdf)) prend le relais quand la CRE n'a pas encore publié un nouveau prix, et pour l'option Base de 18 à 36 kVA, que la CRE ne publie pas. Elle fournit aussi l'abonnement mensuel, tel qu'EDF le facture. Si EDF change la mise en page de sa grille, l'intégration l'ignore plutôt que de lire des prix faux.
3. **Les derniers prix connus** sont conservés : si les deux sources sont injoignables, rien ne tombe à « indisponible ».

Couleurs Tempo : l'API publique de **RTE**, avec [api-couleur-tempo.fr](https://www.api-couleur-tempo.fr) en secours.

### Qui décide quoi

- **Les prix** du Tarif Bleu, Tempo compris, sont proposés par la CRE et fixés par l'État (décision publiée au Journal officiel). Ils sont les mêmes partout en France métropolitaine continentale.
- **La couleur de chaque jour Tempo** est choisie par RTE, le gestionnaire du réseau de transport, la veille vers 11 h, dans la limite de 43 jours blancs et 22 jours rouges par saison (du 1er septembre au 31 août).
- **Vos heures creuses** (option Heures Creuses) sont fixées par votre gestionnaire de réseau de distribution, Enedis ou votre entreprise locale, compteur par compteur, dans le cadre défini par la CRE. Elles figurent sur votre facture. Elles peuvent changer : pensez à les mettre à jour dans *Configurer*. Les heures creuses Tempo, elles, sont les mêmes pour tous : 22 h - 6 h.

### Vous n'êtes pas client EDF ?

Les tarifs réglementés ne sont pas vendus que par EDF. Dans plus de 2 300 communes, c'est l'une des quelque cent **entreprises locales de distribution** (ELD) qui les vend : SICAE, régies, sociétés d'économie mixte. La [carte de l'Agence ORE](https://dataviz.agenceore.fr/distributeurs-energie-france/) indique le distributeur de chaque commune. Ce sont les héritières des distributeurs qui existaient avant la création d'EDF en 1946 et ont été maintenues à côté d'elle. Par exemple : [SICAE ELY](https://www.sicae-ely.fr/) (45 communes d'Eure-et-Loir et des Yvelines), Strasbourg Électricité Réseaux, GEG à Grenoble, SRD dans la Vienne, Gérédis dans les Deux-Sèvres.

Leurs prix du Tarif Bleu sont **les mêmes que ceux d'EDF**, puisqu'ils sont fixés par l'État : la grille de SICAE ELY au 1er août 2026 reprend au centime près les prix hors taxes de la CRE. Cette intégration convient donc aussi à leurs clients. L'appareil s'appelle « EDF » par commodité, c'est bien le tarif réglementé qui est suivi. Si votre entreprise locale gère aussi le réseau, c'est elle qui fixe vos heures creuses.

Les **offres de marché** des fournisseurs alternatifs (prix libres) ne sont pas couvertes.

### Limites

- **France métropolitaine continentale.** En Corse et outre-mer, les prix hors taxes sont les mêmes mais les prix TTC diffèrent.
- **Option EJP** : en extinction, sans source ouverte, non gérée.
- Les majorations ne sont pas incluses dans l'abonnement : absence de compteur Linky, absence de relève, autoproducteurs avec injection.
- Les prix TTC supposent la contribution d'acheminement (CTA) « de la majorité des clients » retenue par EDF et la CRE.

### Pourquoi une nouvelle intégration

[delphiki/hass-tarif-edf](https://github.com/delphiki/hass-tarif-edf) a longtemps rendu ce service. Elle prenait la dernière ligne du fichier plutôt que celle en vigueur, n'avait pas de source de secours, et n'est plus maintenue. Tarif électricité FR est écrite de zéro, sans reprendre son code.

<a name="english"></a>
## <img src=".github/flags/gb.svg" height="14" alt="GB"> English

### What you get

For one pricing option and one subscribed power, the integration creates:

| Entity | Option | What | Example |
|---|---|---|---|
| `sensor.prix_kwh_actuel` | all | Price of the kWh incl. taxes, for the Energy dashboard | 0.1589 |
| `binary_sensor.heures_creuses` | all | On during off-peak hours; `next_change` attribute holds the next switch | On, until 06:00 |
| `sensor.periode_actuelle` | all | Period in force | `rouge_hp` |
| `sensor.abonnement_mensuel` | all | Monthly subscription incl. taxes | €15.86 |
| `sensor.prix_en_vigueur_depuis` · `sensor.source_des_prix` | all | Diagnostic | 2026-08-01, CRE |
| `sensor.prix_kwh_hp` · `sensor.prix_kwh_hc` | Heures Creuses | Price of each period | 0.2142 · 0.1589 |
| `sensor.prix_kwh_bleu_hc` · `sensor.prix_kwh_bleu_hp` · `sensor.prix_kwh_blanc_hc` · `sensor.prix_kwh_blanc_hp` · `sensor.prix_kwh_rouge_hc` · `sensor.prix_kwh_rouge_hp` | Tempo | The six Tempo prices | 0.7295 |
| `sensor.couleur_du_jour` · `sensor.couleur_de_demain` | Tempo | Tempo colour | Blue / White / Red |
| `sensor.jours_bleus_restants` · `sensor.jours_blancs_restants` · `sensor.jours_rouges_restants` | Tempo | Days left in the season | 281 / 43 / 22 |

The Base option has a single price: that is `sensor.prix_kwh_actuel`, with no extra per-period sensor.

The ids are French on every install, on purpose: this integration only ever follows the French regulated tariff, so an example copied from this page or from a forum works as it is.

Entity ids are **the same on every install**, whatever the language of Home Assistant, so the examples below work as they are; the labels shown in the interface are translated. The binary sensor is created for the Base option too, where it stays off, so an automation written for one contract works with the others.

The price changes on the minute: at your off-peak hours, and at 06:00 / 22:00 for Tempo. A Tempo day runs from 06:00 to 06:00 the next day: at 03:00 the previous day's colour still applies, and the integration accounts for it.

RTE publishes tomorrow's colour the day before around 11:00; until then the "Tempo colour tomorrow" sensor is unknown. RTE publishes nothing further ahead.

Example: the day before a red day, heat at full power during off-peak hours, until 06:00: trigger on the *Off-peak hours* binary sensor turning on, with the condition *Tempo colour tomorrow* = `rouge`; set the temperature back when it turns off. The French section above has the full YAML.

### Upgrading from 0.2

Up to 0.2 the id was built from the device name and the translated label, so it changed with the contract, the power and the language of Home Assistant.

| Before (0.2) | Since 1.0 |
|---|---|
| `sensor.tarif_bleu_tempo_9_kva_prix_actuel` | `sensor.prix_kwh_actuel` |
| `sensor.tarif_bleu_tempo_9_kva_prix_jour_rouge_heures_pleines` | `sensor.prix_kwh_rouge_hp` |
| `sensor.tarif_bleu_heures_creuses_6_kva_prix_heures_creuses` | `sensor.prix_kwh_hc` |
| `binary_sensor.tarif_bleu_heures_creuses_6_kva_heures_creuses` | `binary_sensor.heures_creuses` |

Entities are renamed on the first start, **keeping their history**. An id already taken by something else is left alone, and that entity keeps its old name. Automations, scripts and cards naming the old ids have to be updated by hand: Home Assistant does not follow them.

### Installation

1. HACS → *Custom repositories* → `https://github.com/Le-Syl21/tarif_electricite_fr`, category *Integration*.
2. Install *Tarif électricité FR*, restart Home Assistant.
3. *Settings* → *Devices & services* → *Add integration* → *Tarif électricité FR*.
4. Pick the option, then the power (in kVA, on your bill). For Heures Creuses, copy your off-peak hours as written on your bill: `22:00-06:00`, `1h/7h30 & 13h/14h30` or `HC (22H30-6H30)` are accepted. They can be changed later under *Configure*.

### Where the prices come from

No account or key is needed.

1. **The CRE** (the French energy regulator) publishes the history of regulated prices as [open data](https://www.cre.fr/documents/open-data/historique-des-tarifs-reglementes-de-vente-delectricite-pour-les-consommateurs-residentiels.html). The integration uses the row in force *on the current date*: a price change on 1 February or 1 August applies that day, not before.
2. **EDF's price grid** ([PDF](https://particulier.edf.fr/content/dam/2-Actifs/Documents/Offres/Grille_prix_Tarif_Bleu.pdf)) takes over when the CRE has not published a new price yet, and for Base 18 to 36 kVA, which the CRE does not publish. It also gives the monthly subscription as EDF bills it. If EDF changes the layout of its grid, the integration ignores it rather than read wrong prices.
3. **The last known prices** are kept: if both sources are unreachable, nothing turns "unavailable".

Tempo colours: **RTE**'s public API, with [api-couleur-tempo.fr](https://www.api-couleur-tempo.fr) as fallback.

### Who decides what

- **The prices** of Tarif Bleu, Tempo included, are proposed by the CRE and set by the government. They are the same everywhere in mainland France.
- **The colour of each Tempo day** is chosen by RTE, the transmission system operator, around 11:00 the day before, within 43 white and 22 red days per season (1 September to 31 August).
- **Your off-peak hours** (Heures Creuses option) are set meter by meter by your distribution system operator, Enedis or your local company, under rules set by the CRE. They are on your bill and may change: update them under *Configure*. Tempo off-peak hours are the same for everyone: 22:00 - 06:00.

### Not an EDF customer?

EDF is not the only seller of regulated prices. In more than 2,300 towns, one of about a hundred **local distribution companies** (ELD) sells them: SICAE, municipal utilities, semi-public companies. [Agence ORE's map](https://dataviz.agenceore.fr/distributeurs-energie-france/) shows the distributor of each town. They descend from the distributors that existed before EDF was created in 1946 and were kept alongside it. For example: [SICAE ELY](https://www.sicae-ely.fr/) (45 towns in Eure-et-Loir and Yvelines), Strasbourg Électricité Réseaux, GEG in Grenoble, SRD in Vienne, Gérédis in Deux-Sèvres.

Their Tarif Bleu prices are **the same as EDF's**, since the government sets them: SICAE ELY's grid of 1 August 2026 matches the CRE's pre-tax prices to the cent. This integration therefore suits their customers too; the device is named "EDF" for convenience, what it follows is the regulated tariff. If your local company also runs the network, it sets your off-peak hours.

**Market offers** from alternative suppliers (free prices) are not covered.

### Limits

- **Mainland France.** In Corsica and overseas, pre-tax prices are the same but prices including taxes differ.
- **EJP option**: being phased out, no open source, not supported.
- Surcharges are not included in the subscription: no Linky meter, no meter reading, self-producers with grid injection.
- Prices including taxes assume the transmission contribution (CTA) "of most customers" used by EDF and the CRE.

### Why a new integration

[delphiki/hass-tarif-edf](https://github.com/delphiki/hass-tarif-edf) did this job for a long time. It took the last row of the file rather than the one in force, had no fallback source, and is no longer maintained. Tarif électricité FR is written from scratch and reuses none of its code.

## Development / Développement

```sh
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
```

## License / Licence

MIT. See [LICENSE](LICENSE).
