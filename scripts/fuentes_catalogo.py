"""Catálogo de fuentes de «The Daily Iván»: qué se lee cada mañana y por qué.

CRITERIOS DE ENTRADA (al menos uno, y siempre trayectoria y redacción identificable):
  · Medios con datos independientes de credibilidad en España: Digital News Report España (Reuters Institute y
    Universidad de Navarra), que mide la confianza de los lectores en cada marca.
  · Certificación Journalism Trust Initiative (Reporteros Sin Fronteras): elDiario.es fue de los tres primeros
    medios españoles certificados (junio de 2025).
  · Verificadores firmantes del código de principios de la IFCN (Newtral, Maldita.es).
  · Agencias de noticias y servicios públicos de radiotelevisión.
  · Cabeceras de referencia internacional y de su sector (prensa económica, defensa, clima, vivienda), con
    redacción propia y largo recorrido.
  · Fuentes oficiales y primarias: boletines, bancos centrales, estadísticas, reguladores, tribunales, gobiernos y
    organismos internacionales. Son la fuente preferente siempre que existan.

EXCLUSIONES: medios con la peor credibilidad medida y resoluciones judiciales por publicar informaciones sin base
(ver EXCLUIDOS), webs de bulos o hiperpartidistas, agregadores, prensa del corazón y contenidos sin firma ni
redacción identificable. La capa «radar» (Google News) recoge miles de medios solo para medir qué se está
contando; nunca se cita como fuente y su cobertura no cuenta en «Cobertura».

CAMPOS: id, nombre, tipo, bloques, línea (orientación editorial habitual, solo para equilibrar), dominio, url
(canal RSS directo) o site (búsqueda de Google News restringida a ese sitio, cuando el medio no publica RSS o lo
bloquea), y opcionalmente horas (ventana de antigüedad) y max (titulares que se guardan).

TIPOS: generalista y agencia (cuentan en «Cobertura» como generalistas), especializado y analisis (cuentan aparte
como especializados), verificador, oficial y radar.

USO: python3 scripts/fuentes_catalogo.py [bloque] imprime los dominios de referencia (del bloque o todos), para
restringir las búsquedas web a medios del catálogo.
"""

BLOQUES = ["mercados", "inversion", "geopolitica", "espana", "internacional", "vivienda", "naturaleza"]
GENERALISTAS = {"generalista", "agencia"}
ESPECIALIZADOS = {"especializado", "analisis"}


def F(id, nombre, tipo, bloques, dominio, url=None, site=None, linea="", horas=None, max=None, idioma="es", medio=None):
    """medio: cabecera a la que pertenece (las secciones de un mismo medio cuentan una sola vez en «Cobertura»)."""
    return {"id": id, "nombre": nombre, "tipo": tipo, "bloques": bloques, "dominio": dominio, "url": url,
            "site": site, "linea": linea, "horas": horas, "max": max, "idioma": idioma, "medio": medio or nombre}


ES_GEN = ["espana", "internacional"]
INT_GEN = ["internacional", "geopolitica"]
ECO = ["mercados", "inversion"]

