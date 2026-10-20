"""Icônes (tracés de 24×24, style trait) et couleurs par catégorie."""

ICONS = {
    "grid": ["M3 3h7v7H3z", "M14 3h7v7h-7z", "M14 14h7v7h-7z", "M3 14h7v7H3z"],
    "list": ["M8 6h13", "M8 12h13", "M8 18h13", "M3 6h.01", "M3 12h.01", "M3 18h.01"],
    "repeat": ["M17 1l4 4-4 4", "M3 11V9a4 4 0 0 1 4-4h14", "M7 23l-4-4 4-4", "M21 13v2a4 4 0 0 1-4 4H3"],
    "scissors": ["M6 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6z", "M6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
                 "M20 4L8.12 15.88", "M14.47 14.48L20 20", "M8.12 8.12L12 12"],
    "sliders": ["M4 21v-7", "M4 10V3", "M12 21v-9", "M12 8V3", "M20 21v-5", "M20 12V3", "M1 14h6", "M9 8h6", "M17 16h6"],
    "upload": ["M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4", "M17 8l-5-5-5 5", "M12 3v12"],
    "sun": ["M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10z", "M12 1v2", "M12 21v2", "M4.22 4.22l1.42 1.42",
            "M18.36 18.36l1.42 1.42", "M1 12h2", "M21 12h2", "M4.22 19.78l1.42-1.42", "M18.36 5.64l1.42-1.42"],
    "chev-left": ["M15 18l-6-6 6-6"],
    "chev-right": ["M9 18l6-6-6-6"],
    "check": ["M20 6L9 17l-5-5"],
    "home": ["M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z", "M9 22V12h6v10"],
    "zap": ["M13 2L3 14h9l-1 8 10-12h-9l1-8z"],
    "shield": ["M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"],
    "bag": ["M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z", "M3 6h18", "M16 10a4 4 0 0 1-8 0"],
    "coffee": ["M18 8h1a4 4 0 0 1 0 8h-1", "M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z", "M6 1v3", "M10 1v3", "M14 1v3"],
    "car": ["M3 13l2-6h14l2 6v5H3z", "M3 18v2", "M21 18v2", "M7 15.5h.01", "M17 15.5h.01"],
    "heart": ["M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"],
    "users": ["M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2", "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8",
              "M23 21v-2a4 4 0 0 0-3-3.87", "M16 3.13a4 4 0 0 1 0 7.75"],
    "card": ["M1 4h22v16H1z", "M1 10h22"],
    "file": ["M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z", "M14 2v6h6", "M16 13H8", "M16 17H8"],
    "trend": ["M23 6l-9.5 9.5-5-5L1 18", "M17 6h6v6"],
    "play": ["M5 3l14 9-14 9z"],
    "phone": ["M5 2h14v20H5z", "M12 18h.01"],
    "scale": ["M12 3v18", "M5 21h14", "M5 7h14", "M5 7l-3 7a3 3 0 0 0 6 0z", "M19 7l-3 7a3 3 0 0 0 6 0z"],
    "euro": ["M18 7a6 6 0 1 0 0 10", "M4 10h10", "M4 14h10"],
    "tool": ["M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94z"],
    "help": ["M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z", "M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3", "M12 17h.01"],
}

# catégorie -> (icône, couleur)
CATEGORY_STYLE = {
    "Foyer (compte joint)": ("home", "#7b8bff"),
    "Crédit immobilier": ("home", "#8a96b0"),
    "Crédit conso": ("card", "#8a96b0"),
    "Impôts et taxes": ("file", "#a3a3b8"),
    "Énergie": ("zap", "#facc15"),
    "Télécom": ("phone", "#60a5fa"),
    "Assurances & mutuelle": ("shield", "#34d399"),
    "Logement": ("tool", "#2dd4bf"),
    "Frais bancaires": ("euro", "#94a3b8"),
    "Alimentation": ("coffee", "#38bdf8"),
    "Transports": ("car", "#fb923c"),
    "Santé": ("heart", "#f87171"),
    "Shopping & loisirs": ("bag", "#c084fc"),
    "PayPal (à détailler)": ("card", "#f472b6"),
    "Abonnements & services": ("repeat", "#84cc16"),
    "Juridique": ("scale", "#a78bfa"),
    "Famille & amis": ("users", "#fb7185"),
    "À catégoriser": ("help", "#94a3b8"),
    "Investissement": ("trend", "#4ade9b"),
    "Autres": ("grid", "#94a3b8"),
}


def category_style(category: str) -> dict:
    icon, color = CATEGORY_STYLE.get(category, ("help", "#94a3b8"))
    return {"icon": icon, "color": color}
