"""
🛡️ Architecte d'Autorité Sémantique v9.0 (Streamlit Cloud Edition)
-------------------------------------------------------------------
VERSION OPTIMISÉE POUR STREAMLIT CLOUD:
- ✅ Cache @st.cache_data pour éviter les appels répétés
- ✅ Retry avec backoff exponentiel
- ✅ Headers compatibles Streamlit Cloud
- ✅ Timeouts adaptés
- ✅ Gestion robuste des erreurs
"""

import streamlit as st
import requests
import json
import time
import re
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any

# ============================================================================
# 1. CONFIG
# ============================================================================
st.set_page_config(page_title="AAS v9.0", page_icon="🛡️", layout="wide")

# Session State
if 'logs' not in st.session_state:
    st.session_state.logs = []
if 'entity' not in st.session_state:
    st.session_state.entity = None
if 'social_links' not in st.session_state:
    st.session_state.social_links = {k: '' for k in ['linkedin', 'twitter', 'facebook', 'instagram', 'youtube']}
if 'mistral_key' not in st.session_state:
    st.session_state.mistral_key = ''
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False


def add_log(msg: str, status: str = "info"):
    icons = {"info": "ℹ️", "success": "✅", "error": "❌", "warning": "⚠️"}
    entry = f"{icons.get(status, '•')} {time.strftime('%H:%M:%S')} {msg}"
    st.session_state.logs.append(entry)
    if len(st.session_state.logs) > 30:
        st.session_state.logs.pop(0)


# ============================================================================
# 2. DATA CLASS
# ============================================================================
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
    lei: str = ""
    naf: str = ""
    website: str = ""
    org_type: str = "Organization"
    parent_org_name: str = ""
    parent_org_qid: str = ""
    address: str = ""

    def score(self) -> int:
        s = 0
        if self.qid: s += 20
        if self.siren: s += 20
        if self.lei: s += 15
        if self.website: s += 15
        if self.parent_org_qid: s += 15
        if self.expertise_fr: s += 15
        return min(s, 100)


if st.session_state.entity is None:
    st.session_state.entity = Entity()


# ============================================================================
# 3. API FUNCTIONS WITH CACHE (STREAMLIT CLOUD OPTIMIZED)
# ============================================================================

@st.cache_data(ttl=300, show_spinner=False)
def wikidata_search(query: str) -> List[Dict]:
    """Recherche Wikidata avec cache 5 minutes."""
    
    url = "https://www.wikidata.org/w/api.php"
    params = {
        "action": "wbsearchentities",
        "search": query,
        "language": "fr",
        "uselang": "fr",
        "format": "json",
        "limit": 10,
        "type": "item"
    }
    # Headers importants pour Streamlit Cloud
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AAS-Bot/9.0; +https://github.com/)",
        "Accept": "application/json",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"
    }
    
    # Retry avec backoff
    for attempt in range(3):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=20)
            
            if response.status_code == 200:
                data = response.json()
                results = data.get('search', [])
                return [{
                    'qid': item['id'],
                    'label': item.get('label', item['id']),
                    'desc': item.get('description', '')
                } for item in results]
            
            elif response.status_code == 429:
                # Rate limit - attendre et réessayer
                time.sleep(2 ** attempt)
                continue
            else:
                return []
                
        except requests.Timeout:
            if attempt < 2:
                time.sleep(1)
                continue
            return []
        except Exception:
            return []
    
    return []