FUENTES = [
    # ── España · generalistas (todas las líneas editoriales) ──────────────────────────────────────────────
    F("elpais", "El País", "generalista", ES_GEN, "elpais.com", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada", linea="centroizquierda"),
    F("eldiario", "elDiario.es", "generalista", ES_GEN, "eldiario.es", "https://www.eldiario.es/rss/", linea="izquierda"),
    F("infolibre", "infoLibre", "generalista", ES_GEN, "infolibre.es", ["https://www.infolibre.es/rss", "https://www.infolibre.es/rss/"], linea="izquierda"),
    F("ser", "Cadena SER", "generalista", ES_GEN, "cadenaser.com", "https://cadenaser.com/arc/outboundfeeds/rss/?outputType=xml", linea="centroizquierda", max=40),
    F("elperiodico", "El Periódico", "generalista", ES_GEN, "elperiodico.com", site="elperiodico.com", linea="centroizquierda"),
    F("elmundo", "El Mundo", "generalista", ES_GEN, "elmundo.es", "https://e00-elmundo.uecdn.es/rss/portada.xml", linea="centroderecha"),
    F("abc", "ABC", "generalista", ES_GEN, "abc.es", "https://www.abc.es/rss/2.0/portada/", linea="derecha"),
    F("elespanol", "El Español", "generalista", ES_GEN, "elespanol.com", "https://www.elespanol.com/rss/", linea="centroderecha"),
    F("larazon", "La Razón", "generalista", ES_GEN, "larazon.es", site="larazon.es", linea="derecha"),
    F("cope", "COPE", "generalista", ES_GEN, "cope.es", site="cope.es", linea="derecha"),
    F("elconfidencial", "El Confidencial", "generalista", ES_GEN, "elconfidencial.com", "https://rss.elconfidencial.com/espana/", linea="centro"),
    F("lavanguardia", "La Vanguardia", "generalista", ES_GEN, "lavanguardia.com", "https://www.lavanguardia.com/rss/home.xml", linea="centro"),
    F("20minutos", "20minutos", "generalista", ES_GEN, "20minutos.es", "https://www.20minutos.es/rss/", linea="centro"),
    F("ondacero", "Onda Cero", "generalista", ES_GEN, "ondacero.es", site="ondacero.es", linea="centro"),
    F("antena3", "Antena 3 Noticias", "generalista", ES_GEN, "antena3.com", "https://www.antena3.com/noticias/rss/4013050.xml", linea="centro"),
    F("rtve", "RTVE", "generalista", ES_GEN, "rtve.es", site="rtve.es/noticias", linea="publico"),  # su RSS dejó de actualizarse en 2022
    F("europapress", "Europa Press", "agencia", ES_GEN, "europapress.es", "https://www.europapress.es/rss/rss.aspx", linea="agencia"),
    F("efe", "Agencia EFE", "agencia", ES_GEN, "efe.com", site="efe.com", linea="agencia"),
    # Verificadores (IFCN)
    F("newtral", "Newtral", "verificador", ["espana"], "newtral.es", "https://www.newtral.es/feed/", linea="verificacion"),
    F("maldita", "Maldita.es", "verificador", ["espana"], "maldita.es", "https://maldita.es/feed/", linea="verificacion"),

    # ── Internacional · agencias y cabeceras de referencia ───────────────────────────────────────────────
    F("reuters", "Reuters", "agencia", INT_GEN + ECO, "reuters.com", site="reuters.com", linea="agencia", idioma="en", max=30),
    F("ap", "Associated Press", "agencia", INT_GEN, "apnews.com", site="apnews.com", linea="agencia", idioma="en"),
    F("bbc", "BBC News (mundo)", "generalista", INT_GEN, "bbc.co.uk", "https://feeds.bbci.co.uk/news/world/rss.xml", linea="publico", idioma="en", medio="BBC"),
    F("bbcmundo", "BBC Mundo", "generalista", INT_GEN, "bbc.com", "https://feeds.bbci.co.uk/mundo/rss.xml", linea="publico", medio="BBC"),
    F("guardian", "The Guardian", "generalista", INT_GEN, "theguardian.com", "https://www.theguardian.com/world/rss", linea="centroizquierda", idioma="en"),
    F("nyt", "The New York Times", "generalista", INT_GEN, "nytimes.com", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", linea="centroizquierda", idioma="en"),
    F("wsj", "The Wall Street Journal", "generalista", INT_GEN + ECO, "wsj.com", site="wsj.com", linea="centroderecha", idioma="en"),  # su RSS no se actualiza desde 2025
    F("economist", "The Economist", "generalista", INT_GEN, "economist.com", "https://www.economist.com/international/rss.xml", linea="liberal", idioma="en", horas=96),
    F("politico", "Politico Europe", "generalista", INT_GEN, "politico.eu", "https://www.politico.eu/feed/", linea="centro", idioma="en"),
    F("npr", "NPR", "generalista", INT_GEN, "npr.org", "https://feeds.npr.org/1004/rss.xml", linea="publico", idioma="en"),
    F("lemonde", "Le Monde", "generalista", INT_GEN, "lemonde.fr", "https://www.lemonde.fr/rss/une.xml", linea="centroizquierda", idioma="fr"),
    F("spiegel", "Der Spiegel", "generalista", INT_GEN, "spiegel.de", "https://www.spiegel.de/international/index.rss", linea="centroizquierda", idioma="en"),
    F("faz", "Frankfurter Allgemeine", "generalista", INT_GEN, "faz.net", "https://www.faz.net/rss/aktuell/politik/", linea="centroderecha", idioma="de"),
    F("corriere", "Corriere della Sera", "generalista", INT_GEN, "corriere.it", site="corriere.it", linea="centro", idioma="it"),
    F("dw", "DW en español", "generalista", INT_GEN, "dw.com", "https://rss.dw.com/xml/rss-sp-all", linea="publico"),
    F("france24", "France 24 en español", "generalista", INT_GEN, "france24.com", "https://www.france24.com/es/rss", linea="publico"),
    F("euronews", "Euronews en español", "generalista", INT_GEN, "euronews.com", "https://es.euronews.com/rss", linea="centro"),
    F("aljazeera", "Al Jazeera", "generalista", INT_GEN, "aljazeera.com", "https://www.aljazeera.com/xml/rss/all.xml", linea="centro", idioma="en"),
    F("elpais_am", "El País América", "generalista", ["internacional"], "elpais.com", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/america/portada", linea="centroizquierda", medio="El País"),
    F("lanacion", "La Nación (Argentina)", "generalista", ["internacional"], "lanacion.com.ar", "https://www.lanacion.com.ar/arc/outboundfeeds/rss/?outputType=xml", linea="centroderecha"),
    F("eluniversal", "El Universal (México)", "generalista", ["internacional"], "eluniversal.com.mx", "https://www.eluniversal.com.mx/arc/outboundfeeds/rss/?outputType=xml", linea="centro"),
    F("folha", "Folha de S.Paulo", "generalista", ["internacional"], "folha.uol.com.br", "https://feeds.folha.uol.com.br/mundo/rss091.xml", linea="centro", idioma="pt"),
    F("scmp", "South China Morning Post", "generalista", INT_GEN, "scmp.com", "https://www.scmp.com/rss/91/feed", linea="centro", idioma="en"),
    F("japantimes", "The Japan Times", "generalista", ["internacional"], "japantimes.co.jp", "https://www.japantimes.co.jp/feed/", linea="centro", idioma="en"),
    F("nhk", "NHK World", "generalista", ["internacional"], "nhk.or.jp", site="www3.nhk.or.jp/nhkworld", linea="publico", idioma="en"),

    # ── Economía, mercados e inversión ────────────────────────────────────────────────────────────────────
    F("expansion", "Expansión", "especializado", ECO + ["espana"], "expansion.com", "https://e00-expansion.uecdn.es/rss/portada.xml"),
    F("expansion_merc", "Expansión (mercados)", "especializado", ECO, "expansion.com", "https://e00-expansion.uecdn.es/rss/mercados.xml", medio="Expansión"),
    F("cincodias", "Cinco Días", "especializado", ECO + ["espana"], "cincodias.elpais.com", "https://feeds.elpais.com/mrss-s/pages/ep/site/cincodias.elpais.com/portada"),
    F("eleconomista", "elEconomista", "especializado", ECO, "eleconomista.es", site="eleconomista.es"),
    F("ft", "Financial Times", "especializado", ECO + ["internacional"], "ft.com", "https://www.ft.com/rss/home", idioma="en"),
    F("bloomberg", "Bloomberg", "especializado", ECO, "bloomberg.com", "https://feeds.bloomberg.com/markets/news.rss", idioma="en"),
    F("bloomberglinea", "Bloomberg Línea", "especializado", ECO, "bloomberglinea.com", "https://www.bloomberglinea.com/arc/outboundfeeds/rss/?outputType=xml"),
    F("cnbc", "CNBC", "especializado", ECO, "cnbc.com", "https://www.cnbc.com/id/100003114/device/rss/rss.html", idioma="en"),
    F("cnbc_inv", "CNBC (inversión)", "especializado", ["inversion"], "cnbc.com", "https://www.cnbc.com/id/15839069/device/rss/rss.html", idioma="en", medio="CNBC"),
    F("cnbc_res", "CNBC (resultados)", "especializado", ["inversion"], "cnbc.com", "https://www.cnbc.com/id/15839135/device/rss/rss.html", idioma="en", medio="CNBC"),
    F("marketwatch", "MarketWatch", "especializado", ECO, "marketwatch.com", "https://feeds.content.dowjones.io/public/rss/mw_topstories", idioma="en"),
    F("economist_fin", "The Economist (finanzas)", "especializado", ECO, "economist.com", "https://www.economist.com/finance-and-economics/rss.xml", idioma="en", horas=96, medio="The Economist"),
    F("kitco", "Kitco (metales preciosos)", "especializado", ECO, "kitco.com", site="kitco.com", idioma="en"),
    F("wgc", "World Gold Council", "analisis", ECO, "gold.org", site="gold.org", idioma="en", horas=168),
    F("coindesk", "CoinDesk", "especializado", ECO, "coindesk.com", "https://www.coindesk.com/arc/outboundfeeds/rss/", idioma="en"),

    # ── Geopolítica y defensa ─────────────────────────────────────────────────────────────────────────────
    F("defensenews", "Defense News", "especializado", ["geopolitica"], "defensenews.com", "https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml", idioma="en"),
    F("breakingdefense", "Breaking Defense", "especializado", ["geopolitica"], "breakingdefense.com", "https://breakingdefense.com/feed/", idioma="en"),
    F("infodefensa", "Infodefensa", "especializado", ["geopolitica"], "infodefensa.com", site="infodefensa.com"),
    F("kyivindependent", "The Kyiv Independent", "especializado", ["geopolitica"], "kyivindependent.com", site="kyivindependent.com", idioma="en"),
    F("meduza", "Meduza", "especializado", ["geopolitica"], "meduza.io", "https://meduza.io/rss/en/all", idioma="en"),
    F("timesofisrael", "The Times of Israel", "especializado", ["geopolitica"], "timesofisrael.com", site="timesofisrael.com", idioma="en"),
    F("almonitor", "Al-Monitor", "especializado", ["geopolitica"], "al-monitor.com", "https://www.al-monitor.com/rss", idioma="en"),
    F("foreignpolicy", "Foreign Policy", "analisis", ["geopolitica"], "foreignpolicy.com", "https://foreignpolicy.com/feed/", idioma="en", horas=72),
    F("crisisgroup", "International Crisis Group", "analisis", ["geopolitica"], "crisisgroup.org", "https://www.crisisgroup.org/rss.xml", idioma="en", horas=168),
    F("elcano", "Real Instituto Elcano", "analisis", ["geopolitica"], "realinstitutoelcano.org", site="realinstitutoelcano.org", horas=168),

    # ── Vivienda, empleo y Madrid ─────────────────────────────────────────────────────────────────────────
    F("idealista", "idealista/news", "especializado", ["vivienda"], "idealista.com", "https://www.idealista.com/news/rss/v2/latest-news.xml"),
    F("expansion_inmo", "Expansión (inmobiliario)", "especializado", ["vivienda"], "expansion.com", "https://e00-expansion.uecdn.es/rss/inmobiliario.xml", medio="Expansión"),
    F("elconfi_viv", "El Confidencial (vivienda)", "especializado", ["vivienda"], "elconfidencial.com", "https://rss.elconfidencial.com/vivienda/", horas=72, medio="El Confidencial"),
    F("elpais_madrid", "El País (Madrid)", "generalista", ["vivienda", "espana"], "elpais.com", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/espana/subsection/madrid", linea="centroizquierda", medio="El País"),
    F("elmundo_madrid", "El Mundo (Madrid)", "generalista", ["vivienda", "espana"], "elmundo.es", "https://e00-elmundo.uecdn.es/rss/madrid.xml", linea="centroderecha", medio="El Mundo"),
    F("telemadrid", "Telemadrid", "generalista", ["vivienda", "espana"], "telemadrid.es", site="telemadrid.es", linea="publico"),

    # ── Naturaleza y clima ────────────────────────────────────────────────────────────────────────────────
    F("efeverde", "EFEverde", "especializado", ["naturaleza"], "efeverde.com", "https://efeverde.com/feed/"),
    F("elpais_clima", "El País (clima y medio ambiente)", "especializado", ["naturaleza"], "elpais.com", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/clima-y-medio-ambiente/portada", medio="El País"),
    F("carbonbrief", "Carbon Brief", "especializado", ["naturaleza"], "carbonbrief.org", "https://www.carbonbrief.org/feed/", idioma="en", horas=72),
    F("guardian_env", "The Guardian (medio ambiente)", "especializado", ["naturaleza"], "theguardian.com", "https://www.theguardian.com/environment/rss", idioma="en", medio="The Guardian"),
    F("insideclimate", "Inside Climate News", "especializado", ["naturaleza"], "insideclimatenews.org", "https://insideclimatenews.org/feed/", idioma="en", horas=72),

    # ── Fuentes oficiales y primarias ─────────────────────────────────────────────────────────────────────
    # España
    F("moncloa", "La Moncloa (notas de prensa)", "oficial", ["espana"], "lamoncloa.gob.es", "https://www.lamoncloa.gob.es/Paginas/rss.aspx", site="lamoncloa.gob.es", horas=48),
    F("congreso", "Congreso de los Diputados", "oficial", ["espana"], "congreso.es", site="congreso.es", horas=48),
    F("cgpj", "Poder Judicial (CGPJ y tribunales)", "oficial", ["espana"], "poderjudicial.es", site="poderjudicial.es", horas=48),
    F("tc", "Tribunal Constitucional", "oficial", ["espana"], "tribunalconstitucional.es", site="tribunalconstitucional.es", horas=168),
    F("ine", "INE", "oficial", ["mercados", "espana", "vivienda"], "ine.es", site="ine.es", horas=48),
    F("bde", "Banco de España", "oficial", ECO, "bde.es", "https://www.bde.es/wbe/es/inicio/rss/rss-noticias/", horas=72),
    F("cnmv", "CNMV", "oficial", ECO, "cnmv.es", site="cnmv.es", horas=72),
    F("defensa", "Ministerio de Defensa", "oficial", ["geopolitica"], "defensa.gob.es", site="defensa.gob.es", horas=72),
    F("exteriores", "Ministerio de Asuntos Exteriores", "oficial", ["geopolitica", "internacional"], "exteriores.gob.es", site="exteriores.gob.es", horas=72),
    F("mivau", "Ministerio de Vivienda", "oficial", ["vivienda"], "mivau.gob.es", site="mivau.gob.es", horas=96),
    F("trabajo", "Ministerio de Trabajo", "oficial", ["vivienda"], "trabajo.gob.es", site="trabajo.gob.es", horas=168),
    F("miteco", "Ministerio para la Transición Ecológica", "oficial", ["naturaleza"], "miteco.gob.es", site="miteco.gob.es", horas=96),
    F("aemet", "AEMET (avisos)", "oficial", ["naturaleza"], "aemet.es", "https://www.aemet.es/documentos_d/eltiempo/prediccion/avisos/rss/CAP_AFAE_wah_RSS.xml", horas=24),
    F("comunidadmadrid", "Comunidad de Madrid", "oficial", ["vivienda", "espana"], "comunidad.madrid", site="comunidad.madrid", horas=48),
    F("aytomadrid", "Ayuntamiento de Madrid", "oficial", ["vivienda"], "madrid.es", site="madrid.es", horas=48),
    F("pozuelo", "Ayuntamiento de Pozuelo de Alarcón", "oficial", ["vivienda"], "pozuelodealarcon.org", "https://www.pozuelodealarcon.org/rss.xml", horas=96),
    # Europa e internacional
    F("bce", "Banco Central Europeo", "oficial", ECO, "ecb.europa.eu", "https://www.ecb.europa.eu/rss/press.html", horas=72),
    F("fed", "Reserva Federal", "oficial", ECO, "federalreserve.gov", "https://www.federalreserve.gov/feeds/press_all.xml", horas=72),
    F("boe_uk", "Banco de Inglaterra", "oficial", ECO, "bankofengland.co.uk", "https://www.bankofengland.co.uk/rss/news", horas=72, idioma="en"),
    F("comisionue", "Comisión Europea", "oficial", ["internacional", "mercados"], "ec.europa.eu", "https://ec.europa.eu/commission/presscorner/api/rss?language=es", horas=48),
    F("consejoue", "Consejo de la UE", "oficial", ["internacional", "geopolitica"], "consilium.europa.eu", "https://www.consilium.europa.eu/es/rss/pressreleases.ashx", horas=48),
    F("eurostat", "Eurostat", "oficial", ["mercados"], "ec.europa.eu/eurostat", site="ec.europa.eu/eurostat", horas=72, idioma="en"),
    F("imf", "FMI", "oficial", ECO, "imf.org", site="imf.org", horas=72, idioma="en"),
    F("iea", "Agencia Internacional de la Energía", "oficial", ECO + ["naturaleza"], "iea.org", site="iea.org", horas=168, idioma="en"),
    F("opec", "OPEP", "oficial", ECO, "opec.org", site="opec.org", horas=168, idioma="en"),
    F("nato", "OTAN", "oficial", ["geopolitica"], "nato.int", site="nato.int", horas=72, idioma="en"),
    F("onu", "Noticias ONU", "oficial", ["internacional", "geopolitica"], "news.un.org", site="news.un.org", horas=48),
    F("wmo", "Organización Meteorológica Mundial", "oficial", ["naturaleza"], "wmo.int", site="wmo.int", horas=168, idioma="en"),
    F("noaa", "NOAA", "oficial", ["naturaleza"], "noaa.gov", site="noaa.gov", horas=48, idioma="en"),
    F("nhc", "Centro Nacional de Huracanes (NOAA)", "oficial", ["naturaleza"], "nhc.noaa.gov", "https://www.nhc.noaa.gov/index-at.xml", horas=48, idioma="en"),
    F("copernicus", "Copernicus (clima)", "oficial", ["naturaleza"], "climate.copernicus.eu", "https://climate.copernicus.eu/rss.xml", site="climate.copernicus.eu", horas=720, idioma="en"),
]

# BOE: se lee aparte con su API de datos abiertos (sumario del día)
BOE = {"id": "boe", "nombre": "BOE (sumario del día)", "tipo": "oficial", "bloques": ["espana", "vivienda", "mercados"],
       "dominio": "boe.es", "linea": ""}

# Radar amplio: portadas de Google News, que agregan miles de medios. Solo para ver qué se está contando y en
# cuántos sitios; nunca se cita y no cuenta en «Cobertura».
GN_TEMA = "https://news.google.com/rss/headlines/section/topic/{t}?hl={hl}&gl={gl}&ceid={gl}:{l}"
RADAR = [
    {"id": "gn_es", "nombre": "Google News España · portada", "url": "https://news.google.com/rss?hl=es&gl=ES&ceid=ES:es"},
    {"id": "gn_es_nacional", "nombre": "Google News España · nacional", "url": GN_TEMA.format(t="NATION", hl="es", gl="ES", l="es")},
    {"id": "gn_es_economia", "nombre": "Google News España · economía", "url": GN_TEMA.format(t="BUSINESS", hl="es", gl="ES", l="es")},
    {"id": "gn_es_mundo", "nombre": "Google News España · internacional", "url": GN_TEMA.format(t="WORLD", hl="es", gl="ES", l="es")},
    {"id": "gn_es_ciencia", "nombre": "Google News España · ciencia", "url": GN_TEMA.format(t="SCIENCE", hl="es", gl="ES", l="es")},
    {"id": "gn_es_salud", "nombre": "Google News España · salud", "url": GN_TEMA.format(t="HEALTH", hl="es", gl="ES", l="es")},
    {"id": "gn_us_mundo", "nombre": "Google News EE. UU. · mundo", "url": GN_TEMA.format(t="WORLD", hl="en-US", gl="US", l="en")},
    {"id": "gn_us_economia", "nombre": "Google News EE. UU. · economía", "url": GN_TEMA.format(t="BUSINESS", hl="en-US", gl="US", l="en")},
    {"id": "gn_gb_mundo", "nombre": "Google News Reino Unido · mundo", "url": GN_TEMA.format(t="WORLD", hl="en-GB", gl="GB", l="en")},
    {"id": "gn_local", "nombre": "Google News · Aravaca y Pozuelo", "url": "https://news.google.com/rss/search?q=Aravaca%20OR%20%22Pozuelo%20de%20Alarc%C3%B3n%22%20when%3A3d&hl=es&gl=ES&ceid=ES:es",
     "solo_catalogo": True},
]

# Medios excluidos, con el motivo documentado. No se leen ni se citan.
EXCLUIDOS = {
    "okdiario.com": "Peor balance de credibilidad del Digital News Report España 2025 (31 % confía, 37 % desconfía) y "
                    "resoluciones judiciales por publicar informaciones sin sustento (p. ej., Tribunal de Instancia de "
                    "Sevilla, julio de 2026).",
}

# Otros dominios de referencia que pueden citarse aunque no se lean cada mañana (fuentes primarias y cabeceras
# solventes que suelen aparecer al investigar).
OTROS_DOMINIOS = {
    "boe.es", "bde.es", "oecd.org", "worldbank.org", "who.int", "un.org", "europa.eu", "europarl.europa.eu",
    "eib.org", "bis.org", "esma.europa.eu", "eba.europa.eu", "tesoro.es", "hacienda.gob.es", "seg-social.es",
    "sepe.es", "cis.es", "airef.es", "funcas.es", "bls.gov", "bea.gov", "treasury.gov", "whitehouse.gov",
    "state.gov", "defense.gov", "kremlin.ru", "gov.uk", "elysee.fr", "bundesregierung.de", "esa.int", "nasa.gov",
    "ipcc.ch", "unep.org", "csic.es", "agenciasinc.es", "nature.com", "science.org", "thelancet.com",
    "lamoncloa.gob.es", "mineco.gob.es", "inclusion.gob.es", "transportes.gob.es", "interior.gob.es",
    "sipri.org", "iiss.org", "csis.org", "chathamhouse.org", "brookings.edu", "cfr.org", "rand.org",
    "afp.com", "eldiariodemadrid.es", "alternativaseconomicas.coop",  # los dos últimos, certificados JTI
    # prensa regional de larga trayectoria (la más creíble para los lectores según el Digital News Report España)
    "elcorreo.com", "diariovasco.com", "heraldo.es", "lavozdegalicia.es", "elnortedecastilla.es", "diariodesevilla.es",
    "levante-emv.com", "lasprovincias.es", "ideal.es", "laverdad.es", "diariodenavarra.es", "lne.es", "farodevigo.es",
    "morningstar.es", "morningstar.com", "barrons.com", "axios.com", "washingtonpost.com", "latimes.com",
    "theatlantic.com", "time.com", "cnn.com", "nbcnews.com", "cbsnews.com", "abcnews.go.com", "news.sky.com",
    "independent.co.uk", "telegraph.co.uk", "thetimes.co.uk", "lefigaro.fr", "liberation.fr", "zeit.de",
    "sueddeutsche.de", "repubblica.it", "publico.pt", "expresso.pt", "clarin.com", "eltiempo.com", "elespectador.com",
    "emol.com", "abcnews.com", "elcomercio.pe", "ladiaria.com.uy", "laopinion.com", "excelsior.com.mx", "ara.cat",
    # radiotelevisiones públicas autonómicas
    "canalsur.es", "ccma.cat", "3cat.cat", "eitb.eus", "crtvg.es", "apuntmedia.es", "rtpa.es", "aragondigital.es",
    # agencias y prensa especializada de referencia (energía, transporte marítimo, Asia)
    "gcaptain.com", "lloydslist.com", "spglobal.com", "argusmedia.com", "asia.nikkei.com", "nikkei.com",
    "en.yna.co.kr", "english.kyodonews.net", "aemet.es", "meteofrance.com", "metoffice.gov.uk",
}


def dominio_de(url):
    from urllib.parse import urlparse
    host = urlparse(url).netloc.lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def en_lista(host, dominios):
    """True si host es uno de los dominios o un subdominio suyo (también admite dominios con ruta, p. ej. ec.europa.eu/eurostat)."""
    for d in dominios:
        base = d.split("/")[0]
        if host == base or host.endswith("." + base):
            return True
    return False


OFICIAL_SUFIJOS = (".gob.es", ".gov", ".gov.uk", ".europa.eu", ".int", ".mil", ".gouv.fr", ".bund.de", ".gob.mx", ".gob.ar")


def clasificar_dominio(url):
    """'excluido', 'catalogo', 'oficial', 'referencia' u 'otro'."""
    host = dominio_de(url)
    if en_lista(host, EXCLUIDOS):
        return "excluido"
    if en_lista(host, {f["dominio"] for f in FUENTES} | {BOE["dominio"]}):
        return "catalogo"
    if host.endswith(OFICIAL_SUFIJOS) or en_lista(host, {"boe.es", "bde.es", "ine.es", "cnmv.es", "imf.org", "oecd.org", "un.org"}):
        return "oficial"
    if en_lista(host, OTROS_DOMINIOS):
        return "referencia"
    return "otro"


if __name__ == "__main__":
    # python3 scripts/fuentes_catalogo.py [bloque]  → dominios de referencia (catálogo y oficiales) del bloque, para
    # usarlos en WebSearch como allowed_domains; sin bloque, todos.
    import json, sys
    b = sys.argv[1] if len(sys.argv) > 1 else None
    doms = sorted({f["dominio"].split("/")[0] for f in FUENTES if not b or b in f["bloques"]} | ({"boe.es"} if not b or b in BOE["bloques"] else set()))
    print(json.dumps(doms, ensure_ascii=False))
