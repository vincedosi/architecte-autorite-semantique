"""
🛡️ Architecte d'Autorité Sémantique v7.3 (Version Intégrale Audité)
------------------------------------------------------------------
- Persistance : Import/Export JSON en Sidebar (Fix global).
- Sécurité : Mot de passe (SEOTOOLS).
- GEO Optimizer : Mistral AI + Filiation (Parent Org) + Identifiants Trust.
- Visualisation : Moteur graphique 3-Orbites complet avec labels.
"""

import streamlit as st
import asyncio
import httpx
import pandas as pd
import json
import math
import time
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any

# ============================================================================
# 1. CONFIGURATION & MODELS
# ============================================================================
st.set_page_config(page_title="Architecte d'Autorité Sémantique", page_icon="🛡️", layout="wide")

@dataclass
class Entity:
    name: str = ""
    name_en: str = ""
    legal_name: str = ""
    description_fr: str = ""
    description_en: str = ""
    expertise_fr: str = ""
    expertise_en: str = ""
    qid: str = ""
    siren: str = ""
    siret: str = ""
    isni: str = ""
    ror: str = ""
    lei: str = ""
    address: str = ""
    city: str = ""
    postal_code: str = ""
    website: str = ""
    org_type: str = "Organization"
    parent_org_name: str = ""
    parent_org_wiki: str = ""

    def authority_score(self) -> int:
        score = 0
        if self.qid: score += 25
        if self.siren: score += 20
        if self.lei: score += 20
        if self.website: score += 15
        if self.isni or self.ror: score += 20
        return min(score, 100)

@dataclass
class Relation:
    qid: str = ""
    name: str = ""
    url: str = ""
    schema_type: str = "Organization"
    include: bool = True

# ============================================================================
# 2. AUTHENTIFICATION & SESSION
# ============================================================================
if 'authenticated' not in st.session_state: st.session_state.authenticated = False
if 'entity' not in st.session_state: st.session_state.entity = Entity()
if 'relations' not in st.session_state: st.session_state.relations = []
if 'social_links' not in st.session_state: 
    st.session_state.social_links = {k:'' for k in ['linkedin','twitter','facebook','instagram','youtube']}
if 'mistral_key' not in st.session_state: st.session_state.mistral_key = ""

def check_password():
    if st.session_state.authenticated: return True
    st.title("🛡️ Accès Restreint")
    pwd = st.text_input("Veuillez entrer le mot de passe :", type="password")
    if st.button("Se connecter"):
        if pwd == "SEOTOOLS":
            st.session_state.authenticated = True
            st.rerun()
        else: st.error("Mot de passe incorrect.")
    return False

if not check_password(): st.stop()

# ============================================================================
# 3. MOTEURS API & IA (MISTRAL)
# ============================================================================
class MistralEngine:
    @staticmethod
    async def optimize(api_key, entity):
        prompt = f"""Tu es un expert GEO. Analyse {entity.name} (SIREN: {entity.siren}).
        Génère ce JSON uniquement: {{"desc_fr": "...", "desc_en": "...", "expertise_fr": "A, B, C", "expertise_en": "D, E, F"}}"""
        async with httpx.AsyncClient() as client:
            try:
                r = await client.post("https://api.mistral.ai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": "mistral-small-latest", "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}},
                    timeout=25.0)
                return json.loads(r.json()['choices'][0]['message']['content']) if r.status_code == 200 else None
            except: return None

# ============================================================================
# 4. SIDEBAR (CONFIG & RECHERCHE)
# ============================================================================
with st.sidebar:
    st.header("🛡️ Configuration")
    
    # IMPORT JSON
    st.subheader("📥 Charger un Dossier")
    uploaded_file = st.file_uploader("Fichier Config .json", type="json", label_visibility="collapsed")
    if uploaded_file:
        try:
            data = json.load(uploaded_file)
            st.session_state.entity = Entity(**data['entity'])
            st.session_state.relations = [Relation(**r) for r in data.get('relations', [])]
            st.session_state.social_links.update(data.get('social_links', {}))
            st.success("Dossier chargé !")
            time.sleep(1)
            st.rerun()
        except: st.error("Format invalide.")

    st.divider()
    st.session_state.mistral_key = st.text_input("Clé Mistral AI", value=st.session_state.mistral_key, type="password")
    
    st.divider()
    st.subheader("🔍 Recherche & Fusion")
    q = st.text_input("Nom de l'organisation")
    if st.button("Lancer l'audit", use_container_width=True, type="primary") and q:
        try:
            res = httpx.get(f"https://recherche-entreprises.api.gouv.fr/search?q={q}&per_page=1").json()['results'][0]
            e = st.session_state.entity
            e.name, e.siren = res['nom_complet'], res['siren']
            s = res.get('siege', {})
            e.address, e.city, e.postal_code = s.get('adresse',''), s.get('libelle_commune',''), s.get('code_postal','')
            st.session_state.entity = e
            st.rerun()
        except: st.error("Non trouvé.")

    if st.button("🗑️ Reset Complet", use_container_width=True):
        st.session_state.entity = Entity()
        st.session_state.relations = []
        st.session_state.social_links = {k:'' for k in st.session_state.social_links}
        st.rerun()

