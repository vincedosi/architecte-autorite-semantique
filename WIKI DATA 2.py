"""
🛡️ Architecte d'Autorité Sémantique v8.1 (INSEE + Wikidata Resilient)
----------------------------------------------------------------------
CHANGELOG v8.1:
- ✅ NEW: Intégration API INSEE (SIRENE) pour enrichissement FR
- ✅ NEW: Wikidata REST API (plus stable que Action API)
- ✅ NEW: Système de retry automatique avec backoff
- ✅ FIX: Gestion robuste des timeouts et erreurs réseau
- ✅ FIX: Parent Organization via P749 SPARQL
- ✅ IMPROVE: Logs détaillés pour debug
"""

import streamlit as st
import asyncio
import httpx
import json
import time
import re
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
from urllib.parse import quote

# ============================================================================
# 1. CONFIGURATION & INITIALISATION
# ============================================================================
st.set_page_config(
    page_title="AAS v8.1 - INSEE + Wikidata",
    page_icon="🛡️",
    layout="wide"
)

# Session State
DEFAULT_SESSION = {
    'logs': [],
    'authenticated': False,
    'entity': None,
    'social_links': {k: '' for k in ['linkedin', 'twitter', 'facebook', 'instagram', 'youtube']},
    'res_wiki': [],
    'res_insee': [],
    'mistral_key': '',
    'insee_token': ''
}

for key, default in DEFAULT_SESSION.items():
    if key not in st.session_state:
        st.session_state[key] = default


def add_log(msg: str, status: str = "info") -> None:
    """Ajoute un log avec timestamp et icône."""
    icons = {"info": "ℹ️", "success": "✅", "error": "❌", "warning": "⚠️", "debug": "🔧"}
    timestamp = time.strftime("%H:%M:%S")
    st.session_state.logs.append(f"{icons.get(status, '•')} [{timestamp}] {msg}")
    if len(st.session_state.logs) > 40:
        st.session_state.logs.pop(0)


# ============================================================================
# 2. DATA CLASSES
# ============================================================================
@dataclass
class Entity:
    """Entité organisationnelle avec identifiants multi-sources."""
    # Identité
    name: str = ""
    name_en: str = ""
    legal_name: str = ""  # Dénomination légale INSEE
    
    # Descriptions
    description_fr: str = ""
    description_en: str = ""
    expertise_fr: str = ""
    expertise_en: str = ""
    
    # Identifiants
    qid: str = ""           # Wikidata QID
    siren: str = ""         # INSEE SIREN (9 chiffres)
    siret: str = ""         # INSEE SIRET (14 chiffres)
    lei: str = ""           # LEI (20 caractères)
    naf: str = ""           # Code NAF/APE
    
    # Web
    website: str = ""
    
    # Schema.org
    org_type: str = "Organization"
    
    # Filiation
    parent_org_name: str = ""
    parent_org_qid: str = ""
    parent_org_siren: str = ""  # SIREN de la maison mère
    
    # Adresse (INSEE)
    address_street: str = ""
    address_city: str = ""
    address_postal: str = ""
    address_country: str = "FR"
    
    # Source tracking
    source_wikidata: bool = False
    source_insee: bool = False

    def authority_score(self) -> int:
        """Score d'autorité sémantique (0-100)."""
        score = 0
        if self.qid: score += 20
        if self.siren: score += 20
        if self.siret: score += 10
        if self.lei: score += 15
        if self.website: score += 10
        if self.expertise_fr: score += 10
        if self.parent_org_qid or self.parent_org_siren: score += 10
        if self.address_city: score += 5
        return min(score, 100)


if st.session_state.entity is None:
    st.session_state.entity = Entity()


