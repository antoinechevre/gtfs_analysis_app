"""
Génère le nuage de points HTML interactif (autonome, Plotly.js via CDN,
aucune dépendance serveur) du benchmark inter-réseaux — cf.
benchmark/index_benchmark_reseaux.csv sur le dataset HF ww_GTFS, alimenté
par le bouton "Enregistrer ce réseau dans le benchmark" de la page
Benchmark (views/benchmark.py) et la cellule équivalente du notebook.

Repris du même principe que le benchmark de l'app sœur "accessibility"
(src/nuage_points_benchmark.py, antoinechevre/Accessibility_analysis) :
un point par réseau, le réseau actuellement chargé surligné en rouge parmi
les autres en bleu. Simplifié ici (pas de décile/domaine à filtrer, un
seul réseau = un seul point, pas plusieurs lignes par domaine BPE) : axe
X fixe (population), Y au choix parmi les indicateurs transit disponibles.
"""

import json
import string

# Une seule abscisse pour l'instant (population de la ville, cf.
# src/population.py) — struct en liste pour rester extensible si d'autres
# abscisses ont un sens plus tard (ex: date_JOB).
OPTIONS_X = [
    ("population_totale", "Population de la ville"),
]

LIBELLES_Y = {
    "vehicules_km_total": "Véhicules.km totaux (tous modes)",
    "nombre_arrets": "Nombre d'arrêts",
    "vehicules_km_bus": "Véhicules.km Bus",
    "vehicules_km_metro": "Véhicules.km Métro",
    "vehicules_km_tram": "Véhicules.km Tram",
    "vehicules_km_par_1000hab_total": "Véh.km pour 1000 hab. (tous modes)",
    "vehicules_km_par_1000hab_bus": "Véh.km pour 1000 hab. (Bus seul)",
    "vehicules_km_par_1000hab_metro_tram": "Véh.km pour 1000 hab. (Métro+Tram)",
    # Index villes africaines (cf. views/benchmark.py, data/GTFS_Africa) :
    # substituts aux métriques BPE-par-domaine du benchmark standard,
    # indisponibles hors de France — cf. views/accessibilite.py.
    "population_accessible_60min": "Population accessible en 60 min",
    "equipements_accessibles_60min": "Équipements accessibles en 60 min (tous types)",
}

# Colonnes dérivées calculées à la volée (numérateur / population_totale *
# 1000), pas stockées dans le CSV : toujours à jour même si un ancien CSV
# a été enregistré avant leur ajout, tant que population_totale et le(s)
# numérateur(s) sont présents.
COLONNES_PAR_1000HAB = {
    "vehicules_km_par_1000hab_total": ("vehicules_km_total",),
    "vehicules_km_par_1000hab_bus": ("vehicules_km_bus",),
    "vehicules_km_par_1000hab_metro_tram": ("vehicules_km_metro", "vehicules_km_tram"),
}


def ajouter_colonnes_par_1000hab(df):
    """Ajoute les colonnes de COLONNES_PAR_1000HAB à df (copie), calculées
    si population_totale et les colonnes numérateur nécessaires sont
    présentes ; sinon la colonne dérivée n'est simplement pas ajoutée."""
    if "population_totale" not in df.columns:
        return df
    df = df.copy()
    for nom_colonne, numerateurs in COLONNES_PAR_1000HAB.items():
        if all(c in df.columns for c in numerateurs):
            df[nom_colonne] = sum(df[c] for c in numerateurs) / df["population_totale"] * 1000
    return df


def options_y(colonnes):
    """Ne propose que les colonnes Y effectivement présentes dans le CSV
    (un ancien CSV pourrait manquer une colonne ajoutée plus tard)."""
    return [(c, libelle) for c, libelle in LIBELLES_Y.items() if c in colonnes]


