"""
🛡️ Architecte d'Autorité Sémantique v8.2 (DEBUG + FIX)
-------------------------------------------------------
CHANGELOG v8.2:
- ✅ FIX: Bug critique - la recherche Wikidata ne remplissait pas les champs
- ✅ NEW: Diagnostic réseau intégré (bouton "Test Connexions")
- ✅ FIX: Async/await mal géré avec Streamlit
- ✅ FIX: Session state entity reset intempestif
- ✅ NEW: Logs plus détaillés pour debug
- ✅ FIX: Parent Organization via SPARQL P749
"""

import streamlit as st
import requests  # Plus fiable que httpx avec Streamlit
import json
import time
import re
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any

# ============================================================================
# 1. CONFIGURATION
# ============================================================================
st.set_page_config(
    page_title="AAS v8.2 DEBUG",
    page_icon="🛡️",
    layout="wide"
)

# Session State - Initialisation PROPRE
if 'logs' not in st.session_state:
    st.session_state.logs = []
if 'entity' not in st.session_state:
    st.session_state.entity = None
if 'social_links' not in st.session_state:
    st.session_state.social_links = {k: '' for k in ['linkedin', 'twitter', 'facebook', 'instagram', 'youtube']}
if 'res_wiki' not in st.session_state:
    st.session_state.res_wiki = []
if 'res_insee' not in st.session_state:
    st.session_state.res_insee = []
if 'mistral_key' not in st.session_state:
    st.session_state.mistral_key = ''
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False


def add_log(msg: str, status: str = "info") -> None:
    """Log avec timestamp."""
    icons = {"info": "ℹ️", "success": "✅", "error": "❌", "warning": "⚠️", "debug": "🔧"}
    timestamp = time.strftime("%H:%M:%S")
    entry = f"{icons.get(status, '•')} [{timestamp}] {msg}"
    st.session_state.logs.append(entry)
    if len(st.session_state.logs) > 50:
        st.session_state.logs.pop(0)
    # Debug console
    print(entry)


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
    parent_org_siren: str = ""
    address_street: str = ""
    address_city: str = ""
    address_postal: str = ""

    def authority_score(self) -> int:
        score = 0
        if self.qid: score += 20
        if self.siren: score += 20
        if self.lei: score += 15
        if self.website: score += 15
        if self.parent_org_qid: score += 10
        if self.expertise_fr: score += 10
        if self.address_city: score += 10
        return min(score, 100)


# Initialiser entity SI None
if st.session_state.entity is None:
    st.session_state.entity = Entity()