# ============================================================================
# 3. HTTP CLIENT WITH RETRY
# ============================================================================
class ResilientClient:
    """Client HTTP avec retry automatique et backoff exponentiel."""
    
    @staticmethod
    async def get_with_retry(
        client: httpx.AsyncClient,
        url: str,
        params: dict = None,
        headers: dict = None,
        max_retries: int = 3,
        timeout: float = 15.0
    ) -> Optional[httpx.Response]:
        """GET avec retry et backoff."""
        
        for attempt in range(max_retries):
            try:
                response = await client.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=timeout
                )
                
                if response.status_code == 200:
                    return response
                elif response.status_code == 429:
                    # Rate limit - wait and retry
                    wait_time = 2 ** attempt
                    add_log(f"Rate limit (429), retry dans {wait_time}s...", "warning")
                    await asyncio.sleep(wait_time)
                elif response.status_code >= 500:
                    # Server error - retry
                    wait_time = 2 ** attempt
                    add_log(f"Erreur serveur ({response.status_code}), retry...", "warning")
                    await asyncio.sleep(wait_time)
                else:
                    add_log(f"HTTP {response.status_code}", "error")
                    return response
                    
            except httpx.TimeoutException:
                add_log(f"Timeout (tentative {attempt + 1}/{max_retries})", "warning")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
            except httpx.ConnectError:
                add_log(f"Connexion échouée (tentative {attempt + 1})", "warning")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
            except Exception as e:
                add_log(f"Erreur: {str(e)[:40]}", "error")
                break
        
        return None