@st.cache_data(ttl=600, show_spinner=False)
def wikidata_get_entity(qid: str) -> Dict:
    """Récupère les détails d'une entité avec cache 10 minutes."""
    
    url = "https://www.wikidata.org/w/api.php"
    params = {
        "action": "wbgetentities",
        "ids": qid,
        "languages": "fr|en",
        "props": "labels|descriptions|claims",
        "format": "json"
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AAS-Bot/9.0; +https://github.com/)",
        "Accept": "application/json"
    }
    
    result = {
        "name_fr": "", "name_en": "", "desc_fr": "", "desc_en": "",
        "siren": "", "lei": "", "website": "",
        "parent_name": "", "parent_qid": ""
    }
    
    for attempt in range(3):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=20)
            
            if response.status_code == 200:
                data = response.json()
                entity = data.get('entities', {}).get(qid, {})
                
                labels = entity.get('labels', {})
                descs = entity.get('descriptions', {})
                claims = entity.get('claims', {})
                
                result["name_fr"] = labels.get('fr', {}).get('value', '')
                result["name_en"] = labels.get('en', {}).get('value', '')
                result["desc_fr"] = descs.get('fr', {}).get('value', '')
                result["desc_en"] = descs.get('en', {}).get('value', '')
                
                # P1616 = SIREN
                if 'P1616' in claims and claims['P1616']:
                    result["siren"] = claims['P1616'][0].get('mainsnak', {}).get('datavalue', {}).get('value', '')
                
                # P1278 = LEI
                if 'P1278' in claims and claims['P1278']:
                    result["lei"] = claims['P1278'][0].get('mainsnak', {}).get('datavalue', {}).get('value', '')
                
                # P856 = Website
                if 'P856' in claims and claims['P856']:
                    result["website"] = claims['P856'][0].get('mainsnak', {}).get('datavalue', {}).get('value', '')
                
                # P749 = Parent Organization
                if 'P749' in claims and claims['P749']:
                    parent_data = claims['P749'][0].get('mainsnak', {}).get('datavalue', {}).get('value', {})
                    if isinstance(parent_data, dict):
                        result["parent_qid"] = parent_data.get('id', '')
                    # Récupérer le nom du parent
                    if result["parent_qid"]:
                        result["parent_name"] = wikidata_get_label(result["parent_qid"])
                
                return result
                
            elif response.status_code == 429:
                time.sleep(2 ** attempt)
                continue
                
        except Exception:
            if attempt < 2:
                time.sleep(1)
                continue
    
    return result


@st.cache_data(ttl=600, show_spinner=False)
def wikidata_get_label(qid: str) -> str:
    """Récupère juste le label d'un QID."""
    try:
        url = "https://www.wikidata.org/w/api.php"
        params = {
            "action": "wbgetentities",
            "ids": qid,
            "languages": "fr|en",
            "props": "labels",
            "format": "json"
        }
        headers = {"User-Agent": "Mozilla/5.0 (compatible; AAS-Bot/9.0)"}
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            labels = data.get('entities', {}).get(qid, {}).get('labels', {})
            return labels.get('fr', {}).get('value', '') or labels.get('en', {}).get('value', '')
    except:
        pass
    return ""


@st.cache_data(ttl=300, show_spinner=False)
def insee_search(query: str) -> List[Dict]:
    """Recherche INSEE avec cache 5 minutes."""
    
    try:
        url = "https://recherche-entreprises.api.gouv.fr/search"
        params = {"q": query, "per_page": 10}
        
        response = requests.get(url, params=params, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            results = data.get('results', [])
            
            return [{
                'siren': item.get('siren', ''),
                'siret': item.get('siege', {}).get('siret', ''),
                'name': item.get('nom_complet', ''),
                'legal_name': item.get('nom_raison_sociale', ''),
                'naf': item.get('activite_principale', ''),
                'address': f"{item.get('siege', {}).get('adresse', '')} {item.get('siege', {}).get('code_postal', '')} {item.get('siege', {}).get('commune', '')}",
                'active': item.get('etat_administratif') == 'A'
            } for item in results]
    except:
        pass
    
    return []


def mistral_optimize(api_key: str, entity: Entity) -> Optional[Dict]:
    """Enrichissement Mistral."""
    if not api_key:
        return None
    
    prompt = f"""Expert SEO. Analyse: {entity.name} (SIREN: {entity.siren or 'N/A'})
Génère JSON: {{"description_fr": "...", "description_en": "...", "expertise_fr": "A, B", "expertise_en": "X, Y", "parent_org_name": "ou null", "parent_org_qid": "Qxxx ou null"}}"""

    try:
        response = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "mistral-small-latest",
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "temperature": 0.2
            },
            timeout=30
        )
        
        if response.status_code == 200:
            content = response.json()['choices'][0]['message']['content']
            return json.loads(content)
    except:
        pass
    
    return None


# ============================================================================
# 4. AUTH
# ============================================================================
if not st.session_state.authenticated:
    st.title("🛡️ AAS v9.0 - Streamlit Cloud")
    pwd = st.text_input("Mot de passe:", type="password")
    if st.button("Déverrouiller"):
        if pwd == "SEOTOOLS":
            st.session_state.authenticated = True
            st.rerun()
    st.stop()