def generer_html_str(df, reseau_actuel=None):
    """Retourne le HTML du nuage de points (chaîne, pas de fichier écrit).

    reseau_actuel : si fourni (valeur de la colonne "reseau"), ses points
    sont surlignés en rouge parmi les autres en bleu. Sinon (mode
    autonome), tous les points sont dans la même couleur.

    Si un même réseau apparaît plusieurs fois (relances qui se sont
    chevauchées), seule la ligne à la date_JOB la plus récente est gardée
    — date_JOB au format YYYYMMDD (ordre lexicographique = chronologique).
    """
    if "date_JOB" in df.columns:
        df = df.loc[df.groupby("reseau")["date_JOB"].transform("max") == df["date_JOB"]]

    df = ajouter_colonnes_par_1000hab(df)

    options_x_dispo = [(c, l) for c, l in OPTIONS_X if c in df.columns]
    options_y_dispo = options_y(df.columns)

    for col in ("reseau", "ville_principale"):
        if col not in df.columns:
            raise ValueError(f"Colonne attendue absente du benchmark : {col}")
    if not options_x_dispo:
        raise ValueError("Aucune colonne d'abscisses reconnue (population_totale).")
    if not options_y_dispo:
        raise ValueError("Aucune colonne d'ordonnées reconnue parmi " + ", ".join(LIBELLES_Y))

    colonnes_utiles = ["reseau", "ville_principale"] + [c for c, _ in options_x_dispo] + [
        c for c, _ in options_y_dispo
    ]
    donnees = df[colonnes_utiles].to_dict(orient="records")

    template = string.Template(TEMPLATE_HTML)
    return template.substitute(
        donnees_json=json.dumps(donnees, ensure_ascii=False, default=str),
        options_x_json=json.dumps(options_x_dispo, ensure_ascii=False),
        options_y_json=json.dumps(options_y_dispo, ensure_ascii=False),
        nb_reseaux=df["reseau"].nunique(),
        reseau_actuel_json=json.dumps(reseau_actuel, ensure_ascii=False) if reseau_actuel else "null",
    )


TEMPLATE_HTML = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Benchmark inter-réseaux — nuage de points</title>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>
  :root {
    color-scheme: light;
    --surface-1: #fcfcfb;
    --page: #f9f9f7;
    --text-primary: #0b0b0b;
    --text-secondary: #52514e;
    --text-muted: #898781;
    --gridline: #e1e0d9;
    --baseline: #c3c2b7;
    --border: rgba(11,11,11,0.10);
    --couleur-actuel: #e34948;
    --couleur-autres: #2a78d6;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      color-scheme: dark;
      --surface-1: #1a1a19;
      --page: #0d0d0d;
      --text-primary: #ffffff;
      --text-secondary: #c3c2b7;
      --text-muted: #898781;
      --gridline: #2c2c2a;
      --baseline: #383835;
      --border: rgba(255,255,255,0.10);
      --couleur-actuel: #e66767;
      --couleur-autres: #3987e5;
    }
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; }
  body {
    margin: 0;
    background: var(--page);
    color: var(--text-primary);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  .page {
    max-width: 1200px;
    height: 100vh;
    margin: 0 auto;
    padding: 24px 20px 20px;
    overflow-y: auto;
  }
  h1 { font-size: 20px; font-weight: 600; margin: 0 0 4px; }
  .sous-titre { color: var(--text-secondary); font-size: 13px; margin: 0 0 20px; }
  .filtres {
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    align-items: flex-end;
    background: var(--surface-1);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 16px;
  }
  .filtre label {
    display: block;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: .03em;
    color: var(--text-muted);
    margin-bottom: 4px;
  }
  .filtre select { display: none; }
  .menu-perso { position: relative; }
  .menu-perso-bouton {
    font: inherit;
    font-size: 13px;
    padding: 6px 8px;
    border-radius: 6px;
    border: 1px solid var(--baseline);
    background: var(--surface-1);
    color: var(--text-primary);
    min-width: 240px;
    text-align: left;
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
  }
  .menu-perso-bouton::after { content: "▾"; color: var(--text-muted); font-size: 10px; }
  .menu-perso-liste {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    z-index: 20;
    background: var(--surface-1);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 4px;
    margin: 0;
    list-style: none;
    min-width: 100%;
    max-height: 240px;
    overflow-y: auto;
    box-shadow: 0 8px 24px rgba(0,0,0,0.15);
  }
  .menu-perso-liste[hidden] { display: none; }
  .menu-perso-liste li {
    padding: 6px 10px;
    font-size: 13px;
    border-radius: 6px;
    cursor: pointer;
    white-space: nowrap;
  }
  .menu-perso-liste li:hover, .menu-perso-liste li.actif { background: var(--gridline); }
  #chart {
    min-height: 260px;
    width: 100%;
    background: var(--surface-1);
    border: 1px solid var(--border);
    border-radius: 10px;
  }
  .bas-de-page { display: flex; justify-content: space-between; align-items: center; margin-top: 10px; }
  .bas-de-page button {
    font: inherit;
    font-size: 12px;
    padding: 6px 10px;
    border-radius: 6px;
    border: 1px solid var(--baseline);
    background: var(--surface-1);
    color: var(--text-primary);
    cursor: pointer;
  }
  #zone-tableau { margin-top: 16px; display: none; max-height: 240px; overflow-y: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; background: var(--surface-1); }
  th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--gridline); }
  th { color: var(--text-muted); font-weight: 600; text-transform: uppercase; font-size: 10px; letter-spacing: .03em; }
  td.num { font-variant-numeric: tabular-nums; text-align: right; }