# ============================================================================
# 3. WIKIDATA ENGINE (SYNCHRONE - plus fiable avec Streamlit)
# ============================================================================
class WikidataEngine:
    """Moteur Wikidata SYNCHRONE (requests au lieu de httpx async)."""
    
    HEADERS = {
        "User-Agent": "SemanticAuthorityArchitect/8.2 (https://votre-site.fr; contact@email.fr) Python/requests",
        "Accept": "application/json"
    }
    
    ACTION_API = "https://www.wikidata.org/w/api.php"
    SPARQL = "https://query.wikidata.org/sparql"
    
    @staticmethod
    def test_connection() -> Dict[str, Any]:
        """Test de connexion aux APIs."""
        results = {"action_api": False, "sparql": False, "errors": []}
        
        # Test Action API
        try:
            r = requests.get(
                WikidataEngine.ACTION_API,
                params={"action": "wbsearchentities", "search": "test", "language": "fr", "format": "json", "limit": 1},
                headers=WikidataEngine.HEADERS,
                timeout=10
            )
            if r.status_code == 200:
                results["action_api"] = True
                add_log(f"Action API OK (HTTP {r.status_code})", "success")
            else:
                results["errors"].append(f"Action API: HTTP {r.status_code}")
                add_log(f"Action API: HTTP {r.status_code}", "error")
        except Exception as e:
            results["errors"].append(f"Action API: {str(e)}")
            add_log(f"Action API error: {str(e)[:50]}", "error")
        
        # Test SPARQL
        try:
            test_query = "SELECT ?item WHERE { ?item wdt:P31 wd:Q5 } LIMIT 1"
            r = requests.get(
                WikidataEngine.SPARQL,
                params={"query": test_query, "format": "json"},
                headers=WikidataEngine.HEADERS,
                timeout=15
            )
            if r.status_code == 200:
                results["sparql"] = True
                add_log(f"SPARQL OK (HTTP {r.status_code})", "success")
            else:
                results["errors"].append(f"SPARQL: HTTP {r.status_code}")
                add_log(f"SPARQL: HTTP {r.status_code}", "error")
        except Exception as e:
            results["errors"].append(f"SPARQL: {str(e)}")
            add_log(f"SPARQL error: {str(e)[:50]}", "error")
        
        return results

    @staticmethod
    def search(query: str) -> List[Dict]:
        """Recherche Wikidata via Action API."""
        add_log(f"🔍 Wikidata search: '{query}'")
        
        try:
            params = {
                "action": "wbsearchentities",
                "search": query,
                "language": "fr",
                "uselang": "fr",
                "format": "json",
                "limit": 10,
                "type": "item"
            }
            
            response = requests.get(
                WikidataEngine.ACTION_API,
                params=params,
                headers=WikidataEngine.HEADERS,
                timeout=15
            )
            
            add_log(f"HTTP {response.status_code}", "debug")
            
            if response.status_code == 200:
                data = response.json()
                results = data.get('search', [])
                add_log(f"Wikidata: {len(results)} résultats trouvés", "success")
                
                output = []
                for item in results:
                    output.append({
                        'qid': item['id'],
                        'label': item.get('label', item['id']),
                        'desc': item.get('description', 'Pas de description')
                    })
                    add_log(f"  → {item['id']}: {item.get('label', '?')}", "debug")
                
                return output
            else:
                add_log(f"Wikidata HTTP Error: {response.status_code}", "error")
                add_log(f"Response: {response.text[:200]}", "debug")
                
        except requests.Timeout:
            add_log("Wikidata TIMEOUT (15s)", "error")
        except requests.ConnectionError as e:
            add_log(f"Wikidata CONNECTION ERROR: {str(e)[:50]}", "error")
        except Exception as e:
            add_log(f"Wikidata ERROR: {type(e).__name__}: {str(e)[:50]}", "error")
        
        return []

    @staticmethod
    def get_details(qid: str) -> Dict[str, Any]:
        """Récupère les détails complets via Action API + SPARQL."""
        add_log(f"📋 Getting details for {qid}")
        
        result = {
            "name_fr": "", "name_en": "", "desc_fr": "", "desc_en": "",
            "siren": "", "lei": "", "website": "",
            "parent_name": "", "parent_qid": ""
        }
        
        # 1. Action API pour labels/descriptions
        try:
            params = {
                "action": "wbgetentities",
                "ids": qid,
                "languages": "fr|en",
                "props": "labels|descriptions|claims",
                "format": "json"
            }
            
            response = requests.get(
                WikidataEngine.ACTION_API,
                params=params,
                headers=WikidataEngine.HEADERS,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                entity_data = data.get('entities', {}).get(qid, {})
                
                labels = entity_data.get('labels', {})
                descs = entity_data.get('descriptions', {})
                claims = entity_data.get('claims', {})
                
                result["name_fr"] = labels.get('fr', {}).get('value', '')
                result["name_en"] = labels.get('en', {}).get('value', '')
                result["desc_fr"] = descs.get('fr', {}).get('value', '')
                result["desc_en"] = descs.get('en', {}).get('value', '')
                
                # P1616 = SIREN
                if 'P1616' in claims:
                    siren_claims = claims['P1616']
                    if siren_claims:
                        result["siren"] = siren_claims[0].get('mainsnak', {}).get('datavalue', {}).get('value', '')
                        add_log(f"SIREN trouvé: {result['siren']}", "debug")
                
                # P1278 = LEI
                if 'P1278' in claims:
                    lei_claims = claims['P1278']
                    if lei_claims:
                        result["lei"] = lei_claims[0].get('mainsnak', {}).get('datavalue', {}).get('value', '')
                
                # P856 = Website
                if 'P856' in claims:
                    web_claims = claims['P856']
                    if web_claims:
                        result["website"] = web_claims[0].get('mainsnak', {}).get('datavalue', {}).get('value', '')
                
                # P749 = Parent Organization
                if 'P749' in claims:
                    parent_claims = claims['P749']
                    if parent_claims:
                        parent_id = parent_claims[0].get('mainsnak', {}).get('datavalue', {}).get('value', {}).get('id', '')
                        if parent_id:
                            result["parent_qid"] = parent_id
                            add_log(f"Parent QID trouvé: {parent_id}", "success")
                            # Récupérer le nom du parent
                            parent_data = WikidataEngine._get_label(parent_id)
                            result["parent_name"] = parent_data
                
                add_log(f"Action API: données récupérées pour {qid}", "success")
            else:
                add_log(f"Action API error: HTTP {response.status_code}", "error")
                
        except Exception as e:
            add_log(f"Action API exception: {str(e)[:50]}", "error")
        
        return result

    @staticmethod
    def _get_label(qid: str) -> str:
        """Récupère juste le label d'un QID."""
        try:
            params = {
                "action": "wbgetentities",
                "ids": qid,
                "languages": "fr|en",
                "props": "labels",
                "format": "json"
            }
            response = requests.get(
                WikidataEngine.ACTION_API,
                params=params,
                headers=WikidataEngine.HEADERS,
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                labels = data.get('entities', {}).get(qid, {}).get('labels', {})
                return labels.get('fr', {}).get('value', '') or labels.get('en', {}).get('value', '')
        except:
            pass
        return ""


# ============================================================================
# 4. INSEE ENGINE
# ============================================================================
class INSEEEngine:
    """API INSEE gratuite."""
    
    API_URL = "https://recherche-entreprises.api.gouv.fr/search"
    
    @staticmethod
    def search(query: str) -> List[Dict]:
        """Recherche entreprise."""
        add_log(f"🏛️ INSEE search: '{query}'")
        
        try:
            response = requests.get(
                INSEEEngine.API_URL,
                params={"q": query, "per_page": 10},
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                results = data.get('results', [])
                add_log(f"INSEE: {len(results)} entreprises", "success")
                
                output = []
                for item in results:
                    siege = item.get('siege', {})
                    output.append({
                        'siren': item.get('siren', ''),
                        'siret': siege.get('siret', ''),
                        'name': item.get('nom_complet', ''),
                        'legal_name': item.get('nom_raison_sociale', ''),
                        'naf': item.get('activite_principale', ''),
                        'address': siege.get('adresse', ''),
                        'city': siege.get('commune', ''),
                        'postal': siege.get('code_postal', ''),
                        'active': item.get('etat_administratif') == 'A'
                    })
                return output
            else:
                add_log(f"INSEE HTTP {response.status_code}", "error")
        except Exception as e:
            add_log(f"INSEE error: {str(e)[:50]}", "error")
        
        return []


# ============================================================================
# 5. MISTRAL ENGINE
# ============================================================================
class MistralEngine:
    """Enrichissement Mistral AI."""
    
    @staticmethod
    def optimize(api_key: str, entity: Entity) -> Optional[Dict]:
        """Génère descriptions + détecte parent."""
        if not api_key:
            add_log("Mistral: clé manquante", "error")
            return None
        
        add_log("🤖 Mistral: génération GEO...")
        
        prompt = f"""Expert SEO. Analyse cette entreprise:
NOM: {entity.name}
SIREN: {entity.siren or 'N/A'}
QID: {entity.qid or 'N/A'}

Génère en JSON STRICT:
{{"description_fr": "...", "description_en": "...", "expertise_fr": "A, B, C", "expertise_en": "X, Y, Z", "parent_org_name": "nom ou null", "parent_org_qid": "Qxxxxx ou null"}}"""

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
                result = json.loads(content)
                add_log("Mistral: OK", "success")
                return result
            else:
                add_log(f"Mistral HTTP {response.status_code}", "error")
        except Exception as e:
            add_log(f"Mistral error: {str(e)[:40]}", "error")
        
        return None


# ============================================================================
# 6. AUTHENTICATION
# ============================================================================
if not st.session_state.authenticated:
    st.title("🛡️ AAS v8.2 DEBUG")
    pwd = st.text_input("Mot de passe:", type="password")
    if st.button("Déverrouiller"):
        if pwd == "SEOTOOLS":
            st.session_state.authenticated = True
            st.rerun()
    st.stop()


# ============================================================================
# 7. SIDEBAR
# ============================================================================
with st.sidebar:
    st.header("⚙️ AAS v8.2")
    
    # Console Logs
    with st.expander("📟 Console DEBUG", expanded=True):
        log_area = st.container(height=200)
        with log_area:
            for log in reversed(st.session_state.logs[-20:]):
                st.caption(log)
    
    # Test de connexion
    st.divider()
    if st.button("🔌 Test Connexions API", use_container_width=True):
        with st.spinner("Test en cours..."):
            results = WikidataEngine.test_connection()
            if results["action_api"] and results["sparql"]:
                st.success("✅ Toutes les APIs sont OK!")
            else:
                st.error(f"❌ Erreurs: {', '.join(results['errors'])}")
    
    st.divider()
    st.session_state.mistral_key = st.text_input("Clé Mistral", st.session_state.mistral_key, type="password")
    
    st.divider()
    st.subheader("🔍 Recherche")
    
    search_source = st.radio("Source", ["Wikidata", "INSEE", "Les deux"], horizontal=True)
    search_query = st.text_input("Nom ou SIREN")
    
    if st.button("🔎 Rechercher", type="primary", use_container_width=True):
        if search_query:
            add_log(f"=== Nouvelle recherche: '{search_query}' ===", "info")
            
            if search_source in ["Wikidata", "Les deux"]:
                st.session_state.res_wiki = WikidataEngine.search(search_query)
            
            if search_source in ["INSEE", "Les deux"]:
                st.session_state.res_insee = INSEEEngine.search(search_query)
            
            st.rerun()
    
    # Résultats Wikidata
    if st.session_state.res_wiki:
        st.markdown("**🌐 Wikidata:**")
        for i, item in enumerate(st.session_state.res_wiki[:6]):
            btn_label = f"{item['qid']}: {item['label'][:25]}"
            if st.button(btn_label, key=f"w_{i}_{item['qid']}", use_container_width=True):
                add_log(f"Sélection: {item['qid']}", "info")
                
                # Récupérer les détails
                details = WikidataEngine.get_details(item['qid'])
                
                # Mettre à jour l'entity
                e = st.session_state.entity
                e.qid = item['qid']
                e.name = details['name_fr'] or item['label']
                e.name_en = details['name_en']
                e.description_fr = details['desc_fr']
                e.description_en = details['desc_en']
                e.siren = e.siren or details['siren']  # Ne pas écraser si déjà présent
                e.lei = details['lei']
                e.website = e.website or details['website']
                
                if details['parent_qid']:
                    e.parent_org_qid = details['parent_qid']
                    e.parent_org_name = details['parent_name']
                    add_log(f"Parent: {e.parent_org_name} ({e.parent_org_qid})", "success")
                
                add_log(f"Entity mise à jour: {e.name}", "success")
                st.rerun()
    
    # Résultats INSEE
    if st.session_state.res_insee:
        st.markdown("**🏛️ INSEE:**")
        for i, item in enumerate(st.session_state.res_insee[:6]):
            status = "🟢" if item.get('active', True) else "🔴"
            btn_label = f"{status} {item['name'][:25]}"
            if st.button(btn_label, key=f"i_{i}_{item['siren']}", use_container_width=True):
                e = st.session_state.entity
                e.name = e.name or item['name']
                e.legal_name = item.get('legal_name', '')
                e.siren = item['siren']
                e.siret = item.get('siret', '')
                e.naf = item.get('naf', '')
                e.address_street = item.get('address', '')
                e.address_city = item.get('city', '')
                e.address_postal = item.get('postal', '')
                add_log(f"INSEE chargé: {item['name']}", "success")
                st.rerun()


# ============================================================================
# 8. MAIN UI
# ============================================================================
st.title("🛡️ Architecte d'Autorité Sémantique v8.2")

e = st.session_state.entity

# Score
if e.name or e.qid or e.siren:
    col1, col2, col3 = st.columns(3)
    with col1:
        score = e.authority_score()
        color = "🟢" if score >= 70 else "🟡" if score >= 40 else "🔴"
        st.metric("Score", f"{color} {score}/100")
    with col2:
        st.metric("QID", e.qid or "—")
    with col3:
        st.metric("SIREN", e.siren or "—")

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
            e.siret = st.text_input("SIRET", e.siret)
        with col2:
            e.qid = st.text_input("QID Wikidata", e.qid)
            e.lei = st.text_input("LEI", e.lei)
            e.naf = st.text_input("NAF", e.naf)
            e.website = st.text_input("Site web", e.website)
        
        st.divider()
        e.address_street = st.text_input("Adresse", e.address_street)
        col1, col2 = st.columns(2)
        with col1:
            e.address_postal = st.text_input("CP", e.address_postal)
        with col2:
            e.address_city = st.text_input("Ville", e.address_city)
    
    with tabs[1]:
        st.subheader("🔗 Filiation (Parent Organization)")
        
        col1, col2 = st.columns(2)
        with col1:
            e.parent_org_name = st.text_input("Nom maison mère", e.parent_org_name)
        with col2:
            e.parent_org_qid = st.text_input("QID maison mère", e.parent_org_qid)
        
        if e.parent_org_qid:
            st.success(f"✅ Lié à: [{e.parent_org_name}](https://www.wikidata.org/wiki/{e.parent_org_qid})")
        elif e.qid:
            st.info("ℹ️ Aucun parent trouvé dans Wikidata. Utilisez Mistral pour détecter automatiquement.")
    
    with tabs[2]:
        if st.button("🪄 Auto-Optimize (Mistral)", type="primary"):
            if st.session_state.mistral_key:
                result = MistralEngine.optimize(st.session_state.mistral_key, e)
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
    
    with tabs[3]:
        # Build JSON-LD
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
        
        json_ld = {
            "@context": "https://schema.org",
            "@type": e.org_type,
            "name": e.name
        }
        
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
        if e.address_city:
            json_ld["address"] = {
                "@type": "PostalAddress",
                "streetAddress": e.address_street,
                "postalCode": e.address_postal,
                "addressLocality": e.address_city,
                "addressCountry": "FR"
            }
        if parent:
            json_ld["parentOrganization"] = parent
        
        st.json(json_ld)
        
        col1, col2 = st.columns(2)
        with col1:
            st.download_button("📄 JSON-LD", json.dumps(json_ld, indent=2, ensure_ascii=False), f"jsonld_{e.siren or 'export'}.json")
        with col2:
            config = {"entity": asdict(e), "social_links": st.session_state.social_links}
            st.download_button("💾 Config", json.dumps(config, indent=2, ensure_ascii=False), f"config_{e.siren or 'export'}.json")

else:
    st.info("👈 Recherchez une entreprise dans la sidebar")
    
    st.markdown("""
    ### 🐛 Mode DEBUG v8.2
    
    1. Cliquez sur **"Test Connexions API"** pour vérifier que Wikidata répond
    2. Regardez la **Console DEBUG** pour voir les erreurs en temps réel
    3. Le bouton recherche utilise maintenant `requests` (synchrone) au lieu de `httpx` (async)
    
    **Informations Boursorama (pour test):**
    - QID Wikidata: `Q2110465`
    - SIREN: `351058151`
    - Parent: Société Générale (`Q270618`)
    """)

st.divider()
st.caption("🛡️ AAS v8.2 DEBUG | Wikidata + INSEE | requests synchrone")