# ============================================================================
# 4. WIKIDATA ENGINE (REST API + SPARQL)
# ============================================================================
class WikidataEngine:
    """Moteur Wikidata avec REST API (nouveau) et SPARQL."""
    
    HEADERS = {
        "User-Agent": "SemanticAuthorityBot/8.1 (https://votre-site.fr; contact@email.fr) Python/httpx",
        "Accept": "application/json"
    }
    
    # Endpoints
    ACTION_API = "https://www.wikidata.org/w/api.php"
    REST_API = "https://www.wikidata.org/w/rest.php/wikibase/v1"
    SPARQL = "https://query.wikidata.org/sparql"

    @staticmethod
    async def search(client: httpx.AsyncClient, query: str) -> List[Dict]:
        """Recherche via Action API (le plus fiable pour la recherche)."""
        add_log(f"🔍 Wikidata: recherche '{query}'")
        
        params = {
            "action": "wbsearchentities",
            "search": query,
            "language": "fr",
            "uselang": "fr",
            "format": "json",
            "limit": 10,
            "type": "item"
        }
        
        response = await ResilientClient.get_with_retry(
            client, WikidataEngine.ACTION_API, params, WikidataEngine.HEADERS
        )
        
        if response and response.status_code == 200:
            data = response.json()
            results = data.get('search', [])
            add_log(f"Wikidata: {len(results)} résultats", "success")
            
            return [{
                'qid': item['id'],
                'label': item.get('label', item['id']),
                'desc': item.get('description', '')
            } for item in results]
        
        add_log("Wikidata search failed", "error")
        return []

    @staticmethod
    async def get_entity_rest(client: httpx.AsyncClient, qid: str) -> Optional[Dict]:
        """Récupère une entité via le nouveau REST API (plus stable)."""
        add_log(f"📡 REST API: {qid}")
        
        url = f"{WikidataEngine.REST_API}/entities/items/{qid}"
        response = await ResilientClient.get_with_retry(
            client, url, headers=WikidataEngine.HEADERS, timeout=20.0
        )
        
        if response and response.status_code == 200:
            return response.json()
        return None

    @staticmethod
    async def get_details(client: httpx.AsyncClient, qid: str) -> Dict[str, Any]:
        """Récupère tous les détails d'une entité (REST + SPARQL)."""
        add_log(f"📋 Récupération complète: {qid}")
        
        result = {
            "name_fr": "", "name_en": "", "desc_fr": "", "desc_en": "",
            "siren": "", "lei": "", "website": "",
            "parent_name": "", "parent_qid": ""
        }
        
        # 1. REST API pour labels/descriptions (plus rapide)
        entity_data = await WikidataEngine.get_entity_rest(client, qid)
        
        if entity_data:
            labels = entity_data.get('labels', {})
            descs = entity_data.get('descriptions', {})
            
            result["name_fr"] = labels.get('fr', '')
            result["name_en"] = labels.get('en', '')
            result["desc_fr"] = descs.get('fr', '')
            result["desc_en"] = descs.get('en', '')
            
            # Extraire les statements pour SIREN/LEI/Website
            statements = entity_data.get('statements', {})
            
            # P1616 = SIREN
            if 'P1616' in statements:
                siren_data = statements['P1616']
                if siren_data and len(siren_data) > 0:
                    result["siren"] = siren_data[0].get('value', {}).get('content', '')
            
            # P1278 = LEI
            if 'P1278' in statements:
                lei_data = statements['P1278']
                if lei_data and len(lei_data) > 0:
                    result["lei"] = lei_data[0].get('value', {}).get('content', '')
            
            # P856 = Website
            if 'P856' in statements:
                web_data = statements['P856']
                if web_data and len(web_data) > 0:
                    result["website"] = web_data[0].get('value', {}).get('content', '')
            
            # P749 = Parent Organization
            if 'P749' in statements:
                parent_data = statements['P749']
                if parent_data and len(parent_data) > 0:
                    parent_id = parent_data[0].get('value', {}).get('content', '')
                    if parent_id:
                        result["parent_qid"] = parent_id
                        # Récupérer le nom du parent
                        parent_entity = await WikidataEngine.get_entity_rest(client, parent_id)
                        if parent_entity:
                            parent_labels = parent_entity.get('labels', {})
                            result["parent_name"] = parent_labels.get('fr', parent_labels.get('en', ''))
                            add_log(f"✅ Parent: {result['parent_name']} ({parent_id})", "success")
            
            add_log("REST API: données récupérées", "success")
        else:
            # Fallback sur SPARQL si REST échoue
            add_log("REST API failed, fallback SPARQL...", "warning")
            result = await WikidataEngine._get_details_sparql(client, qid)
        
        return result

    @staticmethod
    async def _get_details_sparql(client: httpx.AsyncClient, qid: str) -> Dict[str, Any]:
        """Fallback SPARQL pour les détails."""
        result = {
            "name_fr": "", "name_en": "", "desc_fr": "", "desc_en": "",
            "siren": "", "lei": "", "website": "",
            "parent_name": "", "parent_qid": ""
        }
        
        query = f"""
        SELECT ?itemLabel ?itemLabel_en ?itemDescription ?siren ?lei ?website ?parentOrg ?parentOrgLabel WHERE {{
            BIND(wd:{qid} AS ?item)
            OPTIONAL {{ ?item wdt:P1616 ?siren. }}
            OPTIONAL {{ ?item wdt:P1278 ?lei. }}
            OPTIONAL {{ ?item wdt:P856 ?website. }}
            OPTIONAL {{ ?item wdt:P749 ?parentOrg. }}
            SERVICE wikibase:label {{ 
                bd:serviceParam wikibase:language "fr,en".
                ?item rdfs:label ?itemLabel.
                ?item schema:description ?itemDescription.
                ?parentOrg rdfs:label ?parentOrgLabel.
            }}
            OPTIONAL {{
                ?item rdfs:label ?itemLabel_en.
                FILTER(LANG(?itemLabel_en) = "en")
            }}
        }} LIMIT 1
        """
        
        response = await ResilientClient.get_with_retry(
            client,
            WikidataEngine.SPARQL,
            params={'query': query, 'format': 'json'},
            headers=WikidataEngine.HEADERS,
            timeout=25.0
        )
        
        if response and response.status_code == 200:
            bindings = response.json().get('results', {}).get('bindings', [])
            if bindings:
                data = bindings[0]
                result["name_fr"] = data.get('itemLabel', {}).get('value', '')
                result["name_en"] = data.get('itemLabel_en', {}).get('value', '')
                result["desc_fr"] = data.get('itemDescription', {}).get('value', '')
                result["siren"] = data.get('siren', {}).get('value', '')
                result["lei"] = data.get('lei', {}).get('value', '')
                result["website"] = data.get('website', {}).get('value', '')
                
                parent_uri = data.get('parentOrg', {}).get('value', '')
                if parent_uri:
                    match = re.search(r'(Q\d+)$', parent_uri)
                    if match:
                        result["parent_qid"] = match.group(1)
                        result["parent_name"] = data.get('parentOrgLabel', {}).get('value', '')
                
                add_log("SPARQL: données récupérées", "success")
        
        return result