# ============================================================================
# 5. SIDEBAR
# ============================================================================
with st.sidebar:
    st.header("⚙️ AAS v9.0")
    
    # Logs
    with st.expander("📟 Logs", expanded=False):
        for log in reversed(st.session_state.logs[-10:]):
            st.caption(log)
    
    st.divider()
    st.session_state.mistral_key = st.text_input("Clé Mistral", st.session_state.mistral_key, type="password")
    
    st.divider()
    st.subheader("🔍 Recherche")
    
    search_source = st.radio("Source", ["🌐 Wikidata", "🏛️ INSEE", "🔄 Les deux"], horizontal=True)
    search_query = st.text_input("Nom de l'organisation")
    
    col1, col2 = st.columns(2)
    with col1:
        search_btn = st.button("🔎 Chercher", type="primary", use_container_width=True)
    with col2:
        if st.button("🗑️ Reset", use_container_width=True):
            st.session_state.entity = Entity()
            st.cache_data.clear()
            st.rerun()
    
    # Recherche
    if search_btn and search_query:
        add_log(f"Recherche: {search_query}", "info")
        
        wiki_results = []
        insee_results = []
        
        if "Wikidata" in search_source or "deux" in search_source:
            with st.spinner("Wikidata..."):
                wiki_results = wikidata_search(search_query)
                if wiki_results:
                    add_log(f"Wikidata: {len(wiki_results)} résultats", "success")
                else:
                    add_log("Wikidata: aucun résultat", "warning")
        
        if "INSEE" in search_source or "deux" in search_source:
            with st.spinner("INSEE..."):
                insee_results = insee_search(search_query)
                if insee_results:
                    add_log(f"INSEE: {len(insee_results)} résultats", "success")
                else:
                    add_log("INSEE: aucun résultat", "warning")
        
        # Stocker les résultats dans session state
        st.session_state['wiki_results'] = wiki_results
        st.session_state['insee_results'] = insee_results
        st.rerun()
    
    # Afficher résultats Wikidata
    wiki_results = st.session_state.get('wiki_results', [])
    if wiki_results:
        st.markdown("**🌐 Wikidata:**")
        for i, item in enumerate(wiki_results[:6]):
            btn_key = f"wiki_{item['qid']}_{i}"
            if st.button(f"🔗 {item['qid']}: {item['label'][:20]}", key=btn_key, use_container_width=True):
                add_log(f"Sélection: {item['qid']}", "info")
                
                with st.spinner(f"Chargement {item['qid']}..."):
                    details = wikidata_get_entity(item['qid'])
                
                e = st.session_state.entity
                e.qid = item['qid']
                e.name = details['name_fr'] or item['label']
                e.name_en = details['name_en']
                e.description_fr = details['desc_fr']
                e.description_en = details['desc_en']
                e.siren = e.siren or details['siren']
                e.lei = details['lei']
                e.website = e.website or details['website']
                
                if details['parent_qid']:
                    e.parent_org_qid = details['parent_qid']
                    e.parent_org_name = details['parent_name']
                    add_log(f"Parent: {e.parent_org_name}", "success")
                
                add_log(f"Chargé: {e.name}", "success")
                st.rerun()
    
    # Afficher résultats INSEE
    insee_results = st.session_state.get('insee_results', [])
    if insee_results:
        st.markdown("**🏛️ INSEE:**")
        for i, item in enumerate(insee_results[:6]):
            status = "🟢" if item.get('active') else "🔴"
            btn_key = f"insee_{item['siren']}_{i}"
            if st.button(f"{status} {item['name'][:22]}", key=btn_key, use_container_width=True):
                e = st.session_state.entity
                e.name = e.name or item['name']
                e.legal_name = item.get('legal_name', '')
                e.siren = item['siren']
                e.siret = item.get('siret', '')
                e.naf = item.get('naf', '')
                e.address = item.get('address', '')
                add_log(f"INSEE: {item['name']}", "success")
                st.rerun()


# ============================================================================
# 6. MAIN
# ============================================================================
st.title("🛡️ Architecte d'Autorité Sémantique v9.0")

e = st.session_state.entity

# Métriques
if e.name or e.qid or e.siren:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        score = e.score()
        color = "🟢" if score >= 70 else "🟡" if score >= 40 else "🔴"
        st.metric("Score", f"{color} {score}/100")
    with col2:
        st.metric("QID", e.qid or "—")
    with col3:
        st.metric("SIREN", e.siren or "—")
    with col4:
        st.metric("Parent", e.parent_org_qid or "—")