</style>
</head>
<body>
<div class="page">
  <h1>Benchmark inter-réseaux</h1>
  <p class="sous-titre">$nb_reseaux réseau(x) — issu de benchmark/index_benchmark_reseaux.csv</p>

  <div class="filtres">
    <div class="filtre">
      <label>Abscisses</label>
      <select id="select-x" hidden></select>
    </div>
    <div class="filtre">
      <label>Ordonnées</label>
      <select id="select-y" hidden></select>
    </div>
  </div>

  <div id="chart"></div>

  <div class="bas-de-page">
    <span class="sous-titre" id="compte-points"></span>
    <button id="btn-tableau" type="button">Afficher le tableau</button>
  </div>

  <div id="zone-tableau"><table id="tableau"><thead></thead><tbody></tbody></table></div>
</div>

<script>
const DONNEES = $donnees_json;
const OPTIONS_X = $options_x_json;   // [[colonne, libelle], ...]
const OPTIONS_Y = $options_y_json;   // [[colonne, libelle], ...]
const RESEAU_ACTUEL = $reseau_actuel_json;  // nom du réseau à surligner, ou null

function cssVar(nom) {
  return getComputedStyle(document.documentElement).getPropertyValue(nom).trim();
}

function ajusterHauteurChart() {
  const page = document.querySelector(".page");
  const chart = document.getElementById("chart");
  const autresElements = Array.from(page.children).filter(el => el !== chart && el.id !== "zone-tableau");
  const hauteurAutres = autresElements.reduce((somme, el) => somme + el.offsetHeight, 0);
  const stylePage = getComputedStyle(page);
  const paddingVertical = parseFloat(stylePage.paddingTop) + parseFloat(stylePage.paddingBottom);
  const hauteurDisponible = page.clientHeight - hauteurAutres - paddingVertical;
  chart.style.height = Math.max(280, hauteurDisponible) + "px";
}

function remplirSelect(select, options, valeurDefaut) {
  select.textContent = "";
  for (const opt of options) {
    const el = document.createElement("option");
    el.value = opt[0];
    el.textContent = opt[1];
    select.appendChild(el);
  }
  if (valeurDefaut) select.value = valeurDefaut;
}

// Menu déroulant "maison" au-dessus d'un <select> natif gardé caché comme
// état/interface : l'iframe sandboxée de Streamlit (components.v1.html) a
// sandbox="allow-same-origin allow-scripts allow-downloads", sans
// allow-forms — Chrome y bloque l'ouverture du menu natif d'un <select>
// au clic réel.
function creerMenuPersonnalise(select) {
  const conteneur = document.createElement("div");
  conteneur.className = "menu-perso";
  const bouton = document.createElement("button");
  bouton.type = "button";
  bouton.className = "menu-perso-bouton";
  const liste = document.createElement("ul");
  liste.className = "menu-perso-liste";
  liste.hidden = true;
  conteneur.appendChild(bouton);
  conteneur.appendChild(liste);
  select.insertAdjacentElement("afterend", conteneur);

  function libelleDe(valeur) {
    const opt = Array.from(select.options).find(o => o.value === valeur);
    return opt ? opt.textContent : "";
  }

  function rafraichir() {
    bouton.textContent = libelleDe(select.value);
    liste.textContent = "";
    for (const opt of select.options) {
      const li = document.createElement("li");
      li.textContent = opt.textContent;
      if (opt.value === select.value) li.classList.add("actif");
      li.addEventListener("click", () => {
        select.value = opt.value;
        select.dispatchEvent(new Event("change"));
        liste.hidden = true;
        rafraichir();
      });
      liste.appendChild(li);
    }
  }

  bouton.addEventListener("click", (e) => {
    e.stopPropagation();
    liste.hidden = !liste.hidden;
  });
  document.addEventListener("click", () => { liste.hidden = true; });

  rafraichir();
}

const selectX = document.getElementById("select-x");
const selectY = document.getElementById("select-y");

remplirSelect(selectX, OPTIONS_X, OPTIONS_X[0][0]);
remplirSelect(selectY, OPTIONS_Y, OPTIONS_Y[0][0]);

[selectX, selectY].forEach(creerMenuPersonnalise);

let derniereSelection = [];