# ============================================================================
# 5. INSEE ENGINE (API SIRENE)
# ============================================================================
class INSEEEngine:
    """Moteur de recherche INSEE SIRENE."""
    
    # L'API publique INSEE ne nécessite pas de token pour les recherches basiques
    SIRENE_API = "https://api.insee.fr/entreprises/sirene/V3.11"
    RECHERCHE_API = "https://recherche-entreprises.api.gouv.fr"  # API gratuite!
    
    @staticmethod
    async def search_free(client: httpx.AsyncClient, query: str) -> List[Dict]:
        """Recherche via l'API gratuite recherche-entreprises.api.gouv.fr"""
        add_log(f"🏛️ INSEE: recherche '{query}'")
        
        url = f"{INSEEEngine.RECHERCHE_API}/search"
        params = {
            "q": query,
            "per_page": 10,
            "page": 1
        }
        
        response = await ResilientClient.get_with_retry(
            client, url, params, timeout=15.0
        )
        
        if response and response.status_code == 200:
            data = response.json()
            results = data.get('results', [])
            add_log(f"INSEE: {len(results)} entreprises trouvées", "success")
            
            return [{
                'siren': item.get('siren', ''),
                'siret': item.get('siege', {}).get('siret', ''),
                'name': item.get('nom_complet', ''),
                'legal_name': item.get('nom_raison_sociale', ''),
                'naf': item.get('activite_principale', ''),
                'naf_label': item.get('libelle_activite_principale', ''),
                'address': f"{item.get('siege', {}).get('adresse', '')}",
                'city': item.get('siege', {}).get('commune', ''),
                'postal': item.get('siege', {}).get('code_postal', ''),
                'date_creation': item.get('date_creation', ''),
                'is_active': item.get('etat_administratif') == 'A'
            } for item in results if item.get('siren')]
        
        add_log("INSEE search failed", "error")
        return []

    @staticmethod
    async def get_by_siren(client: httpx.AsyncClient, siren: str) -> Optional[Dict]:
        """Récupère les détails d'une entreprise par SIREN."""
        add_log(f"🏛️ INSEE: détails SIREN {siren}")
        
        # Nettoyer le SIREN
        siren = re.sub(r'\D', '', siren)[:9]
        
        if len(siren) != 9:
            add_log("SIREN invalide (doit avoir 9 chiffres)", "error")
            return None
        
        url = f"{INSEEEngine.RECHERCHE_API}/search"
        params = {"q": siren}
        
        response = await ResilientClient.get_with_retry(client, url, params)
        
        if response and response.status_code == 200:
            data = response.json()
            results = data.get('results', [])
            
            for item in results:
                if item.get('siren') == siren:
                    add_log(f"INSEE: trouvé {item.get('nom_complet', '')}", "success")
                    return {
                        'siren': item.get('siren', ''),
                        'siret': item.get('siege', {}).get('siret', ''),
                        'name': item.get('nom_complet', ''),
                        'legal_name': item.get('nom_raison_sociale', ''),
                        'naf': item.get('activite_principale', ''),
                        'naf_label': item.get('libelle_activite_principale', ''),
                        'address': item.get('siege', {}).get('adresse', ''),
                        'city': item.get('siege', {}).get('commune', ''),
                        'postal': item.get('siege', {}).get('code_postal', '')
                    }
        
        return None