# ============================================================================
# 5. GRAPH ENGINE (3 ORBITES COMPLET)
# ============================================================================
def render_authority_graph(entity, relations, socials):
    W, H = 850, 720
    CX, CY = W/2, H/2 - 20
    R_ID, R_REL, R_SOC = 180, 260, 330
    
    ids = [("Wikidata", entity.qid, "#22C55E", "W"), ("INSEE", entity.siren, "#F97316", "S"),
           ("ISNI", entity.isni, "#A855F7", "I"), ("ROR", entity.ror, "#EC4899", "R"),
           ("LEI", entity.lei, "#06B6D4", "L"), ("Web", entity.website, "#3B82F6", "W")]
    
    rel_active = [r for r in relations if r.include]
    cfg_soc = {'linkedin': ('#0077B5', 'In'), 'twitter': ('#1DA1F2', 'X'), 'facebook': ('#1877F2', 'Fb'), 'instagram': ('#E4405F', 'Ig'), 'youtube': ('#FF0000', 'Yt')}
    soc_active = [(n.capitalize(), cfg_soc.get(n, ('#64748B', 'S'))) for n, url in socials.items() if url and url.strip()]

    svg = f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="background:white; border-radius:20px;">'
    svg += '<defs><filter id="sh"><feDropShadow dx="0" dy="2" stdDeviation="3" flood-opacity="0.15"/></filter></defs>'
    
    # Orbites (lignes de fond)
    svg += f'<circle cx="{CX}" cy="{CY}" r="{R_ID}" fill="none" stroke="#F1F5F9" stroke-width="2" stroke-dasharray="10,5" />'
    if rel_active: svg += f'<circle cx="{CX}" cy="{CY}" r="{R_REL}" fill="none" stroke="#F1F5F9" stroke-width="2" stroke-dasharray="5,5" />'
    if soc_active: svg += f'<circle cx="{CX}" cy="{CY}" r="{R_SOC}" fill="none" stroke="#F1F5F9" stroke-width="1" stroke-dasharray="2,2" />'

    # Orbite 1 : IDs
    for i, (lab, val, col, ico) in enumerate(ids):
        angle = (2 * math.pi * i) / len(ids) - (math.pi / 2)
        x, y = CX + R_ID * math.cos(angle), CY + R_ID * math.sin(angle)
        svg += f'<circle cx="{x}" cy="{y}" r="34" fill="{col if val else "#F8FAFC"}" opacity="{1 if val else 0.4}" filter="url(#sh)" />'
        svg += f'<text x="{x}" y="{y+7}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="20" fill="{"white" if val else "#94A3B8"}">{ico}</text>'
        svg += f'<text x="{x}" y="{y+50}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="10" fill="#1E293B">{lab}</text>'

    # Orbite 2 : Ecosystème
    for i, r in enumerate(rel_active):
        angle = (2 * math.pi * i) / len(rel_active) - (math.pi / 2) + 0.2
        x, y = CX + R_REL * math.cos(angle), CY + R_REL * math.sin(angle)
        svg += f'<circle cx="{x}" cy="{y}" r="26" fill="#6366F1" filter="url(#sh)" />'
        svg += f'<text x="{x}" y="{y+40}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="9" fill="#4338CA">{r.name[:15]}</text>'

    # Orbite 3 : Social
    for i, (lab, (col, ico)) in enumerate(soc_active):
        angle = (2 * math.pi * i) / len(soc_active) - (math.pi / 2) - 0.2
        x, y = CX + R_SOC * math.cos(angle), CY + R_SOC * math.sin(angle)
        svg += f'<circle cx="{x}" cy="{y}" r="24" fill="{col}" filter="url(#sh)" />'
        svg += f'<text x="{x}" y="{y+6}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="13" fill="white">{ico}</text>'
        svg += f'<text x="{x}" y="{y+38}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="9" fill="#64748B">{lab}</text>'

    # Centre
    score = entity.authority_score()
    svg += f'<circle cx="{CX}" cy="{CY}" r="78" fill="navy" filter="url(#sh)" />'
    svg += f'<text x="{CX}" y="{CY+15}" text-anchor="middle" font-family="Arial" font-weight="bold" font-size="38" fill="white">{score}%</text>'
    svg += '</svg>'
    return svg

# ============================================================================
# 6. MAIN UI
# ============================================================================
st.title("🛡️ Architecte d'Autorité Sémantique")
e = st.session_state.entity