# Tabs
if e.name or e.siren or e.qid:
    tabs = st.tabs(["🆔 Identité", "🔗 Filiation", "🪄 GEO Magic", "💾 JSON-LD"])
    
    with tabs[0]:
        col1, col2 = st.columns(2)
        with col1:
            e.org_type = st.selectbox("Type", ["Organization", "Corporation", "LocalBusiness", "BankOrCreditUnion"])
            e.name = st.text_input("Nom", e.name)
            e.legal_name = st.text_input("Raison sociale", e.legal_name)
            e.siren = st.text_input("SIREN", e.siren)
        with col2:
            e.qid = st.text_input("QID Wikidata", e.qid)
            e.lei = st.text_input("LEI", e.lei)
            e.website = st.text_input("Site web", e.website)
            e.address = st.text_input("Adresse", e.address)
    
    with tabs[1]:
        st.subheader("🔗 Filiation (Parent Organization)")
        col1, col2 = st.columns(2)
        with col1:
            e.parent_org_name = st.text_input("Nom maison mère", e.parent_org_name)
        with col2:
            e.parent_org_qid = st.text_input("QID maison mère", e.parent_org_qid)
        
        if e.parent_org_qid:
            st.success(f"✅ Lié à: [{e.parent_org_name}](https://www.wikidata.org/wiki/{e.parent_org_qid})")
    
    with tabs[2]:
        if st.button("🪄 Auto-Optimize (Mistral)", type="primary"):
            if st.session_state.mistral_key:
                with st.spinner("Mistral..."):
                    result = mistral_optimize(st.session_state.mistral_key, e)
                if result:
                    e.description_fr = result.get('description_fr', e.description_fr)
                    e.description_en = result.get('description_en', e.description_en)
                    e.expertise_fr = result.get('expertise_fr', e.expertise_fr)
                    e.expertise_en = result.get('expertise_en', e.expertise_en)
                    if not e.parent_org_name and result.get('parent_org_name'):
                        e.parent_org_name = result['parent_org_name']
                    if not e.parent_org_qid and result.get('parent_org_qid'):
                        e.parent_org_qid = result['parent_org_qid']
                    add_log("Mistral OK", "success")
                    st.rerun()
                else:
                    st.error("Mistral a échoué")
            else:
                st.error("Clé Mistral requise")
        
        e.description_fr = st.text_area("Description FR", e.description_fr, height=80)
        e.description_en = st.text_area("Description EN", e.description_en, height=80)
        e.expertise_fr = st.text_input("Expertise FR", e.expertise_fr)
    
    with tabs[3]:
        # JSON-LD
        same_as = []
        if e.qid:
            same_as.append(f"https://www.wikidata.org/wiki/{e.qid}")
        same_as.extend([v for v in st.session_state.social_links.values() if v])
        
        identifiers = []
        if e.siren:
            identifiers.append({"@type": "PropertyValue", "propertyID": "SIREN", "value": e.siren})
        if e.lei:
            identifiers.append({"@type": "PropertyValue", "propertyID": "LEI", "value": e.lei})
        
        parent = None
        if e.parent_org_name:
            parent = {"@type": "Organization", "name": e.parent_org_name}
            if e.parent_org_qid:
                parent["sameAs"] = f"https://www.wikidata.org/wiki/{e.parent_org_qid}"
        
        json_ld = {"@context": "https://schema.org", "@type": e.org_type, "name": e.name}
        
        if e.legal_name:
            json_ld["legalName"] = e.legal_name
        if e.website:
            json_ld["@id"] = f"{e.website.rstrip('/')}/#organization"
            json_ld["url"] = e.website
        if e.description_fr:
            json_ld["description"] = e.description_fr
        if e.siren:
            json_ld["taxID"] = f"FR{e.siren}"
        if identifiers:
            json_ld["identifier"] = identifiers
        if same_as:
            json_ld["sameAs"] = same_as
        if parent:
            json_ld["parentOrganization"] = parent
        
        st.json(json_ld)
        
        st.download_button(
            "💾 Télécharger JSON-LD",
            json.dumps(json_ld, indent=2, ensure_ascii=False),
            f"jsonld_{e.siren or 'export'}.json",
            mime="application/json"
        )

else:
    st.info("👈 Recherchez une entreprise dans la sidebar")
    
    st.markdown("""
    ### ☁️ Version Streamlit Cloud v9.0
    
    **Optimisations:**
    - 🔄 Cache automatique (évite les appels répétés)
    - ⏱️ Retry avec backoff exponentiel
    - 🌐 Headers compatibles cloud
    
    **Test rapide:** Cherchez "Boursorama" ou "IKEA"
    """)

st.divider()
st.caption("🛡️ AAS v9.0 | Streamlit Cloud Edition | Wikidata + INSEE")
