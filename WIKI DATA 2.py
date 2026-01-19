"""
🛡️ Architecte d'Autorité Sémantique v4.8 (Audit & Social Color Fix)
------------------------------------------------------------------
- Fix : Couleurs sociales rétablies (plus de bulles noires).
- Fix : Détection Instagram et réseaux sociaux dans le graph.
- Audit : Conservation de l'adresse, SIRET, APE et Fusion.
- Graphique 3-Orbites : IDs -> Écosystème -> Social (avec Labels).
"""

import streamlit as st
import requests
import pandas as pd
import json
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
import time
import math

# ============================================================================
# CONFIGURATION & STYLE
# ============================================================================
st.set_page_config(
    page_title="Architecte d'Autorité Sémantique",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main { background-color: #F8FAFC; }
    .stTabs [data-baseweb="tab-list"] { 
        gap: 8px; background: white; padding: 10px; border-radius: 12px; border: 1px solid #E5E7EB;
    }
    .stTabs [aria-selected="true"] { background-color: #0066FF !important; color: white !important; }
    section[data-testid="stSidebar"] { background-color: #FFFFFF; border-right: 1px solid #E5E7EB; }
    .stMetric { background: white; padding: 15px; border-radius: 10px; border: 1px solid #E5E7EB; }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# DATA MODELS
# ============================================================================
@dataclass
class Entity:
    name: str = ""
    qid: str = ""
    siren: str = ""
    siret: str = ""
    isni: str = ""
    ror: str = ""
    lei: str = ""
    address: str = ""
    postal_code: str = ""
    city: str = ""
    country: str = "France"
    ape: str = ""
    creation_date: str = ""
    website: str = ""
    
    def authority_score(self) -> int:
        score = 0
        if self.qid: score += 25
        if self.siren: score += 20
        if self.isni: score += 15
        if self.ror: score += 15
        if self.lei: score += 15
        if self.website: score += 10
        return min(score, 100)

@dataclass
class Relation:
    qid: str
    name: str
    relation_type: str = "lié"
    schema_type: str = "subOrganization"
    include: bool = True

# ============================================================================
# API MANAGER
# ============================================================================
class APIManager:
    WIKIDATA_API = "https://www.wikidata.org/w/api.php"
    WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
    INSEE_API = "https://recherche-entreprises.api.gouv.fr/search"
    HEADERS = {"User-Agent": "SemanticAuthority/4.8", "Accept": "application/json"}

    @st.cache_data(ttl=3600, show_spinner=False)
    def search_wikidata(_self, query: str) -> List[Dict]:
        try:
            p = {"action": "wbsearchentities", "search": query, "language": "fr", "format": "json", "limit": 10}
            r = requests.get(_self.WIKIDATA_API, params=p, headers=_self.HEADERS)
            return [{'qid': i['id'], 'label': i.get('label', ''), 'description': i.get('description', '')} for i in r.json().get('search', [])]
        except: return []

    @st.cache_data(ttl=1800, show_spinner=False)
    def search_insee(_self, query: str) -> List[Dict]:
        try:
            r = requests.get(_self.INSEE_API, params={"q": query, "per_page": 10})
            return r.json().get('results', [])
        except: return []

    @st.cache_data(ttl=3600, show_spinner=False)
    def get_wikidata_entity(_self, qid: str) -> Dict:
        q = f"""SELECT ?siren ?siret ?isni ?ror ?lei ?website ?inception ?hqLabel WHERE {{
          BIND(wd:{qid} AS ?item)
          OPTIONAL {{ ?item wdt:P1616 ?siren. }} OPTIONAL {{ ?item wdt:P1185 ?siret. }}
          OPTIONAL {{ ?item wdt:P213 ?isni. }} OPTIONAL {{ ?item wdt:P6782 ?ror. }}
          OPTIONAL {{ ?item wdt:P1278 ?lei. }} OPTIONAL {{ ?item wdt:P856 ?website. }}
          OPTIONAL {{ ?item wdt:P571 ?inception. }} OPTIONAL {{ ?item wdt:P159 ?hq. }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "fr,en". }}
        }} LIMIT 1"""
        try:
            r = requests.get(_self.WIKIDATA_SPARQL, params={'query': q, 'format': 'json'}, timeout=10)
            bindings = r.json()['results']['bindings']
            if not bindings: return {}
            b = bindings[0]
            return {
                'siren': b.get('siren', {}).get('value', ''), 'siret': b.get('siret', {}).get('value', ''),
                'isni': b.get('isni', {}).get('value', ''), 'ror': b.get('ror', {}).get('value', ''),
                'lei': b.get('lei', {}).get('value', ''), 'website': b.get('website', {}).get('value', ''),
                'inception': b.get('inception', {}).get('value', ''), 'headquarters': b.get('hqLabel', {}).get('value', '')
            }
        except: return {}

# ============================================================================
# GRAPH RENDERER (FIX COULEURS SOCIALES & LABELS)
# ============================================================================
def render_authority_graph(entity: Entity, relations: List[Relation], social_links: Dict[str, str]):
    W, H = 850, 720
    CX, CY = W/2, H/2 - 20
    R_ID, R_REL, R_SOC = 180, 260, 330
    
    # Orbite 1 : IDs
    ids = [
        ("Wikidata", entity.qid, "#22C55E", "W"), ("INSEE", entity.siren, "#F97316", "S"),
        ("ISNI", entity.isni, "#A855F7", "I"), ("ROR", entity.ror, "#EC4899", "R"),
        ("LEI", entity.lei, "#06B6D4", "L"), ("Web", entity.website, "#3B82F6", "W")
    ]
    
    # Orbite 2 : Écosystème (Inclus uniquement)
    rels_to_draw = [r for r in relations if r.include]
    
    # Orbite 3 : Social (Filtrage et Config Couleurs)
    socs_to_draw = []
    social_cfg = {
        'linkedin': ('#0077B5', 'In'), 
        'twitter': ('#1DA1F2', 'X'), 
        'facebook': ('#1877F2', 'Fb'), 
        'instagram': ('#E4405F', 'Ig'), 
        'youtube': ('#FF0000', 'Yt'),
        'tiktok': ('#000000', 'Tk')
    }
    
    for net, url in social_links.items():
        if url and url.strip():
            conf = social_cfg.get(net, ('#64748B', 'S'))
            socs_to_draw.append((net.capitalize(), url, conf[0], conf[1]))

    svg = f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="background:white; border-radius:20px;">'
    svg += '<defs><filter id="sh"><feDropShadow dx="0" dy="2" stdDeviation="3" flood-opacity="0.15"/></filter>'
    svg += '<linearGradient id="gr" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#3B82F6"/><stop offset="100%" stop-color="#1E40AF"/></linearGradient></defs>'
    
    # Cercles d'orbite
    svg += f'<circle cx="{CX}" cy="{CY}" r="{R_ID}" fill="none" stroke="#F1F5F9" stroke-width="2" stroke-dasharray="10,5" />'
    if rels_to_draw: svg += f'<circle cx="{CX}" cy="{CY}" r="{R_REL}" fill="none" stroke="#F1F5F9" stroke-width="2" stroke-dasharray="5,5" />'
    if socs_to_draw: svg += f'<circle cx="{CX}" cy="{CY}" r="{R_SOC}" fill="none" stroke="#F1F5F9" stroke-width="1" stroke-dasharray="2,2" />'

    # Dessin IDs
    for i, (lab, val, col, ico) in enumerate(ids):
        angle = (2 * math.pi * i) / len(ids) - (math.pi / 2)
        x, y = CX + R_ID * math.cos(angle), CY + R_ID * math.sin(angle)
        active = bool(val)
        svg += f'<line x1="{CX}" y1="{CY}" x2="{x}" y2="{y}" stroke="{col if active else "#E2E8F0"}" stroke-width="1.5" opacity="0.3" />'
        svg += f'<circle cx="{x}" cy="{y}" r="34" fill="{col if active else "#F8FAFC"}" filter="url(#sh)" opacity="{1 if active else 0.6}" />'
        svg += f'<text x="{x}" y="{y+7}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="20" fill="{"white" if active else "#94A3B8"}">{ico}</text>'
        svg += f'<text x="{x}" y="{y+50}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="10" fill="{"#1E293B" if active else "#94A3B8"}">{lab}</text>'

    # Dessin Écosystème
    for i, rel in enumerate(rels_to_draw):
        angle = (2 * math.pi * i) / len(rels_to_draw) - (math.pi / 2) + 0.2
        x, y = CX + R_REL * math.cos(angle), CY + R_REL * math.sin(angle)
        svg += f'<line x1="{CX}" y1="{CY}" x2="{x}" y2="{y}" stroke="#6366F1" stroke-width="1" opacity="0.2" />'
        svg += f'<circle cx="{x}" cy="{y}" r="26" fill="#6366F1" filter="url(#sh)" />'
        svg += f'<text x="{x}" y="{y+40}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="9" fill="#4338CA">{rel.name[:15]}</text>'

    # Dessin Social (FIX COULEURS & LABELS)
    for i, (lab, url, col, ico) in enumerate(socs_to_draw):
        angle = (2 * math.pi * i) / len(socs_to_draw) - (math.pi / 2) - 0.2
        x, y = CX + R_SOC * math.cos(angle), CY + R_SOC * math.sin(angle)
        svg += f'<line x1="{CX}" y1="{CY}" x2="{x}" y2="{y}" stroke="{col}" stroke-width="1" opacity="0.1" stroke-dasharray="2,2" />'
        svg += f'<circle cx="{x}" cy="{y}" r="24" fill="{col}" filter="url(#sh)" />'
        svg += f'<text x="{x}" y="{y+6}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="13" fill="white">{ico}</text>'
        svg += f'<text x="{x}" y="{y+40}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="9" fill="#64748B">{lab}</text>'

    # Centre
    score = entity.authority_score()
    name = (entity.name[:18] + "..") if len(entity.name) > 18 else entity.name
    svg += f'<circle cx="{CX}" cy="{CY}" r="78" fill="url(#gr)" filter="url(#sh)" />'
    svg += f'<text x="{CX}" y="{CY-15}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="13" fill="white">{name}</text>'
    svg += f'<text x="{CX}" y="{CY+22}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="40" fill="white">{score}%</text>'
    svg += f'<text x="{CX}" y="{CY+42}" text-anchor="middle" font-family="Arial" font-size="9" fill="rgba(255,255,255,0.85)">SCORE D\'AUTORITÉ</text>'
    svg += '</svg>'
    return svg

# ============================================================================
# INITIALISATION
# ============================================================================
api = APIManager()
if 'entity' not in st.session_state: st.session_state.entity = Entity()
if 'relations' not in st.session_state: st.session_state.relations = []
if 'social_links' not in st.session_state: 
    st.session_state.social_links = {k:'' for k in ['linkedin','twitter','facebook','instagram','youtube','tiktok']}
if 'res_wiki' not in st.session_state: st.session_state.res_wiki = []
if 'res_insee' not in st.session_state: st.session_state.res_insee = []

# ============================================================================
# SIDEBAR (FUSION & PERSISTANCE)
# ============================================================================
with st.sidebar:
    st.header("🔍 Audit Sémantique")
    src = st.radio("Source de recherche", ["Mixte", "Wikidata", "INSEE"], horizontal=True)
    q = st.text_input("Nom de l'organisation")
    
    if st.button("Lancer la recherche", type="primary", use_container_width=True) and q:
        with st.spinner("Audit des bases..."):
            st.session_state.res_wiki = api.search_wikidata(q) if src in ["Mixte", "Wikidata"] else []
            st.session_state.res_insee = api.search_insee(q) if src in ["Mixte", "INSEE"] else []

    if st.session_state.res_wiki:
        st.markdown("**🌐 Wikidata**")
        for i, res in enumerate(st.session_state.res_wiki[:5]):
            if st.button(f"Fusionner {res['label'][:22]}", key=f"W_{i}", use_container_width=True):
                e = st.session_state.entity
                e.name = e.name or res['label']
                e.qid = res['qid']
                d = api.get_wikidata_entity(e.qid)
                e.siren = e.siren or d.get('siren','')
                e.website = e.website or d.get('website','')
                e.isni = e.isni or d.get('isni','')
                e.ror = e.ror or d.get('ror','')
                e.lei = e.lei or d.get('lei','')
                # Relations auto
                from_wiki = requests.get("https://query.wikidata.org/sparql", params={'query': f'SELECT DISTINCT ?item ?itemLabel WHERE {{ {{ wd:{e.qid} wdt:P355 ?item. }} UNION {{ ?item wdt:P355 wd:{e.qid}. }} SERVICE wikibase:label {{ bd:serviceParam wikibase:language "fr,en". }} }} LIMIT 10', 'format': 'json'}).json()['results']['bindings']
                st.session_state.relations.extend([Relation(qid=r['item']['value'].split('/')[-1], name=r['itemLabel']['value']) for r in from_wiki])
                st.session_state.entity = e
                st.rerun()

    if st.session_state.res_insee:
        st.markdown("**🏛️ INSEE**")
        for i, res in enumerate(st.session_state.res_insee[:5]):
            if st.button(f"Fusionner {res.get('nom_complet','')[:22]}", key=f"I_{i}", use_container_width=True):
                e = st.session_state.entity
                e.name = e.name or res.get('nom_complet','')
                e.siren = res.get('siren','')
                s = res.get('siege', {})
                e.address = s.get('adresse', '')
                e.postal_code = s.get('code_postal', '')
                e.city = s.get('libelle_commune', '')
                e.siret = s.get('siret', '')
                e.ape = res.get('activite_principale', '')
                st.session_state.entity = e
                st.rerun()
    
    st.divider()
    if st.button("🗑️ Reset Dossier", use_container_width=True):
        st.session_state.entity = Entity()
        st.session_state.relations = []
        st.session_state.social_links = {k:'' for k in st.session_state.social_links}
        st.rerun()

# ============================================================================
# MAIN UI
# ============================================================================
st.title("🛡️ Architecte d'Autorité Sémantique")

if st.session_state.entity.name or st.session_state.entity.siren or st.session_state.entity.qid:
    st.success(f"Audit actif : **{st.session_state.entity.name}**")
    tabs = st.tabs(["🎯 Cartographie", "🆔 Identité & Légal", "🏢 Écosystème", "📱 Social Hub", "💾 Export"])
    
    with tabs[0]: # VIZ
        st.markdown(f'<div style="text-align:center;">{render_authority_graph(st.session_state.entity, st.session_state.relations, st.session_state.social_links)}</div>', unsafe_allow_html=True)
        st.info("💡 L'orbite extérieure affiche vos signaux sociaux avec leurs couleurs officielles.")

    with tabs[1]: # IDENTITÉ
        e = st.session_state.entity
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### 🏛️ Données Légales")
            e.name = st.text_input("Raison Sociale", e.name)
            e.siren = st.text_input("SIREN", e.siren)
            e.siret = st.text_input("SIRET Siège", e.siret)
            e.address = st.text_input("Adresse", e.address)
            cx1, cx2 = st.columns(2)
            e.postal_code = cx1.text_input("CP", e.postal_code)
            e.city = cx2.text_input("Ville", e.city)
            e.ape = st.text_input("Code APE", e.ape)
        with c2:
            st.markdown("##### 🌐 Identifiants Mondiaux")
            e.qid = st.text_input("Wikidata QID", e.qid)
            e.website = st.text_input("URL Site Officiel", e.website)
            e.isni = st.text_input("Numéro ISNI", e.isni)
            e.ror = st.text_input("ROR ID", e.ror)
            e.lei = st.text_input("Code LEI", e.lei)
        st.session_state.entity = e

    with tabs[2]: # ECO
        st.markdown("##### 🏢 Filiales & Relations")
        with st.expander("➕ Déclarer manuellement une relation"):
            f1, f2 = st.columns(2)
            n = f1.text_input("Nom de l'entité")
            t_rel = f2.selectbox("Nature", ["subOrganization", "department", "brand", "member"])
            if st.button("Ajouter à la carte"):
                if n:
                    st.session_state.relations.append(Relation(qid="", name=n, schema_type=t_rel))
                    st.rerun()
        if st.session_state.relations:
            df = pd.DataFrame([{"QID": r.qid, "Nom": r.name, "Type": r.schema_type, "Inclure": r.include} for r in st.session_state.relations])
            edited = st.data_editor(df, hide_index=True, use_container_width=True)
            if st.button("Sauvegarder les relations"):
                st.session_state.relations = [Relation(qid=row["QID"], name=row["Nom"], schema_type=row["Type"], include=row["Inclure"]) for _, row in edited.iterrows()]
                st.rerun()

    with tabs[3]: # SOCIAL HUB
        st.markdown("##### 📱 Hub de Triangulation")
        sc1, sc2 = st.columns(2)
        # On itère sur les clés pour être sûr de tout voir
        networks = list(st.session_state.social_links.keys())
        for i, net in enumerate(networks):
            with (sc1 if i % 2 == 0 else sc2):
                st.session_state.social_links[net] = st.text_input(f"Lien {net.capitalize()}", st.session_state.social_links[net])
        
        if st.button("Mettre à jour le graphique"):
            st.rerun()

    with tabs[4]: # EXPORT
        exp = {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": e.name,
            "url": e.website,
        }
        # Identifiants
        ids = []
        if e.siren: ids.append({"@type": "PropertyValue", "propertyID": "SIREN", "value": e.siren})
        if e.siret: ids.append({"@type": "PropertyValue", "propertyID": "SIRET", "value": e.siret})
        if ids: exp["identifier"] = ids
        if e.lei: exp["leiCode"] = e.lei
        # SameAs
        s_as = [f"https://www.wikidata.org/wiki/{e.qid}" if e.qid else None]
        s_as.extend([v for v in st.session_state.social_links.values() if v])
        exp["sameAs"] = [x for x in s_as if x]
        # Relations
        rels = [r for r in st.session_state.relations if r.include]
        if rels: exp["subOrganization"] = [{"@type": r.schema_type, "name": r.name} for r in rels]

        st.json(exp)
        st.download_button("📥 Télécharger JSON-LD", json.dumps(exp, indent=2), "schema.json", "application/ld+json")
else:
    st.info("👈 Recherchez et fusionnez une entité pour générer la cartographie d'autorité.")