if e.name:
    tabs = st.tabs(["🎯 Carte", "🆔 Identité", "🪄 GEO Magic (Mistral)", "🏢 Écosystème", "📱 Social Hub", "💾 Export"])
    
    with tabs[0]:
        st.markdown(f'<div style="text-align:center;">{render_authority_graph(e, st.session_state.relations, st.session_state.social_links)}</div>', unsafe_allow_html=True)

    with tabs[1]:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### 🏛️ Légal")
            e.org_type = st.selectbox("Type Schema.org", ["Organization", "BankOrCreditUnion", "InsuranceAgency", "LocalBusiness"])
            e.name = st.text_input("Nom FR", e.name)
            e.legal_name = st.text_input("Raison Sociale", e.legal_name)
            e.siren = st.text_input("SIREN", e.siren)
            e.address = st.text_input("Adresse", e.address)
        with c2:
            st.markdown("##### 🌐 Sémantique")
            e.qid = st.text_input("Wikidata QID", e.qid)
            e.lei = st.text_input("Code LEI", e.lei)
            e.website = st.text_input("Site Web", e.website)
            e.isni = st.text_input("ISNI", e.isni)
            e.ror = st.text_input("ROR ID", e.ror)
        
        st.divider()
        st.markdown("##### 🔗 Filiation (Parent Organization)")
        e.parent_org_name = st.text_input("Nom de la maison mère", e.parent_org_name)
        e.parent_org_wiki = st.text_input("Wikidata de la maison mère", e.parent_org_wiki)
        st.session_state.entity = e

    with tabs[2]:
        st.markdown("### 🪄 Mistral AI GEO Optimizer")
        if st.button("Remplir les champs sémantiques", use_container_width=True):
            res = asyncio.run(MistralEngine.optimize(st.session_state.mistral_key, e))
            if res:
                e.description_fr, e.description_en = res['desc_fr'], res['desc_en']
                e.expertise_fr, e.expertise_en = res['expertise_fr'], res['expertise_en']
                st.rerun()
        c1, c2 = st.columns(2)
        e.description_fr = c1.text_area("Description FR", e.description_fr)
        e.description_en = c2.text_area("Description EN", e.description_en)
        e.expertise_fr = c1.text_input("KnowsAbout FR", e.expertise_fr)
        e.expertise_en = c2.text_input("KnowsAbout EN", e.expertise_en)

    with tabs[3]:
        with st.expander("➕ Ajouter une Filiale"):
            f1, f2 = st.columns(2)
            fn = f1.text_input("Nom")
            fu = f2.text_input("URL / Wiki")
            if st.button("Ajouter"):
                st.session_state.relations.append(Relation(name=fn, url=fu))
                st.rerun()
        if st.session_state.relations:
            df = pd.DataFrame([asdict(r) for r in st.session_state.relations])
            edited = st.data_editor(df, use_container_width=True, hide_index=True)
            if st.button("Sauvegarder"):
                st.session_state.relations = [Relation(**row) for row in edited.to_dict('records')]
                st.rerun()

    with tabs[4]:
        sc1, sc2 = st.columns(2)
        for i, net in enumerate(st.session_state.social_links.keys()):
            with (sc1 if i%2==0 else sc2):
                st.session_state.social_links[net] = st.text_input(f"Lien {net.capitalize()}", st.session_state.social_links[net])

    with tabs[5]:
        # JSON-LD SEO MASTER
        json_ld = {
            "@context": "https://schema.org",
            "@type": e.org_type,
            "@id": f"{e.website.rstrip('/')}/#organization" if e.website else None,
            "name": [{"@language": "fr", "@value": e.name}, {"@language": "en", "@value": e.name_en or e.name}],
            "legalName": e.legal_name or None,
            "url": e.website,
            "description": [{"@language": "fr", "@value": e.description_fr}, {"@language": "en", "@value": e.description_en}],
            "taxID": f"FR{e.siren}" if e.siren else None,
            "leiCode": e.lei or None,
            "identifier": [{"@type": "PropertyValue", "propertyID": "SIREN", "value": e.siren}] if e.siren else [],
            "sameAs": [f"https://www.wikidata.org/wiki/{e.qid}" if e.qid else None] + [v for v in st.session_state.social_links.values() if v],
            "parentOrganization": {"@type": e.org_type, "name": e.parent_org_name, "sameAs": e.parent_org_wiki} if e.parent_org_name else None,
            "knowsAbout": [{"@language": "fr", "@value": e.expertise_fr}, {"@language": "en", "@value": e.expertise_en}]
        }
        st.json(json_ld)
        # CONFIG EXPORT
        cfg = {"entity": asdict(e), "relations": [asdict(r) for r in st.session_state.relations], "social_links": st.session_state.social_links}
        st.download_button("💾 Sauvegarder Config", json.dumps(cfg, indent=2, ensure_ascii=False), f"config_{e.name}.json")
else:
    st.info("👈 Recherchez une entité ou importez une configuration en barre latérale.")