# ============================================================================
# 6. MISTRAL ENGINE
# ============================================================================
class MistralEngine:
    """Enrichissement via Mistral AI."""
    
    API_URL = "https://api.mistral.ai/v1/chat/completions"
    
    @staticmethod
    async def optimize(api_key: str, entity: Entity) -> Optional[Dict]:
        """Génère descriptions GEO + détecte filiation."""
        if not api_key:
            add_log("Clé Mistral manquante", "error")
            return None
        
        add_log("🤖 Mistral AI: génération GEO...")
        
        prompt = f"""Expert SEO GEO. Analyse cette entreprise française:

NOM: {entity.name}
SIREN: {entity.siren or 'N/A'}
NAF: {entity.naf or 'N/A'}
TYPE: {entity.org_type}
SITE: {entity.website or 'N/A'}

GÉNÈRE en JSON:
1. description_fr: Description SEO optimisée (150-200 car)
2. description_en: English translation
3. expertise_fr: 3-5 domaines d'expertise (virgules)
4. expertise_en: English translation
5. parent_org_name: Maison mère (null si indépendant)
6. parent_org_qid: QID Wikidata du parent (null si inconnu)

RÉPONDS UNIQUEMENT EN JSON VALIDE:"""

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    MistralEngine.API_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": "mistral-small-latest",
                        "messages": [{"role": "user", "content": prompt}],
                        "response_format": {"type": "json_object"},
                        "temperature": 0.2
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    content = response.json()['choices'][0]['message']['content']
                    result = json.loads(content)
                    add_log("Mistral: génération OK", "success")
                    return result
                else:
                    add_log(f"Mistral HTTP {response.status_code}", "error")
                    
            except Exception as e:
                add_log(f"Mistral error: {str(e)[:40]}", "error")
        
        return None


# ============================================================================
# 7. AUTHENTICATION
# ============================================================================
if not st.session_state.authenticated:
    st.title("🛡️ AAS v8.1 - INSEE + Wikidata")
    st.markdown("### 🔐 Accès Restreint")
    
    pwd = st.text_input("Mot de passe:", type="password")
    if st.button("Déverrouiller", type="primary"):
        if pwd == "SEOTOOLS":
            st.session_state.authenticated = True
            add_log("Authentification réussie", "success")
            st.rerun()
        else:
            st.error("❌ Mot de passe incorrect")
    st.stop()


# ============================================================================
# 8. SIDEBAR
# ============================================================================
with st.sidebar:
    st.header("⚙️ AAS v8.1")
    
    # Logs
    with st.expander("📟 Console", expanded=True):
        log_container = st.container(height=180)
        with log_container:
            for log in reversed(st.session_state.logs[-12:]):
                st.caption(log)
    
    st.divider()
    
    # API Keys
    st.subheader("🔑 API Keys")
    st.session_state.mistral_key = st.text_input("Mistral API", value=st.session_state.mistral_key, type="password")
    
    st.divider()
    
    # Search Mode
    st.subheader("🔍 Recherche")
    search_mode = st.radio("Source", ["🏛️ INSEE (FR)", "🌐 Wikidata", "🔄 Les deux"], horizontal=True)
    search_query = st.text_input("Nom ou SIREN")
    
    if st.button("🔎 Rechercher", use_container_width=True, type="primary"):
        if search_query:
            async def run_search():
                async with httpx.AsyncClient() as client:
                    if "INSEE" in search_mode or "deux" in search_mode:
                        st.session_state.res_insee = await INSEEEngine.search_free(client, search_query)
                    if "Wikidata" in search_mode or "deux" in search_mode:
                        st.session_state.res_wiki = await WikidataEngine.search(client, search_query)
            asyncio.run(run_search())
            st.rerun()
    
    # INSEE Results
    if st.session_state.res_insee:
        st.markdown("**🏛️ Résultats INSEE:**")
        for item in st.session_state.res_insee[:5]:
            status = "🟢" if item.get('is_active', True) else "🔴"
            if st.button(f"{status} {item['name'][:30]}", key=f"insee_{item['siren']}", use_container_width=True):
                e = st.session_state.entity
                e.name = item['name']
                e.legal_name = item.get('legal_name', '')
                e.siren = item['siren']
                e.siret = item.get('siret', '')
                e.naf = item.get('naf', '')
                e.address_street = item.get('address', '')
                e.address_city = item.get('city', '')
                e.address_postal = item.get('postal', '')
                e.source_insee = True
                add_log(f"INSEE: {item['name']} chargé", "success")
                st.rerun()
    
    # Wikidata Results
    if st.session_state.res_wiki:
        st.markdown("**🌐 Résultats Wikidata:**")
        for item in st.session_state.res_wiki[:5]:
            if st.button(f"🔗 {item['label'][:25]}", key=f"wiki_{item['qid']}", use_container_width=True):
                async def fetch_wiki():
                    async with httpx.AsyncClient() as client:
                        details = await WikidataEngine.get_details(client, item['qid'])
                        e = st.session_state.entity
                        e.qid = item['qid']
                        e.name = e.name or details['name_fr'] or item['label']
                        e.name_en = details['name_en']
                        e.description_fr = details['desc_fr']
                        e.description_en = details['desc_en']
                        e.siren = e.siren or details['siren']
                        e.lei = details['lei']
                        e.website = e.website or details['website']
                        if details['parent_qid']:
                            e.parent_org_qid = details['parent_qid']
                            e.parent_org_name = details['parent_name']
                        e.source_wikidata = True
                asyncio.run(fetch_wiki())
                st.rerun()