function traceDe(nom, couleur, pts, colX, colY, libelleX, libelleY, couleurTexte, couleurAnneau) {
  return {
    x: pts.map(l => l[colX]),
    y: pts.map(l => l[colY]),
    text: pts.map(l => l.ville_principale),
    customdata: pts.map(l => [l.reseau]),
    mode: "markers+text",
    type: "scatter",
    name: nom,
    textposition: "top center",
    textfont: { size: 11, color: couleurTexte },
    marker: { size: 10, color: couleur, line: { width: 2, color: couleurAnneau } },
    hovertemplate:
      "<b>%{text}</b> (%{customdata[0]})<br>" +
      libelleX + " : %{x}<br>" +
      libelleY + " : %{y:.1f}<extra></extra>",
  };
}

function redessiner() {
  const colX = selectX.value, colY = selectY.value;
  const libelleX = OPTIONS_X.find(o => o[0] === colX)[1];
  const libelleY = OPTIONS_Y.find(o => o[0] === colY)[1];

  const filtre = DONNEES.filter(l => l[colX] != null && l[colY] != null);
  derniereSelection = filtre;

  const couleurTexte = cssVar("--text-secondary");
  const couleurAnneau = cssVar("--surface-1");

  let traces, showlegend;
  if (RESEAU_ACTUEL) {
    const autres = filtre.filter(l => l.reseau !== RESEAU_ACTUEL);
    const actuel = filtre.filter(l => l.reseau === RESEAU_ACTUEL);
    traces = [
      traceDe("Autres réseaux", cssVar("--couleur-autres"), autres, colX, colY, libelleX, libelleY, couleurTexte, couleurAnneau),
      traceDe(`$${RESEAU_ACTUEL} (ce réseau)`, cssVar("--couleur-actuel"), actuel, colX, colY, libelleX, libelleY, couleurTexte, couleurAnneau),
    ];
    showlegend = true;
  } else {
    traces = [
      traceDe("Réseaux", cssVar("--couleur-autres"), filtre, colX, colY, libelleX, libelleY, couleurTexte, couleurAnneau),
    ];
    showlegend = false;
  }

  const couleurGrille = cssVar("--gridline");
  const couleurAxe = cssVar("--baseline");

  const layout = {
    margin: { l: 60, r: 20, t: 10, b: 50 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "system-ui, -apple-system, Segoe UI, sans-serif", color: "#898781", size: 12 },
    xaxis: { title: libelleX, gridcolor: couleurGrille, zerolinecolor: couleurAxe, linecolor: couleurAxe },
    yaxis: { title: libelleY, gridcolor: couleurGrille, zerolinecolor: couleurAxe, linecolor: couleurAxe },
    showlegend: showlegend,
    legend: { orientation: "h", y: -0.18 },
    hovermode: "closest",
  };

  Plotly.react("chart", traces, layout, { displayModeBar: true, responsive: true });
  document.getElementById("compte-points").textContent = `$${filtre.length} point(s) affiché(s)`;
  if (document.getElementById("zone-tableau").style.display !== "none") remplirTableau(colX, colY, libelleX, libelleY);
}

function remplirTableau(colX, colY, libelleX, libelleY) {
  const thead = document.querySelector("#tableau thead");
  const tbody = document.querySelector("#tableau tbody");
  thead.textContent = "";
  tbody.textContent = "";

  const ligneEntete = document.createElement("tr");
  for (const texte of ["Ville principale", "Réseau", libelleX, libelleY]) {
    const th = document.createElement("th");
    th.textContent = texte;
    ligneEntete.appendChild(th);
  }
  thead.appendChild(ligneEntete);

  for (const l of derniereSelection) {
    const tr = document.createElement("tr");
    const cellules = [l.ville_principale, l.reseau, l[colX], typeof l[colY] === "number" ? l[colY].toFixed(1) : l[colY]];
    cellules.forEach((valeur, i) => {
      const td = document.createElement("td");
      td.textContent = valeur;
      if (i >= 2) td.className = "num";
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  }
}

document.getElementById("zone-tableau").style.display = "none";

document.getElementById("btn-tableau").addEventListener("click", () => {
  const zone = document.getElementById("zone-tableau");
  const affichee = zone.style.display !== "none";
  zone.style.display = affichee ? "none" : "block";
  document.getElementById("btn-tableau").textContent = affichee ? "Afficher le tableau" : "Masquer le tableau";
  if (!affichee) remplirTableau(selectX.value, selectY.value, OPTIONS_X.find(o=>o[0]===selectX.value)[1], OPTIONS_Y.find(o=>o[0]===selectY.value)[1]);
});

[selectX, selectY].forEach(el => el.addEventListener("change", redessiner));

window.addEventListener("resize", () => {
  ajusterHauteurChart();
  Plotly.Plots.resize("chart");
});

ajusterHauteurChart();
redessiner();
</script>
</body>
</html>
"""