# ============================================================================
# 9. MAIN UI
# ============================================================================
st.title("🛡️ Architecte d'Autorité Sémantique v8.1")

e = st.session_state.entity

# Score et sources
if e.name or e.qid or e.siren:
    col1, col2, col3 = st.columns(3)
    with col1:
        score = e.authority_score()
        color = "🟢" if score >= 70 else "🟡" if score >= 40 else "🔴"
        st.metric("Score Autorité", f"{color} {score}/100")
    with col2:
        sources = []
        if e.source_insee: sources.append("🏛️ INSEE")
        if e.source_wikidata: sources.append("🌐 Wikidata")
        st.metric("Sources", " + ".join(sources) if sources else "Aucune")
    with col3:
        ids = []
        if e.siren: ids.append("SIREN")
        if e.qid: ids.append("QID")
        if e.lei: ids.append("LEI")
        st.metric("Identifiants", ", ".join(ids) if ids else "Aucun")

# Tabs
if e.name or e.siren or e.qid:
    tabs = st.tabs(["🆔 Identité", "📍 Adresse", "🪄 GEO Magic", "📱 Social", "💾 JSON-LD"])
    
    # Tab 1: Identity
    with tabs[0]:
        col1, col2 = st.columns(2)
        with col1:
            e.org_type = st.selectbox("Type Schema.org", 
                ["Organization", "Corporation", "LocalBusiness", "BankOrCreditUnion", "InsuranceAgency"])
            e.name = st.text_input("Nom commercial", e.name)
            e.legal_name = st.text_input("Raison sociale", e.legal_name)
            e.siren = st.text_input("SIREN", e.siren)
            e.siret = st.text_input("SIRET", e.siret)
        with col2:
            e.qid = st.text_input("QID Wikidata", e.qid)
            e.lei = st.text_input("LEI", e.lei)
            e.naf = st.text_input("Code NAF", e.naf)
            e.website = st.text_input("Site web", e.website)
        
        st.divider()
        st.subheader("🔗 Filiation")
        col1, col2, col3 = st.columns(3)
        with col1:
            e.parent_org_name = st.text_input("Maison mère", e.parent_org_name)
        with col2:
            e.parent_org_qid = st.text_input("QID Parent", e.parent_org_qid)
        with col3:
            e.parent_org_siren = st.text_input("SIREN Parent", e.parent_org_siren)
    
    # Tab 2: Address
    with tabs[1]:
        e.address_street = st.text_input("Adresse", e.address_street)
        col1, col2 = st.columns(2)
        with col1:
            e.address_postal = st.text_input("Code postal", e.address_postal)
        with col2:
            e.address_city = st.text_input("Ville", e.address_city)
    
    # Tab 3: GEO Magic
    with tabs[2]:
        st.info("🪄 Génération automatique des descriptions SEO et détection de la filiation")
        
        if st.button("🪄 Auto-Optimize (Mistral)", type="primary", use_container_width=True):
            if st.session_state.mistral_key:
                result = asyncio.run(MistralEngine.optimize(st.session_state.mistral_key, e))
                if result:
                    e.description_fr = result.get('description_fr', e.description_fr)
                    e.description_en = result.get('description_en', e.description_en)
                    e.expertise_fr = result.get('expertise_fr', e.expertise_fr)
                    e.expertise_en = result.get('expertise_en', e.expertise_en)
                    if not e.parent_org_name and result.get('parent_org_name'):
                        e.parent_org_name = result['parent_org_name']
                    if not e.parent_org_qid and result.get('parent_org_qid'):
                        e.parent_org_qid = result['parent_org_qid']
                    st.rerun()
            else:
                st.error("Clé Mistral requise")
        
        e.description_fr = st.text_area("Description FR", e.description_fr, height=100)
        e.description_en = st.text_area("Description EN", e.description_en, height=100)
        e.expertise_fr = st.text_input("Expertise FR", e.expertise_fr)
        e.expertise_en = st.text_input("Expertise EN", e.expertise_en)
    
    # Tab 4: Social
    with tabs[3]:
        social = st.session_state.social_links
        col1, col2 = st.columns(2)
        with col1:
            social['linkedin'] = st.text_input("LinkedIn", social['linkedin'])
            social['twitter'] = st.text_input("Twitter/X", social['twitter'])
        with col2:
            social['facebook'] = st.text_input("Facebook", social['facebook'])
            social['youtube'] = st.text_input("YouTube", social['youtube'])
    
    # Tab 5: JSON-LD
    with tabs[4]:
        # Build sameAs
        same_as = []
        if e.qid: same_as.append(f"https://www.wikidata.org/wiki/{e.qid}")
        same_as.extend([v for v in st.session_state.social_links.values() if v])
        
        # Build identifiers
        identifiers = []
        if e.siren:
            identifiers.append({"@type": "PropertyValue", "propertyID": "SIREN", "value": e.siren})
        if e.siret:
            identifiers.append({"@type": "PropertyValue", "propertyID": "SIRET", "value": e.siret})
        if e.lei:
            identifiers.append({"@type": "PropertyValue", "propertyID": "LEI", "value": e.lei})
        
        # Build address
        address = None
        if e.address_city:
            address = {
                "@type": "PostalAddress",
                "streetAddress": e.address_street,
                "postalCode": e.address_postal,
                "addressLocality": e.address_city,
                "addressCountry": e.address_country
            }
        
        # Build parent
        parent = None
        if e.parent_org_name:
            parent = {"@type": "Organization", "name": e.parent_org_name}
            if e.parent_org_qid:
                parent["sameAs"] = f"https://www.wikidata.org/wiki/{e.parent_org_qid}"
        
        # Build knowsAbout
        knows = []
        if e.expertise_fr:
            for exp in e.expertise_fr.split(','):
                knows.append({"@language": "fr", "@value": exp.strip()})
        
        # Final JSON-LD
        json_ld = {
            "@context": "https://schema.org",
            "@type": e.org_type,
            "name": e.name
        }
        
        if e.legal_name and e.legal_name != e.name:
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
        if address:
            json_ld["address"] = address
        if knows:
            json_ld["knowsAbout"] = knows
        if parent:
            json_ld["parentOrganization"] = parent
        
        st.json(json_ld)
        
        col1, col2 = st.columns(2)
        with col1:
            st.download_button("📄 JSON-LD", json.dumps(json_ld, indent=2, ensure_ascii=False), 
                             f"jsonld_{e.siren or e.name}.json")
        with col2:
            config = {"entity": asdict(e), "social_links": st.session_state.social_links}
            st.download_button("💾 Config", json.dumps(config, indent=2, ensure_ascii=False),
                             f"config_{e.siren or e.name}.json")

else:
    st.info("👈 Recherchez une entreprise par nom ou SIREN dans la sidebar")
    st.markdown("""
    ### 🚀 v8.1 - Nouveautés
    
    - **🏛️ API INSEE** : Recherche gratuite via recherche-entreprises.api.gouv.fr
    - **🌐 Wikidata REST API** : Plus stable que l'ancienne Action API
    - **🔄 Retry automatique** : Gestion des erreurs réseau et rate limits
    - **🔗 Parent Organization** : Détection automatique (Wikidata P749 + Mistral)
    """)

st.divider()
st.caption("🛡️ AAS v8.1 | INSEE + Wikidata | GEO-Ready")
